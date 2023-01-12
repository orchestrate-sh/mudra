#!/bin/bash
set -eux

NAME=$1
SLEEP_SECONDS=$2
NODE_ENV_FILE=$3

echo "INFO: Executing k8s script for ${NAME}"

# Source common.sh
readonly ROOT_DIR="$(cd "$(dirname "${0}")" && pwd)"
source "${ROOT_DIR}/../common.sh" || exit 1

# Source the node env file
source ".meta/${NODE_ENV_FILE}.env"

# Force login to k8s on AWS
# kubectl --namespace alfa auth can-i get pod --quiet || true

# Set default APP_AFFINITY if not set
APP_AFFINITY="${APP_AFFINITY:=Exclusive}"
# Set default K8S_MIN_INSTANCES if not set
K8S_MIN_INSTANCES="${K8S_MIN_INSTANCES:=0}"
# Display K8S_MIN_INSTANCES
echo "K8S_MIN_INSTANCES: ${K8S_MIN_INSTANCES}"
# DRYRUN with a default of False (TO BE IMPLEMENTED)
DRYRUN="${DRYRUN:=False}"

# Determine StatefulSet or Deployment, default is Deployment
if [ -z ${SERVICE_TYPE+x} ]; then
    SERVICE_TYPE="Deployment"
fi
echo "SERVICE_TYPE: ${SERVICE_TYPE}"

# Set kubectl output logfile paths
KUBECTL_LOGFILE_PATH="logs/node_logs/App/kubectl_output"
# Set PVC_DELETION_CACHE_FILE
PVC_DELETION_CACHE_FILE="logs/node_logs/App/deletepvcs/${NAME}_pvc_cache"
# Set kubectl replica count file paths
KUBECTL_REPLICA_COUNT_PATH="logs/node_logs/App/replica_counts"
EFFECTIVE_REPLICA_COUNT_PATH="logs/node_logs/App/replica_counts/effective"
# Set special logfile paths
KUBECTL_SERVICES_MISSING_NAMESPACES_LOG="logs/node_logs/App/kubectl_services_missing_namespaces.log"

# Ensure that necessary cache and log directories/files exist
mkdir -p ${KUBECTL_LOGFILE_PATH}
mkdir -p ${KUBECTL_REPLICA_COUNT_PATH}
mkdir -p ${EFFECTIVE_REPLICA_COUNT_PATH}
mkdir -p logs/node_logs/App/deletepvcs
touch ${KUBECTL_SERVICES_MISSING_NAMESPACES_LOG}

# See if K8S_SOURCE_NAME and K8S_TARGET_NAME are configured, if not then set to NAME
if [ -z ${K8S_SOURCE_NAME+x} ]; then
    # Configure K8S_SOURCE_NAME
    K8S_SOURCE_NAME=$NAME
fi
echo "K8S_SOURCE_NAME: ${K8S_SOURCE_NAME}"
if [ -z ${K8S_TARGET_NAME+x} ]; then
    # Configure K8S_TARGET_NAME
    K8S_TARGET_NAME=$NAME
fi
echo "K8S_TARGET_NAME: ${K8S_TARGET_NAME}"

# Ensure source and target K8S namespaces are configured, if not then set to K8S_NAMESPACE
MISSING_NAMESPACE_COUNT=0
if [ -z ${K8S_SOURCE_NAMESPACE+x} ]; then
    # Ensure K8S_NAMESPACE is configured since K8S_SOURCE_NAMESPACE not configured
    if [ -z ${K8S_NAMESPACE+x} ]; then
        echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_SOURCE_CONTEXT}"
        echo "${NAME} in ${K8S_SOURCE_CONTEXT} Kubernetes namespace not configured" >>${KUBECTL_SERVICES_MISSING_NAMESPACES_LOG}
        MISSING_NAMESPACE_COUNT=$(($MISSING_NAMESPACE_COUNT + 1))
    else
        # Configure K8S_SOURCE_NAMESPACE
        K8S_SOURCE_NAMESPACE=$K8S_NAMESPACE
    fi
fi
echo "K8S_SOURCE_NAMESPACE: ${K8S_SOURCE_NAMESPACE}"
if [ -z ${K8S_TARGET_NAMESPACE+x} ]; then
    # Ensure K8S_NAMESPACE is configured since K8S_TARGET_NAMESPACE not configured
    if [ -z ${K8S_NAMESPACE+x} ]; then
        echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_TARGET_CONTEXT}"
        echo "${NAME} in ${K8S_TARGET_CONTEXT} Kubernetes namespace not configured" >>${KUBECTL_SERVICES_MISSING_NAMESPACES_LOG}
        MISSING_NAMESPACE_COUNT=$(($MISSING_NAMESPACE_COUNT + 1))
    else
        # Configure K8S_TARGET_NAMESPACE
        K8S_TARGET_NAMESPACE=$K8S_NAMESPACE
    fi
fi
echo "K8S_TARGET_NAMESPACE: ${K8S_TARGET_NAMESPACE}"
# Exit if K8S_SOURCE_NAMESPACE or K8S_TARGET_NAMESPACE not configured
if [ ${MISSING_NAMESPACE_COUNT} -gt 0 ]; then
    echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_SOURCE_CONTEXT} and/or ${K8S_TARGET_CONTEXT}, exiting"
    exit 1
fi

# If running locally, just output relevant verification info and exit 0
if [ $environment == "local" ]; then
    if [ ! -z ${K8S_SOURCE_ONLY+x} ]; then
        echo "K8S_SOURCE_ONLY"
    fi
    [ ${K8S_TARGET_ONLY:-} ] && echo K8S_TARGET_ONLY
    exit 0
fi

# Check if K8S_APP_LABEL_SELECTOR is set
if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
    echo "INFO: Targeting all ${NAME} services by selector, ${K8S_APP_LABEL_SELECTOR}"
fi

###############################################################################

# Function to execute kubectl get command
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name
# $3 = kubectl namespace
# $4 = kubectl context
function kubectl_get() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_get ${service_type} ${name} ${namespace} ${context}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${name}-${context}.log"
    # Execute kubectl command
    kubectl get ${service_type} ${name} --namespace ${namespace} --context=${context} > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Check for errors
    if [ $result -ne 0 ]; then
        echo "FAIL: kubectl command output, ${logfile}"
        # TODO: Should this be an echo or a return?
        return $result
    fi
}

# Function to execute kubectl get command against selector-based service(s)
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl namespace
# $3 = kubectl context
function kubectl_get_by_selector() {
    local service_type=$1
    local namespace=$2
    local context=$3
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_get_by_selector ${service_type} ${namespace} ${context}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${K8S_APP_LABEL_SELECTOR}-${context}.log"
    # Execute kubectl command and log to named file
    local svc_list=$(kubectl get ${service_type} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${namespace} --context=${context} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true) > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Validate service list is not empty or result is not 0
    if [ -z "${svc_list}" ] || [ $result -ne 0 ]; then
        echo "FAIL: Kubernetes ${service_type}(s) not found on namespace ${namespace} in context ${context} with selector ${K8S_APP_LABEL_SELECTOR}"
        return $result
    else
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Execute kubectl to validate service
            kubectl_get ${service_type} ${svc} ${namespace} ${context}
        done <<<"$svc_list"
    fi
}

# Function to execute kubectl to get replica count
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name
# $3 = kubectl namespace
# $4 = kubectl context
function kubectl_get_replica_count() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_get_replica_count ${service_type} ${name} ${namespace} ${context}" >&2
    local logfile="${KUBECTL_LOGFILE_PATH}/${name}-${context}.log"
    # TODO: Determine if the double-execution of the commands can be avoided
    # Execute kubectl command to obtain replica count and log to named file
    # kubectl get ${service_type} ${name} --namespace ${namespace} --context=${context} -o=jsonpath='{.status.replicas}' > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    replica_count=$(kubectl get ${service_type} ${name} --namespace ${namespace} --context=${context} -o=jsonpath='{.status.replicas}')
    local result=$?
    # Check for errors
    if [ $result -ne 0 ]; then
        # echo "FAIL: kubectl command output, ${logfile}"
        # TODO: Determine if the double-execution of the commands can be avoided
        # Execute the kubectl command again to log error to named file (temporary workaround)
        $(kubectl get ${service_type} ${name} --namespace ${namespace} --context=${context} -o=jsonpath='{.status.replicas}' > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2))
        # TODO: Should this be an echo or a return?
        return $result
    fi
    # Check for valid replica count
    # if [ -z ${replica_count+x} ]; then
    #     return 1
    # fi
    # Display replica count
    # echo "Replica count for '${name}' in ${namespace} namespace on cluster ${context}: ${replica_count}"
    # Ensure replica count is a valid number, otherise return K8S_MIN_INSTANCES
    re='^[0-9]+$'
    if ! [[ $replica_count =~ $re ]]; then
        echo ${K8S_MIN_INSTANCES}
        return 1
    fi
    # Return replica count
    echo ${replica_count}
}

# Function to read/cache replica count
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name
# $3 = kubectl namespace
# $4 = kubectl context
function kubectl_cache_replica_count() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    local replica_count_file="${KUBECTL_REPLICA_COUNT_PATH}/${name}-${context}.txt"
    # Cache replica count if not already cached
    if [[ ! -e ${replica_count_file} ]]; then
        local replica_count=$(kubectl_get_replica_count ${service_type} ${name} ${namespace} ${context})
        local result=$?
        # If replica count is not valid, return error
        if [ $result -ne 0 ]; then
            return $result
        fi
        touch ${replica_count_file}
        echo $replica_count >${replica_count_file}
    fi
    # Read cached replica count
    local cached_replica_count=$(cat ${replica_count_file})
    # Ensure cached replica count is a valid number, otherise return K8S_MIN_INSTANCES
    re='^[0-9]+$'
    if ! [[ $cached_replica_count =~ $re ]]; then
        echo ${K8S_MIN_INSTANCES}
        return 1
    fi
    # Return cached replica count
    echo ${cached_replica_count}
}

# Function to execute kubectl against selector-based service(s) to get replica count (uses source context for service list lookup)
# $1 = kubectl service type (sts or deployment)
function kubectl_get_replica_counts_by_selector() {
    local service_type=$1
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_get_replica_counts_by_selector ${service_type}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${K8S_APP_LABEL_SELECTOR}-${K8S_SOURCE_CONTEXT}.log"
    # Execute kubectl command and log to named file
    local svc_list=$(kubectl get ${service_type} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true) > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Validate service list is not empty or result is not 0
    if [ -z "${svc_list}" ] || [ $result -ne 0 ]; then
        echo "FAIL: Kubernetes ${service_type}(s) not found on namespace ${K8S_SOURCE_NAMESPACE} in context ${K8S_SOURCE_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
        # TODO: Should this be an echo or a return?
        return $result
    else
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Get replica counts for service
            kubectl_get_replica_count ${svc} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT}
            # Get replica counts for service (target)
            kubectl_get_replica_count ${svc} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT}
        done <<<"$svc_list"
    fi
}

# Function to find app pods and their corresponding pvcs and cache the pvc list to a file
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name
# $3 = kubectl namespace
# $4 = kubectl context
function cache_pvcs_by_app() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    local logfile="${KUBECTL_LOGFILE_PATH}/${name}-${context}.log"
    # Cache PVCs based on deployment or statefulset name
    echo "INFO: Caching PVC's by ${service_type} ${name} in namespace ${namespace} and context ${context}"
    # Get comma-separated selectors for resource
    local label_selectors="$(kubectl --namespace ${namespace} --context=${context} get ${service_type} ${name} -o json | jq -r '.spec.selector.matchLabels | to_entries | map("\(.key)=\(.value)") | join(",")')"
    # If no selectors, exit
    if [ -z ${label_selectors+x} ]; then
        echo "FAIL: No selectors found for ${service_type} ${name} in namespace ${namespace} and context ${context}"
        exit 1
    fi
    echo "INFO: Label Selectors, ${label_selectors}"
    # Get pod names by selectors
    local pods="$(kubectl get pods -l "${label_selectors}" --namespace ${namespace} --context=${context} --no-headers -o custom-columns=":metadata.name")"
    # If no pods, exit
    if [ -z ${pods+x} ]; then
        echo "FAIL: No pods found for ${service_type} ${name} in namespace ${namespace} and context ${context}"
        return
    fi
    echo "INFO: Pods, ${pods}"
    # for each pod, record PVCs
    local pvcs_to_cache=() # array of pvcs to cache
    for pod in ${pods}; do
        echo "INFO: Processing pod ${pod}"
        # Get pod's PVC names
        local pvcs="$(kubectl get pod --namespace ${namespace} --context=${context} ${pod} -o json | jq -r '.spec.volumes[] | select(.persistentVolumeClaim != null) | .persistentVolumeClaim.claimName')"
        # Add pvcs to cache array
        echo "INFO: Adding PVC's to cache array ${pvcs} for pod ${pod} in namespace ${namespace} and context ${context}"
        pvcs_to_cache+=(${pvcs})
    done

    if ((${#pvcs_to_cache[@]} > 0)); then
        # Cache PVCs to a file
        echo "INFO: Caching PVC's for pod ${pod} in namespace ${namespace} and context ${context}: ${pvcs_to_cache[@]} to ${PVC_DELETION_CACHE_FILE}"
        # Ensure the PVC_DELETION_CACHE_FILE exists
        touch "${PVC_DELETION_CACHE_FILE}"
        # Append pvcs_to_cache to PVC_DELETION_CACHE_FILE
        echo "${pvcs_to_cache[@]}" >>"${PVC_DELETION_CACHE_FILE}"
        # printf " ${pvcs_to_cache[@]} " >>${PVC_DELETION_CACHE_FILE}
    else
        # No PVCs to cache
        echo "INFO: No PVC's to cache for ${service_type} ${name}"
    fi
}

# Function to scale kubectl services
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name
# $3 = kubectl namespace
# $4 = kubectl context
# $5 = desired replica count
function kubectl_scale() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    local replicas=$5
    # If the context is source, and we need to delete PVCs on scale down for source
    if [[ ${K8S_DELETE_PVCS_ON_SCALE_DOWN} = "source" && ${context} = ${K8S_SOURCE_CONTEXT} && ${replicas} -eq 0 ]]; then
        # Cache source PVCs for deletion on scale down
        cache_pvcs_by_app ${service_type} ${name} ${namespace} ${context}
    # Else if the context is target, and we need to delete PVCs on scale down for target
    elif [[ ${K8S_DELETE_PVCS_ON_SCALE_DOWN} = "target" && ${context} = ${K8S_TARGET_CONTEXT} && ${replicas} -eq 0 ]]; then
        # Cache target PVCs for deletion on scale down
        cache_pvcs_by_app ${service_type} ${name} ${namespace} ${context}
    # Otherwise assume we need to delete PVCs in source and target on scale down
    elif [[ ${K8S_DELETE_PVCS_ON_SCALE_DOWN} != "source" && ${K8S_DELETE_PVCS_ON_SCALE_DOWN} != "target" && ${replicas} -eq 0 ]]; then
        # Cache all PVCs for deletion on scale down
        cache_pvcs_by_app ${service_type} ${name} ${namespace} ${context}
    fi
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_scale ${service_type} ${name} ${namespace} ${context} ${replicas}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${name}-${context}.log"
    # Execute kubectl command and log to named file
    kubectl scale --replicas=${replicas} ${service_type} ${name} --namespace ${namespace} --context=${context} > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Check for errors
    if [ $result -ne 0 ]; then
        echo "FAIL: kubectl command output, ${logfile}"
        # TODO: Should this be an echo or a return?
        return $result
    fi
    # Delete cached pvcs, if the cache file is not empty and replicas is 0
    if [ -f ${PVC_DELETION_CACHE_FILE} ] && [ ${replicas} -eq 0 ]; then
        # Read pvc list from PVC_DELETION_CACHE_FILE and strip control characters, set to pvcs_to_delete
        local pvcs_to_delete=$(cat ${PVC_DELETION_CACHE_FILE} | tr -d '\r' | tr -d '\n')
        echo "INFO: Deleting PVC's for ${service_type} ${name} in namespace ${namespace} and context ${context}: $(cat ${PVC_DELETION_CACHE_FILE})"
        # # Iterate through pvcs_to_delete, strip integer from the end, use kubectl to find all pvc's with that name and append them to pvcs_to_delete
        # local pvcs_to_delete_array=()
        # while IFS= read -r pvc; do
        #     local pvc_name=$(echo ${pvc} | sed 's/[0-9]*$//')
        #     local pvcs="$(kubectl get pvc --namespace ${namespace} --context=${context} | grep ${pvc_name})"
        #     echo "INFO: Found PVC's ${pvcs}"
        #     pvcs_to_delete_array+=(${pvcs})
        # done <<<"$pvcs_to_delete"
        # # Concatenate pvcs_to_delete_array into pvcs_to_delete and strip control characters
        # pvcs_to_delete=$(echo "${pvcs_to_delete_array[@]}" | tr -d '\r' | tr -d '\n')
        echo "INFO: PVC's to be deleted: ${pvcs_to_delete}"
        # Actually delete the PVCs
        kubectl delete pvc --namespace ${namespace} --context=${context} ${pvcs_to_delete} > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2) &
    fi
}

# TODO: Have this function read the replica count from read_effective_replica_count
# Function to execute kubectl to scale service(s) by selector
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl namespace
# $3 = kubectl context
# $4 = desired replica count
function kubectl_scale_by_selector() {
    local service_type=$1
    local namespace=$2
    local context=$3
    local replicas=$4
    # Log what we are doing to stdout
    echo "INFO: Executing, kubectl_scale_by_selector ${service_type} ${namespace} ${context} ${replicas}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${name}-${context}.log"
    # Execute kubectl command and log to named file
    local svc_list=$(kubectl get ${service_type} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${namespace} --context=${context} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true) > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Validate service list is not empty or result is not 0
    if [ -z "${svc_list}" ] || [ $result -ne 0 ]; then
        echo "FAIL: Kubernetes ${service_type}(s) not found on namespace ${namespace} in context ${context} with selector ${K8S_APP_LABEL_SELECTOR}"
        # TODO: Should this be an echo or return?
        return $result
    else
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Execute kubectl to validate service
            kubectl_scale ${service_type} ${svc} ${namespace} ${context} ${replicas}
        done <<<"$svc_list"
    fi
}

# Function to save effective replica count
# $1 = kubectl service name
# $2 = kubectl context
# $3 = replica count
function save_effective_replica_count() {
    local name=$1
    local context=$2
    local replica_count=$3
    # Log what we are doing to stdout
    echo "INFO: Executing, save_effective_replica_count ${name} ${context} ${replica_count}" >&2
    local effective_replica_count_file="${EFFECTIVE_REPLICA_COUNT_PATH}/${NODE_ENV_FILE}-${name}-${context}.txt"
    # Cache effective replica count, overwriting existing file
    touch ${effective_replica_count_file}
    echo $replica_count >${effective_replica_count_file}
    # Ensure replica count is a valid number, otherise return K8S_MIN_INSTANCES
    re='^[0-9]+$'
    if ! [[ $replica_count =~ $re ]]; then
        echo ${K8S_MIN_INSTANCES}
        return 1
    fi
    # Return effective replica count
    echo ${replica_count}
}

# Function to get effective replica count
# $1 = kubectl service name
# $2 = kubectl context
function read_effective_replica_count() {
    local name=$1
    local context=$2
    # Log what we are doing to stdout
    # echo "INFO: Executing, read_effective_replica_count ${name} ${context}" >&2
    local effective_replica_count_file="${EFFECTIVE_REPLICA_COUNT_PATH}/${NODE_ENV_FILE}-${name}-${context}.txt"
    # Read effective replica count
    local effective_replica_count=$(cat ${effective_replica_count_file})
    # Ensure effective replica count is a valid number, otherise return K8S_MIN_INSTANCES
    re='^[0-9]+$'
    if ! [[ $effective_replica_count =~ $re ]]; then
        echo ${K8S_MIN_INSTANCES}
        return 1
    fi
    # Return effective replica count
    echo ${effective_replica_count}
}

# Function to validate and finalize replica counts
# $1 = kubectl source_name
# $2 = kubectl source_name
# $3 = source_replica_count
# $4 = target_replica_count
function finalize_replica_counts() {
    local source_name=$1
    local target_name=$2
    local source_replica_count=$3
    local target_replica_count=$4
    # Log what we are doing to stdout
    echo "INFO: Executing, finalize_replica_counts ${source_name} ${target_name} ${source_replica_count} ${target_replica_count}"
    echo "INFO: Finalizing replica counts for ${source_name} (source) ${target_name} (target) in contexts ${K8S_SOURCE_CONTEXT} (source) and ${K8S_TARGET_CONTEXT} (target) using replica counts ${source_replica_count} (source) and ${target_replica_count} (target)"
    if [ ${source_replica_count} = 0 ]; then
        echo "FAIL: source_replica_count: ${source_replica_count}"
        exit 1
    fi
    # Perform exceptions with replica counts
    # Set max_instances to K8S_MAX_INSTANCES if K8S_MAX_INSTANCES is set, otherwise set to source_replica_count
    if [ ! -z "${K8S_MAX_INSTANCES+x}" ]; then
        echo "INFO: Default K8S_MAX_INSTANCES, ${K8S_MAX_INSTANCES}"
        local max_instances="${K8S_MAX_INSTANCES}"
    else
        local max_instances="${source_replica_count}"
    fi
    # Set max_instances to source_replica_count or K8S_MAX_INSTANCES if not set

    # Display max_instances
    echo "INFO: max_instances, ${max_instances}"
    local min_instances="${K8S_MIN_INSTANCES}"
    # Display min_instances
    echo "INFO: min_instances, ${min_instances}"
    # Initialize final_source_replica_count as source_replica_count
    local final_source_replica_count=${source_replica_count}
    # If APP_AFFINITY is Exclusive, final_source_replica_count should be min_instances
    if [ $APP_AFFINITY = "Exclusive" ]; then
        local final_source_replica_count=${min_instances}
    fi
    # Configure final_target_replica_count as source_replica_count
    local final_target_replica_count=${source_replica_count}
    # Validate final_source_replica_count
    # Validate final_source_replica_count is not less than min_instances, otherwise set to min_instances
    if [ $final_source_replica_count -lt ${min_instances} ]; then
        local final_source_replica_count=${min_instances}
    fi
    # Validate final_source_replica_count is not more than max_instances, otherwise set to max_instances
    if [ $final_source_replica_count -gt ${max_instances} ]; then
        local final_source_replica_count=${max_instances}
    fi
    # Override FINAL_*_REPLICA_COUNT if we are rolling back (after min/max instances check)
    if [ ! -z ${ROLLBACK_K8S+x} ]; then
        local final_source_replica_count=${source_replica_count}
        local final_target_replica_count=${target_replica_count}
    fi
    # Validate final_source_replica_count not empty, otherwise set to min_instances
    if [ -z ${final_source_replica_count+x} ]; then
        local final_source_replica_count=${min_instances}
    fi
    # Validate final_source_replica_count is a number, otherwise set to min_instances
    re='^[0-9]+$'
    if ! [[ $final_source_replica_count =~ $re ]]; then
        local final_source_replica_count=${min_instances}
    fi
    # Validate final_target_replica_count
    # Validate final_target_replica_count is not less than min_instances, otherwise set to min_instances
    if [ $final_target_replica_count -lt ${min_instances} ]; then
        local final_target_replica_count=${min_instances}
    fi
    # Validate final_target_replica_count is not more than max_instances, otherwise set to max_instances
    if [ $final_target_replica_count -gt ${max_instances} ]; then
        local final_target_replica_count=${max_instances}
    fi
    # Validate final_target_replica_count not empty, otherwise set to min_instances
    if [ -z ${final_target_replica_count+x} ]; then
        local final_target_replica_count=${min_instances}
    fi
    # Validate final_target_replica_count is a number, otherwise set to min_instances
    re='^[0-9]+$'
    if ! [[ $final_target_replica_count =~ $re ]]; then
        local final_target_replica_count=${min_instances}
    fi
    echo "INFO: final_source_replica_count for ${source_name} in context ${K8S_SOURCE_CONTEXT}: ${final_source_replica_count}"
    save_effective_replica_count ${source_name} ${K8S_SOURCE_CONTEXT} ${final_source_replica_count}
    echo "INFO: final_target_replica_count for ${target_name} in context ${K8S_TARGET_CONTEXT}: ${final_target_replica_count}"
    save_effective_replica_count ${target_name} ${K8S_TARGET_CONTEXT} ${final_target_replica_count}
}

# Function to validate and finalize replica counts by selector (uses source context for service list lookup)
# $1 = kubectl service type (sts or deployment)
function finalize_replica_counts_by_selector() {
    local service_type=$1
    # Log what we are doing to stdout
    echo "INFO: Executing, finalize_replica_counts_by_selector ${service_type}"
    local logfile="${KUBECTL_LOGFILE_PATH}/${K8S_APP_LABEL_SELECTOR}-${K8S_SOURCE_CONTEXT}.log"
    # Execute kubectl command and log to named file
    local svc_list=$(kubectl get ${service_type} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true) > >(tee -a ${logfile}) 2> >(tee -a ${logfile} >&2)
    local result=$?
    # Validate service list is not empty or result is not 0
    if [ -z "${svc_list}" ] || [ $result -ne 0 ]; then
        echo "FAIL: Kubernetes ${service_type}(s) not found on namespace ${K8S_SOURCE_NAMESPACE} in context ${K8S_SOURCE_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
        # TODO: Should this be an echo or a return?
        return $result
    else
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Finalize and save replica counts for service
            # finalize_replica_counts ${svc} $(kubectl_cache_replica_count ${service_type} ${svc} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT}) $(kubectl_cache_replica_count ${service_type} ${svc} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT})
            finalize_replica_counts_by_name ${service_type} ${svc} ${svc}
        done <<<"$svc_list"
    fi
}

# Function to finalize source and target replica counts by service name
# $1 = kubectl service type (sts or deployment)
# $2 = kubectl service name (source)
# $2 = kubectl service name (target)
function finalize_replica_counts_by_name() {
    local service_type=$1
    local source_name=$2
    local target_name=$3
    # Log what we are doing to stdout
    echo "INFO: Executing, finalize_replica_counts_by_name ${service_type} (kubectl_cache_replica_count ${service_type} ${source_name} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT}) (kubectl_cache_replica_count ${service_type} ${target_name} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT})"
    # Finalize replica counts
    finalize_replica_counts ${source_name} ${target_name} $(kubectl_cache_replica_count ${service_type} ${source_name} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT}) $(kubectl_cache_replica_count ${service_type} ${target_name} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT})
}

###############################################################################

# Validate services, gather, validate and finalize effective replica counts
echo "INFO: Validating service(s) exist on both sides and gathering replica counts"
# StatefulSet vs. Deployment
if [ $SERVICE_TYPE = "StatefulSet" ]; then
    # k8s selectors vs. standalone
    if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
        # Get SOURCE StatefulSet list to validate selector
        finalize_replica_counts_by_selector sts
    else
        # Finalize StatefulSet replica counts for source and target
        finalize_replica_counts_by_name sts ${K8S_SOURCE_NAME} ${K8S_TARGET_NAME}
    fi
else
    # k8s selectors vs. standalone
    if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
        # Get SOURCE Deployment list to validate selector
        finalize_replica_counts_by_selector deployment
    else
        # Finalize Deployment replica counts for source and target
        finalize_replica_counts_by_name deployment ${K8S_SOURCE_NAME} ${K8S_TARGET_NAME}
    fi
fi

###############################################################################

# If this is preflight, exit here before actually scaling
if [ ! -z ${PREFLIGHT+x} ]; then
    exit 0
fi

###############################################################################

# If not K8S_TARGET_ONLY, scale source side
if [ -z ${K8S_TARGET_ONLY+x} ]; then
    # Scale pods on source side
    echo "INFO: Scaling pods for ${NAME} on source side (${K8S_SOURCE_CONTEXT})..."
    # StatefulSet vs. Deployment
    if [ $SERVICE_TYPE = "StatefulSet" ]; then
        # k8s selectors vs. standalone
        if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
            # Get service list
            svc_list=$(kubectl get sts --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} --selector="${K8S_APP_LABEL_SELECTOR}" -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)
            # Validate service list
            if [ -z "${svc_list}" ]; then
                echo "FAIL: Kubernetes StatefulSet(s) not found on source namespace: ${K8S_SOURCE_NAMESPACE} in context ${K8S_SOURCE_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
            else
                # Iterate through service list and perform actions
                while IFS= read -r line; do
                    # Extract service name
                    svc=$(echo ${line} | awk '{print $1}')
                    # Set effective replica count
                    count=$(read_effective_replica_count ${svc} ${K8S_SOURCE_CONTEXT})
                    # Execute kubectl to scale service
                    kubectl_scale sts ${svc} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT} ${count}
                done <<<"$svc_list"
            fi
        else
            # Execute kubectl to scale service
            kubectl_scale sts ${K8S_SOURCE_NAME} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT} $(read_effective_replica_count ${NAME} ${K8S_SOURCE_CONTEXT})
        fi
    else
        # k8s selectors vs. standalone
        if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
            # Get service list
            svc_list=$(kubectl get deployments --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} --selector="${K8S_APP_LABEL_SELECTOR}" -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)
            # Validate service list
            if [ -z "${svc_list}" ]; then
                echo "FAIL: Kubernetes Deployment(s) not found on source namespace: ${K8S_SOURCE_NAMESPACE} in context ${K8S_SOURCE_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
            else
                # Iterate through service list and perform actions
                while IFS= read -r line; do
                    # Extract service name
                    svc=$(echo ${line} | awk '{print $1}')
                    # Set effective replica count
                    count=$(read_effective_replica_count ${svc} ${K8S_SOURCE_CONTEXT})
                    # Execute kubectl to scale service
                    kubectl_scale deployment ${svc} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT} ${count}
                done <<<"$svc_list"
            fi
        else
            # Execute kubectl to scale service
            kubectl_scale deployment ${K8S_SOURCE_NAME} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT} $(read_effective_replica_count ${NAME} ${K8S_SOURCE_CONTEXT})
        fi
    fi
    echo "INFO: Scaling of pods for ${NAME} completed on ${K8S_SOURCE_CONTEXT}."
fi

###############################################################################

# If not K8S_SOURCE_ONLY, scale target side
if [ -z ${K8S_SOURCE_ONLY+x} ]; then
    # Scale pods on target side
    echo "INFO: Scaling pods for ${NAME} on target side (${K8S_TARGET_CONTEXT})..."
    # StatefulSet vs. Deployment
    if [ $SERVICE_TYPE = "StatefulSet" ]; then
        # k8s selectors vs. standalone
        if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
            # Get service list
            svc_list=$(kubectl get sts --namespace ${K8S_TARGET_NAMESPACE} --context=${K8S_TARGET_CONTEXT} --selector="${K8S_APP_LABEL_SELECTOR}" -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)
            # Validate service list
            if [ -z "${svc_list}" ]; then
                echo "FAIL: Kubernetes StatefulSet(s) not found on target namespace: ${K8S_TARGET_NAMESPACE} in context ${K8S_TARGET_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
            else
                # Iterate through service list and perform actions
                while IFS= read -r line; do
                    # Extract service name
                    svc=$(echo ${line} | awk '{print $1}')
                    # Set effective replica count
                    count=$(read_effective_replica_count ${svc} ${K8S_TARGET_CONTEXT})
                    # Execute kubectl to scale service
                    kubectl_scale sts ${svc} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT} ${count}
                done <<<"$svc_list"
            fi
        else
            # Execute kubectl to scale service
            kubectl_scale sts ${K8S_TARGET_NAME} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT} $(read_effective_replica_count ${NAME} ${K8S_TARGET_CONTEXT})
        fi
    else
        # k8s selectors vs. standalone
        if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
            # Get service list
            svc_list=$(kubectl get deployments --namespace ${K8S_TARGET_NAMESPACE} --context=${K8S_TARGET_CONTEXT} --selector="${K8S_APP_LABEL_SELECTOR}" -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)
            # Validate service list
            if [ -z "${svc_list}" ]; then
                echo "FAIL: Kubernetes Deployment(s) not found on target namespace ${K8S_TARGET_NAMESPACE} in context ${K8S_TARGET_CONTEXT} with selector ${K8S_APP_LABEL_SELECTOR}"
            else
                # Iterate through service list and perform actions
                while IFS= read -r line; do
                    # Extract service name
                    svc=$(echo ${line} | awk '{print $1}')
                    # Set effective replica count
                    count=$(read_effective_replica_count ${svc} ${K8S_TARGET_CONTEXT})
                    # Execute kubectl to scale service
                    kubectl_scale deployment ${svc} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT} ${count}
                done <<<"$svc_list"
            fi
        else
            # Execute kubectl to scale service
            kubectl_scale deployment ${K8S_TARGET_NAME} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT} $(read_effective_replica_count ${NAME} ${K8S_TARGET_CONTEXT})
        fi
    fi
    echo "INFO: Scaling of pods for ${NAME} completed on ${K8S_TARGET_CONTEXT}."
fi

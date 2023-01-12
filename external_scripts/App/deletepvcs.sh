#!/bin/bash
set -eux

NAME=$1
SLEEP_SECONDS=$2
NODE_ENV_FILE=$3

echo "INFO: Executing deletepvcs script for ${NAME}"

# Source common.sh
readonly ROOT_DIR="$(cd "$(dirname "${0}")" && pwd)"
source "${ROOT_DIR}/../common.sh" || exit 1

# Source the node env file
source ".meta/${NODE_ENV_FILE}.env"

# Force login to k8s on AWS
# kubectl --namespace alfa auth can-i get pod --quiet || true

# Set kubectl output logfile paths
KUBECTL_LOGFILE_PATH="logs/node_logs/App/deletepvcs"

# Set PVC_DELETION_CACHE_FILE
PVC_DELETION_CACHE_FILE="logs/node_logs/App/deletepvcs/${NAME}_pvc_cache"

# Set PVC_DELETION_ACTUAL_LOGFILE
PVC_DELETION_ACTUAL_LOGFILE="logs/node_logs/App/deletepvcs/${NAME}_pvc_actual.log"

# Ensure that cache directories exist
mkdir -p ${KUBECTL_LOGFILE_PATH}

# Configure logfile
LOGFILE="${KUBECTL_LOGFILE_PATH}/${NAME}.log"

# Ensure source and target K8S namespaces are configured, if not then set to K8S_NAMESPACE
MISSING_NAME_SPACE_COUNT=0
if [ -z ${K8S_SOURCE_NAMESPACE+x} ]; then
    # Ensure K8S_NAMESPACE is configured since K8S_SOURCE_NAMESPACE not configured
    if [ -z ${K8S_NAMESPACE+x} ]; then
        echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_SOURCE_CONTEXT}"
        MISSING_NAME_SPACE_COUNT=$(($MISSING_NAME_SPACE_COUNT + 1))
    else
        # Configure K8S_SOURCE_NAMESPACE
        K8S_SOURCE_NAMESPACE=$K8S_NAMESPACE
    fi
fi
if [ -z ${K8S_TARGET_NAMESPACE+x} ]; then
    # Ensure K8S_NAMESPACE is configured since K8S_TARGET_NAMESPACE not configured
    if [ -z ${K8S_NAMESPACE+x} ]; then
        echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_TARGET_CONTEXT}"
        MISSING_NAME_SPACE_COUNT=$(($MISSING_NAME_SPACE_COUNT + 1))
    else
        # Configure K8S_TARGET_NAMESPACE
        K8S_TARGET_NAMESPACE=$K8S_NAMESPACE
    fi
fi
# Exit if K8S_SOURCE_NAMESPACE or K8S_TARGET_NAMESPACE not configured
if [ ${MISSING_NAME_SPACE_COUNT} -gt 0 ]; then
    echo "FAIL: Kubernetes namespace not configured for ${NAME} in ${K8S_SOURCE_CONTEXT} and/or ${K8S_TARGET_CONTEXT}, exiting"
    exit 1
fi

# If running locally, just exit 0
if [ $environment == "local" ]; then
    if [ ! -z ${SOURCE_PVC_LIST+x} ]; then
        if [ ! -z ${DELETE_SOURCE_PVCS+x} ]; then
            for i in ${SOURCE_PVC_LIST//,/ }; do
                echo "INFO: Running locally, skipping PVC cleanup of ${i}"
            done
        fi
    fi
    if [ ! -z ${TARGET_PVC_LIST+x} ]; then
        if [ ! -z ${DELETE_TARGET_PVCS+x} ]; then
            for i in ${TARGET_PVC_LIST//,/ }; do
                echo "INFO: Running locally, skipping PVC cleanup of ${i}"
            done
        fi
    fi
    exit 0
fi

# Take a list of PVCs, find the names in the list that end with a number and add matching names to a list
function find_pvcs_by_name() {
    local pvcs_list=$1
    local namespace=$2
    local context=$3
    local pvcs_output=""
    for i in ${pvcs_list//,/ }; do
        # Strip the number from the end of the PVC name
        pvc_name="${i%[0-9]}"
        # Find the PVCs that contain the same name as the base name of the PVC"
        pvcs_output="${pvcs_output} $(kubectl --context ${context} get pvc -n ${namespace} -o custom-columns='name:metadata.name' --no-headers | grep ${pvc_name})"
    done
    # Return pvcs_output as a comma-separated list
    echo "${pvcs_output// /,}"
}

# Take a list of PVCs and remove any that do not exist
function remove_invalid_pvcs() {
    local pvcs_list=$1
    local namespace=$2
    local context=$3
    local pvcs_output=""
    for pvc_name in ${pvcs_list//,/ }; do
        # Find the PVCs that exist"
        pvcs_output="${pvcs_output} $(kubectl --context ${context} get pvc -n ${namespace} -o custom-columns='name:metadata.name' --no-headers | grep ${pvc_name})"
    done
    # Return pvcs_output as a comma-separated list
    echo "${pvcs_output// /,}"
}

# If SOURCE_PVC_LIST is set, append find_pvcs_by_name to SOURCE_PVC_LIST
if [ ! -z ${SOURCE_PVC_LIST+x} ]; then
    SOURCE_PVC_LIST="${SOURCE_PVC_LIST},$(find_pvcs_by_name "${SOURCE_PVC_LIST}" "${K8S_SOURCE_NAMESPACE}" "${K8S_SOURCE_CONTEXT}")"
    SOURCE_PVC_LIST=$(remove_invalid_pvcs "${SOURCE_PVC_LIST}" "${K8S_SOURCE_NAMESPACE}" "${K8S_SOURCE_CONTEXT}")
fi

# If TARGET_PVC_LIST is set, append find_pvcs_by_name to TARGET_PVC_LIST
if [ ! -z ${TARGET_PVC_LIST+x} ]; then
    TARGET_PVC_LIST="${TARGET_PVC_LIST},$(find_pvcs_by_name "${TARGET_PVC_LIST}" "${K8S_TARGET_NAMESPACE}" "${K8S_TARGET_CONTEXT}")"
    TARGET_PVC_LIST=$(remove_invalid_pvcs "${TARGET_PVC_LIST}" "${K8S_TARGET_NAMESPACE}" "${K8S_TARGET_CONTEXT}")
fi

# Function to delete PVCs based on deployment or statefulset identified by kubernetes selector
delete_pvcs_by_selector() {
    # Delete SOURCE PVCs based on deployment or statefulset identified by kubernetes selector
    if [ ! -z ${DELETE_SOURCE_PVCS+x} ]; then
        echo "INFO: Deleting SOURCE PVC's by selector ${K8S_APP_LABEL_SELECTOR} in namespace ${K8S_SOURCE_NAMESPACE} and context ${K8S_SOURCE_CONTEXT}"
        local source_svc_list="$(kubectl get ${SERVICE_TYPE} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)"
        # If no source_svc_list then exit
        if [ -z "${source_svc_list}" ]; then
            echo "FAIL: No source_svc_list found for ${K8S_APP_LABEL_SELECTOR} in namespace ${K8S_SOURCE_NAMESPACE} and context ${K8S_SOURCE_CONTEXT}"
            exit 1
        fi
        echo "INFO: source_svc_list ${source_svc_list}"
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            echo "INFO: Processing source_svc_list ${line}"
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Execute delete by app
            delete_pvcs_by_app ${SERVICE_TYPE} ${svc} ${K8S_SOURCE_NAMESPACE} ${K8S_SOURCE_CONTEXT}
        done <<<"$source_svc_list"
    fi
    # Delete TARGET PVCs based on deployment or statefulset identified by kubernetes selector
    if [ ! -z ${DELETE_TARGET_PVCS+x} ]; then
        echo "INFO: Deleting TARGET PVC's by selector ${K8S_APP_LABEL_SELECTOR} in namespace ${K8S_TARGET_NAMESPACE} and context ${K8S_TARGET_CONTEXT}"
        local target_svc_list="$(kubectl get ${SERVICE_TYPE} --selector="${K8S_APP_LABEL_SELECTOR}" --namespace ${K8S_TARGET_NAMESPACE} --context=${K8S_TARGET_CONTEXT} -o custom-columns=name:metadata.name,replica:spec.replicas --no-headers=true)"
        # If no target_svc_list then exit
        if [ -z "${target_svc_list+x}" ]; then
            echo "FAIL: No target_svc_list found for ${K8S_APP_LABEL_SELECTOR} in namespace ${K8S_TARGET_NAMESPACE} and context ${K8S_TARGET_CONTEXT}"
            exit 1
        fi
        echo "INFO: target_svc_list: ${target_svc_list}"
        # Iterate through service list and perform actions
        while IFS= read -r line; do
            echo "INFO: Processing target_svc_list ${line}"
            # Extract service name
            local svc=$(echo ${line} | awk '{print $1}')
            # Execute delete by app
            delete_pvcs_by_app ${SERVICE_TYPE} ${svc} ${K8S_TARGET_NAMESPACE} ${K8S_TARGET_CONTEXT}
        done <<<"$target_svc_list"
    fi
    exit 0
}

# Function to delete PVCs based on deployment or statefulset name
delete_pvcs_by_app() {
    local service_type=$1
    local name=$2
    local namespace=$3
    local context=$4
    # Delete SOURCE PVCs based on deployment or statefulset name
    echo "INFO: Deleting PVC's by ${service_type} ${name} in namespace ${namespace} and context ${context}"
    # Get comma-separated selectors for resource
    local label_selectors="$(kubectl --namespace ${namespace} --context=${context} get ${service_type} ${name} -o json | jq -r '.spec.selector.matchLabels | to_entries | map("\(.key)=\(.value)") | join(",")')"
    # If no selectors, exit
    if [ -z ${label_selectors+x} ]; then
        echo "FAIL: No selectors found for ${service_type} ${name} in namespace ${namespace} and context ${context}"
        exit 1
    fi
    echo "INFO: Label Selectors ${label_selectors}"
    # Get pod names by selectors
    local pods="$(kubectl get pods -l "${label_selectors}" --namespace ${namespace} --context=${context} --no-headers -o custom-columns=":metadata.name")"
    # If no pods, return
    if [ -z ${pods+x} ]; then
        echo "FAIL: No pods found for ${service_type} ${name} in namespace ${namespace} and context ${context}"
        return
    fi
    echo "INFO: Pods ${pods}"
    # for each pod, delete PVCs
    local pvcs_to_delete=() # array of pvcs to delete
    for pod in ${pods}; do
        echo "INFO Processing pod: ${pod}"
        # Get pod's PVC names
        local pvcs="$(kubectl get pod --namespace ${namespace} --context=${context} ${pod} -o json | jq -r '.spec.volumes[] | select(.persistentVolumeClaim != null) | .persistentVolumeClaim.claimName')"
        # Add pvcs to deletion array
        echo "INFO: Adding PVC's to deletion array ${pvcs} for pod ${pod} in namespace ${namespace} and context ${context}"
        pvcs_to_delete+=(${pvcs})
    done

    if ((${#pvcs_to_delete[@]} > 0)); then
        # Delete PVCs
        echo "INFO: Deleting PVC's ${pvcs} for pod ${pod} in namespace ${namespace} and context ${context}"
        # If CACHE_PVCS_FOR_DELETION is set, then save $pvcs_to_delete to $PVC_DELETION_CACHE_FILE
        if [ ! -z ${CACHE_PVCS_FOR_DELETION+x} ]; then
            echo "INFO: Caching PVC's for deletion ${pvcs_to_delete[@]} to ${PVC_DELETION_CACHE_FILE}"
            # Ensure the PVC_DELETION_CACHE_FILE exists
            touch "${PVC_DELETION_CACHE_FILE}"
            printf " ${pvcs_to_delete[@]} " >>${PVC_DELETION_CACHE_FILE}
        else
            kubectl delete pvc --namespace ${namespace} --context=${context} ${pvcs_to_delete[@]} > >(tee -a ${LOGFILE}) 2> >(tee -a ${LOGFILE} >&2) &
        fi
    else
        # No PVCs to delete
        echo "INFO: No PVC's to delete for ${service_type} ${name}"
    fi
}

###############################################################################

# If PVC_DELETION_CACHE_FILE exists, then delete PVCs in $PVC_DELETION_CACHE_FILE and move $PVC_DELETION_CACHE_FILE to timestamped backup file, then exit
if [ -f "${PVC_DELETION_CACHE_FILE}" ]; then
    echo "INFO: PVC's found in ${PVC_DELETION_CACHE_FILE}"
    # Delete PVCs in $PVC_DELETION_CACHE_FILE
    kubectl delete pvc --namespace ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} $(cat ${PVC_DELETION_CACHE_FILE} | tr '\n' ' ') > >(tee -a ${LOGFILE}) 2> >(tee -a ${LOGFILE} >&2) &
    # Move $PVC_DELETION_CACHE_FILE to timestamped backup
    echo "INFO: Backing up ${PVC_DELETION_CACHE_FILE}"
    mv "${PVC_DELETION_CACHE_FILE}" "${PVC_DELETION_CACHE_FILE}_$(date +%Y%m%d%H%M%S)"
    # Exit successfully
    echo "INFO: PVC's deleted and list backed up, now exiting"
    exit 0
fi

# If K8S_APP_LABEL_SELECTOR is configured, then get list of PVCs based on selector
if [ ! -z ${K8S_APP_LABEL_SELECTOR+x} ]; then
    echo "INFO: Deleting PVCs by selector ${K8S_APP_LABEL_SELECTOR}"
    delete_pvcs_by_selector
    exit 0
fi

# Remove duplicates from comma-separated SOURCE_PVC_LIST and separate with spaces
if [ ! -z ${SOURCE_PVC_LIST+x} ]; then
    echo "INFO: Removing duplicates from comma-separated SOURCE_PVC_LIST: ${SOURCE_PVC_LIST}"
    SOURCE_PVC_LIST=$(echo "${SOURCE_PVC_LIST}" | tr ',' '\n' | sort -u | tr '\n' ' ')
fi

# Remove duplicates from comma-separated TARGET_PVC_LIST and separate with spaces
if [ ! -z ${TARGET_PVC_LIST+x} ]; then
    echo "INFO: Removing duplicates from comma-separated TARGET_PVC_LIST: ${TARGET_PVC_LIST}"
    TARGET_PVC_LIST=$(echo "${TARGET_PVC_LIST}" | tr ',' '\n' | sort -u | tr '\n' ' ')
fi

echo "INFO: PVC Cleanup Executing pvc-cleanup for ${NAME} with namespace ${K8S_SOURCE_NAMESPACE} and ${K8S_TARGET_NAMESPACE}"

if [ ! -z ${SOURCE_PVC_LIST+x} ]; then
    # Output timestamp to PVC_DELETION_ACTUAL_LOGFILE
    echo "INFO: $(date +%Y%m%d%H%M%S) PVC's to delete, ${SOURCE_PVC_LIST}" >>${PVC_DELETION_ACTUAL_LOGFILE}
    if [ ! -z ${DELETE_SOURCE_PVCS+x} ]; then
        echo "INFO: Cleaning up source PVC ${SOURCE_PVC_LIST}"
        # Run kubectl in the background and redirect output to logfile while output is being written to stdout and stderr
        kubectl -n ${K8S_SOURCE_NAMESPACE} --context=${K8S_SOURCE_CONTEXT} delete pvc "${SOURCE_PVC_LIST}" > >(tee -a ${LOGFILE}) 2> >(tee -a ${LOGFILE} >&2) &
    fi
fi
if [ ! -z ${TARGET_PVC_LIST+x} ]; then
    # Output timestamp to PVC_DELETION_ACTUAL_LOGFILE
    echo "INFO: $(date +%Y%m%d%H%M%S) PVC's to delete, ${TARGET_PVC_LIST}" >>${PVC_DELETION_ACTUAL_LOGFILE}
    if [ ! -z ${DELETE_TARGET_PVCS+x} ]; then
        echo "INFO: Cleaning up target PVC ${TARGET_PVC_LIST}"
        # Run kubectl in the background and redirect output to logfile while output is being written to stdout and stderr
        kubectl -n ${K8S_TARGET_NAMESPACE} --context=${K8S_TARGET_CONTEXT} delete pvc "${TARGET_PVC_LIST}" > >(tee -a ${LOGFILE}) 2> >(tee -a ${LOGFILE} >&2) &
    fi
fi

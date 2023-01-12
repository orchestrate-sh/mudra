#!/usr/bin/env bash
set -eux

NAME=$1
SLEEP_SECONDS=$2
NODE_ENV_FILE=$3

echo "INFO: Executing kubectl wait script for ${WAIT_FOR_K8S_APP} on behalf of ${NAME}"

# Source common.sh
readonly ROOT_DIR="$(cd "$(dirname "${0}")" && pwd)"
source "${ROOT_DIR}/../common.sh" || exit 1

# Source the node env file
source ".meta/${NODE_ENV_FILE}.env"

# Force login to k8s on AWS
# kubectl --namespace alfa auth can-i get pod --quiet || true

# If running locally, just exit 0
if [ $environment == "local" ]; then
    echo "WARN: Running locally, exiting"
    exit 0
fi

###############################################################################

# Kubectl wait for deployment to be ready

function wait_for_app {
    local app_name=${1}
    local app_type=${2}
    local app_namespace=${3}
    local app_context=${4}
    local retry_count=${5:33} # default retry count to 33
    
    echo "INFO: Executing kubectl wait script for ${app_name} on behalf of ${NAME}"
    while true; do
        # Get the app's replica count, or empty if none
        app_replicas=$(kubectl get ${app_type} ${app_name} --namespace ${app_namespace} --context=${app_context} -o json | jq -r '.status.replicas // empty')
        # Get the app's number of ready replicas, or empty if none
        app_ready_replicas=$(kubectl get ${app_type} ${app_name} --namespace ${app_namespace} --context=${app_context} -o json | jq -r '.status.readyReplicas // empty')
        # If we have the app's replica and ready replica counts
        if [[ ! -z ${app_replicas} && ! -z ${app_ready_replicas} ]]; then
            # If all of the app's replicas are ready
            if [ ${app_ready_replicas} -eq ${app_replicas} ]; then
                echo "INFO: ${app_type} ${app_name} is ready"
                break
            fi
        fi
        echo "INFO: Waiting for ${app_type} ${app_name} to be ready"
        # If retry_count is 0, then exit with error
        if [ ${retry_count} -eq 0 ]; then
            echo "FAIL: ${app_type} ${app_name} is not ready after ${retry_count} retries"
            exit 1
        fi
        # Increment retry count
        retry_count=$(($retry_count - 1))
        # Sleep for a bit
        sleep 5
    done
}

# The index of current app iteration
current_app_idx=1
# The name of the current app iteration
declare current_app_name=WAIT_FOR_K8S_APP_${current_app_idx}
# Loop through apps until there is no declared variable for the current index
while [ ! -z ${!current_app_name:-} ]; do
    # Declare the type, namespace and retry count for the current app iteration
    declare current_app_type=WAIT_FOR_K8S_APP_TYPE_${current_app_idx}
    declare current_app_namespace=WAIT_FOR_K8S_APP_NAMESPACE_${current_app_idx}
    declare current_app_retry_count=WAIT_FOR_K8S_APP_RETRY_COUNT_${current_app_idx}
    # Wait for the current app to be ready
    wait_for_app ${!current_app_name} ${!current_app_type} ${!current_app_namespace} ${K8S_TARGET_CONTEXT} ${!current_app_retry_count:-}
    # Increment the index
    current_app_idx=$((current_app_idx+1))
    # Update the app name for the next iteration
    declare current_app_name=WAIT_FOR_K8S_APP_${current_app_idx}
done

#!/bin/bash
NAME=$1
SLEEP_SECONDS=$2
NODE_ENV_FILE=$3

# Source common.sh
readonly ROOT_DIR="$(cd "$(dirname "${0}")" && pwd)"
source "${ROOT_DIR}/../common.sh" || exit 1

# Source the node env file
source ".meta/${NODE_ENV_FILE}.env"

# Force login to k8s on AWS
# kubectl --namespace alfa auth can-i get pod --quiet || true

echo "INFO: Stop script for ${NAME} running..."
sleep $SLEEP_SECONDS
echo "INFO: Successful."

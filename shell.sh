#!/usr/bin/env bash

# Force login to k8s on AWS
# kubectl --namespace alfa auth can-i get pod --quiet || true

[[ ":$PATH:" != *":/root/.local/bin:"* ]] && PATH="/root/.local/bin:${PATH}"

pipenv shell

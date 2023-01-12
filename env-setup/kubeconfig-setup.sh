#!/usr/bin/env bash

# Reference: https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/

# Configure clusters
# kubectl --kubeconfig=k8s-config config unset clusters.<name>
kubectl config --kubeconfig=k8s-config set-cluster development-aws --server=https://1.2.3.4 --certificate-authority=fake-ca-file
kubectl config --kubeconfig=k8s-config set-cluster development-gcp --server=https://1.2.3.4 --certificate-authority=fake-ca-file
kubectl config --kubeconfig=k8s-config set-cluster staging-aws --server=https://5.6.7.8 --insecure-skip-tls-verify
kubectl config --kubeconfig=k8s-config set-cluster staging-gcp --server=https://5.6.7.8 --insecure-skip-tls-verify
kubectl config --kubeconfig=k8s-config set-cluster local-1 --server=https://9.1.0.1 --insecure-skip-tls-verify
kubectl config --kubeconfig=k8s-config set-cluster local-2 --server=https://9.1.0.1 --insecure-skip-tls-verify

# Configure Users
# kubectl --kubeconfig=k8s-config config unset users.<name>
kubectl config --kubeconfig=k8s-config set-credentials developer --client-certificate=fake-cert-file --client-key=fake-key-seefile
kubectl config --kubeconfig=k8s-config set-credentials mudra --username=exp --password=some-password

# Configure contexts
# kubectl --kubeconfig=k8s-config config unset contexts.<name>
kubectl config --kubeconfig=k8s-config set-context dev-aws --cluster=development-aws --namespace=frontend --user=mudra
kubectl config --kubeconfig=k8s-config set-context dev-gcp --cluster=development-gcp --namespace=frontend --user=mudra
kubectl config --kubeconfig=k8s-config set-context stg-aws --cluster=staging-aws --namespace=frontend --user=mudra
kubectl config --kubeconfig=k8s-config set-context stg-gcp --cluster=staging-gcp --namespace=frontend --user=mudra
kubectl config --kubeconfig=k8s-config set-context lcl-1-app1 --cluster=local-1 --namespace=app1 --user=developer
kubectl config --kubeconfig=k8s-config set-context lcl-2-app1 --cluster=local-2 --namespace=app1 --user=developer
kubectl config --kubeconfig=k8s-config set-context lcl-1-app2 --cluster=local-1 --namespace=app2 --user=developer
kubectl config --kubeconfig=k8s-config set-context lcl-2-app2 --cluster=local-2 --namespace=app2 --user=developer
kubectl config --kubeconfig=k8s-config set-context lcl-1-app3 --cluster=local-1 --namespace=app3 --user=developer
kubectl config --kubeconfig=k8s-config set-context lcl-2-app3 --cluster=local-2 --namespace=app3 --user=developer
#!/usr/bin/env bash

# Install python3 (3.8) and pipenv
sudo apt-get -y update
echo 'export PATH="${HOME}/.local/bin:$PATH"' >> ~/.bashrc
sudo apt-get -y install python3-pip
python3 -m pip install --user pipenv

# Install Docker
sudo apt-get -y remove docker docker-engine docker.io containerd runc
sudo apt-get -y update
sudo apt-get -y install \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get -y update
sudo apt-get -y install docker-ce docker-ce-cli containerd.io
sudo apt-get -y install docker-ce docker-ce-cli containerd.io
sudo docker run hello-world

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod a+x kubectl
sudo mv kubectl /usr/local/bin/kubectl
kubectl version --client

# kubeconfig
#./kubeconfig-setup.sh

# metrics
./metrics-setup.sh
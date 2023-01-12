#!/usr/bin/env bash
set -eux

apt -y update
apt -y install python3-pip jq
pip3 install --user pipenv

# Install python (if not already installed)
FILE=/usr/local/bin/python3.8
if ! test -f "$FILE"; then
  apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libsqlite3-dev libreadline-dev libffi-dev curl libbz2-dev
  curl -O https://www.python.org/ftp/python/3.8.2/Python-3.8.2.tar.xz
  tar -xf Python-3.8.2.tar.xz
  cd Python-3.8.2
  ./configure --enable-optimizations
  make -j 4
  make altinstall
fi

# Add pipenv to path
[[ ":$PATH:" != *":/root/.local/bin:"* ]] && PATH="/root/.local/bin:${PATH}"

mk_cd_external_repo_dir() {
  # Make dir external_migration_repos one level up from the update.sh's location.
  local EXT_DIR="external_migration_repos"
  cd ${ORCHESTRA_PATH}
  cd ..
  mkdir -p ${EXT_DIR}
  cd ${EXT_DIR}
}

CWD=$(pwd)
ORCHESTRA_PATH=$(dirname $(realpath "$0"))
mk_cd_external_repo_dir
cd $CWD

git pull
pipenv install

source .cluster-env

#!/usr/bin/env bash
Help()
{
  echo "Pull and run the Pushgateway and optionally Prometheus services."
  echo
  echo "Syntax: metrics-setup.sh [-h|p]"
  echo "options:"
  echo "h  Prints this help."
  echo "p  Gets and run the prometheus-2.28.1.linux-amd64.tar.gz."
  echo
}

Prometheus()
{
  PROMETHEUS_ZIP=prometheus-2.28.1.linux-amd64.tar.gz
  if [ ! -f prometheus-2.28.1.linux-amd64/prometheus ]; then
    if [ ! -f $PROMETHEUS_ZIP ]; then
      curl https://github.com/prometheus/prometheus/releases/download/v2.28.1/prometheus-2.28.1.linux-amd64.tar.gz -L -o $PROMETHEUS_ZIP
    fi
    tar xzf $PROMETHEUS_ZIP
  fi
  config_path=$(dirname $0)/prometheus/prometheus.yml
  if [ -f $config_path ]; then
    prometheus-2.28.1.linux-amd64/prometheus --config.file $config_path &
    echo "Prometheus." 
  else
    echo "Config file not found."
    echo $config_path
    exit 1
  fi
}

# Remove existing pushgateway (always return success)
docker rm -f $(docker ps -a | grep pushgateway | awk '{ print $1 }') | :
docker pull prom/pushgateway
docker run -d -p 9091:9091 prom/pushgateway

while getopts hp option; do
  case $option in
    h) # display Help
      Help
      exit;;
    p) # install prometheus
      Prometheus;;
  esac   
done

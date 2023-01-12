# Prometheus POC (WIP)

The node can send metrics to Promethus by using the Pushgateway service.

Test:

- Start Pushgateway service.
  
  `docker run -d -p 9091:9091 prom/pushgateway`

- Start Prometheus (configured to scrape the Pushgateway service)
  
  `../../prometheus-2.28.1.linux-amd64/prometheus --config.file=/path/to/config/prometheus.yml`

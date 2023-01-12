import time
from prometheus_client import Counter, CollectorRegistry, push_to_gateway

if __name__ == '__main__':
    registry = CollectorRegistry()
    c = Counter('my_failures', 'Description of counter', registry=registry)
    # c.inc()     # Increment by 1
    # Start up the server to expose the metrics.
    # start_http_server(8000)
    # Generate some requests.
    while True:
        c.inc(20.5)  # Increment by given value
        push_to_gateway('localhost:9091', job='batchA', registry=registry)
        break

# Example Orchestration Plan

- [Example Orchestration Plan](#example-orchestration-plan)
  - [Pre Cut-Over Activities](#pre-cut-over-activities)
  - [Orchestration Cutover Execution](#orchestration-cutover-execution)
    - [Phase 0](#phase-0)
      - [Pre-flight checks - database, topics, services](#pre-flight-checks---database-topics-services)
      - [Check preflight results](#check-preflight-results)
      - [Scale Down All services on GCP](#scale-down-all-services-on-gcp)
    - [Phase 1](#phase-1)
      - [Show the list of phase 1 services, topics, databases](#show-the-list-of-phase-1-services-topics-databases)
      - [Execute Phase 1 Orchestration](#execute-phase-1-orchestration)
      - [Validate Phase 1](#validate-phase-1)
        - [Check sql tasks (from pipenv shell)](#check-sql-tasks-from-pipenv-shell)
    - [Phase 2](#phase-2)
      - [Show the list of phase 2 services, topics, databases](#show-the-list-of-phase-2-services-topics-databases)
      - [Execute Phase 2 Orchestration](#execute-phase-2-orchestration)
      - [Account for special cases like assets and inventory](#account-for-special-cases-like-assets-and-inventory)
      - [Check service migration status (check app logs)](#check-service-migration-status-check-app-logs)
      - [Re-run phase 2 service migration for failed services](#re-run-phase-2-service-migration-for-failed-services)
      - [Cut over phase 2 databases - only for databases associated with phase2 services, some special cases might apply (assets and inventory)](#cut-over-phase-2-databases---only-for-databases-associated-with-phase2-services-some-special-cases-might-apply-assets-and-inventory)
      - [Check phase 2 db migration status (check database logs)](#check-phase-2-db-migration-status-check-database-logs)
      - [Re-run db migration for failed cutover database](#re-run-db-migration-for-failed-cutover-database)
      - [Cut over DNS for phase 2 services - I expect this will be manual tomorrow](#cut-over-dns-for-phase-2-services---i-expect-this-will-be-manual-tomorrow)
    - [Phase 3](#phase-3)
      - [Show the list of phase 3 services, topics, databases](#show-the-list-of-phase-3-services-topics-databases)
      - [Execute Phase 3 Orchestration](#execute-phase-3-orchestration)
      - [Swap \& Cut over phase 3 databases](#swap--cut-over-phase-3-databases)
      - [Check phase 3 db migration status](#check-phase-3-db-migration-status)
      - [Cut over DNS for phase 3 services](#cut-over-dns-for-phase-3-services)
    - [Phase 4](#phase-4)
      - [Show the list of phase 4 services, topics, databases](#show-the-list-of-phase-4-services-topics-databases)
      - [Execute Phase 4 Orchestration](#execute-phase-4-orchestration)
      - [Swap \& Cut over phase 4 databases](#swap--cut-over-phase-4-databases)
      - [Check phase 4 db migration status](#check-phase-4-db-migration-status)
      - [phase 4 DNS cutover](#phase-4-dns-cutover)
    - [Phase 5](#phase-5)
      - [Show the list of phase 5 services, topics, databases, buckets](#show-the-list-of-phase-5-services-topics-databases-buckets)
      - [Execute Phase 5 Orchestration](#execute-phase-5-orchestration)
      - [Swap \& Cut over phase 5 databases](#swap--cut-over-phase-5-databases)
      - [Check db migration status](#check-db-migration-status)
      - [Final DNS cutover](#final-dns-cutover)
      - [Clean up databases (cutover)](#clean-up-databases-cutover)
  - [Rollback Activities](#rollback-activities)
    - [Scale down all services on GCP](#scale-down-all-services-on-gcp-1)
    - [Scale AWS back to original](#scale-aws-back-to-original)
    - [Un-swap databases](#un-swap-databases)
    - [Clean up databases (rollback)](#clean-up-databases-rollback)
    - [Scale all services on GCP to targets](#scale-all-services-on-gcp-to-targets)

## Pre Cut-Over Activities

1. Start a root shell:

    ```bash
    sudo -i
    ```

2. Change to orchestration directory:

    ```bash
    cd /root/orchestration
    ```

3. Checkout master branch:

    ```bash
    git checkout master
    ```

4. Get latest updates:

    ```bash
    git pull
    ./update.sh
    ```

5. Reset logging and tracking for orchestration:

    ```bash
    rm -rf logs/ && rm -rf .meta && rm -rf /tmp/mudra && mkdir /tmp/mudra
    ```

6. Set the `MUDRA_ENVIRONMENT` environment variable to the environment to be migrated

    ```bash
    export MUDRA_ENVIRONMENT=<migration environment>
    ```

## Orchestration Cutover Execution

### Phase 0

#### Pre-flight checks - database, topics, services

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Kafka --preflight --maxworkers 10
```

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --preflight --skipnodes data-key-service-db --maxworkers 10
```

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --preflight --maxworkers 10
```

#### Check preflight results

List nodes that failed preflight:

```bash
grep "failed preflight" logs/mudra.log
ls -la logs/failed_preflight
```

Tail all App node logs that failed preflight:

```bash
for app in logs/failed_preflight/App_*; do tail logs/node_logs/App/${app#logs/failed_preflight/App_}-preflight.log; done
```

Tail all Kafka node logs that failed preflight:

```bash
for kafka in logs/failed_preflight/Kafka_*; do tail logs/node_logs/Kafka/${kafka#logs/failed_preflight/Kafka_}-check.log; done
```

Tail all Database node logs that failed preflight:

```bash
for database in logs/failed_preflight/Database_*; do tail logs/node_logs/Database/${database#logs/failed_preflight/Database_}-preflight.log; done
```

#### Scale Down All services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force
```

### Phase 1

#### Show the list of phase 1 services, topics, databases

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="1" type=App --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="1" type=Database --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="1" type=Kafka --maxworkers 10
```

#### Execute Phase 1 Orchestration

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --phase 1 --maxworkers 10
```

#### Validate Phase 1

##### Check sql tasks (from pipenv shell)

```bash
./interface.sh --datafiles orchestration_datafiles --environment ${MUDRA_ENVIRONMENT} database status --phase 1 && column -t -s"," /tmp/mudra/rds/db_status.csv
```

### Phase 2

#### Show the list of phase 2 services, topics, databases

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="2" type=App --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="2" type=Database --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="2" type=Kafka --maxworkers 10
```

#### Execute Phase 2 Orchestration

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --phase 2 --maxworkers 10
```

#### Account for special cases like assets and inventory

#### Check service migration status (check app logs)

#### Re-run phase 2 service migration for failed services

#### Cut over phase 2 databases - only for databases associated with phase2 services, some special cases might apply (assets and inventory)

> This happens automatically at the end of Phase 2

#### Check phase 2 db migration status (check database logs)

> To check the task states of sql migration: `./interface.sh --datafiles orchestration_datafiles --environment ${MUDRA_ENVIRONMENT} database status --phase 2 && column -t -s"," /tmp/mudra/rds/db_status.csv`

#### Re-run db migration for failed cutover database

#### Cut over DNS for phase 2 services - I expect this will be manual tomorrow

### Phase 3

#### Show the list of phase 3 services, topics, databases

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="3" type=App --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="3" type=Database --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="3" type=Kafka --maxworkers 10
```

#### Execute Phase 3 Orchestration

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --phase 3 --maxworkers 10
```

#### Swap & Cut over phase 3 databases

> This happens automatically at the end of Phase 3

#### Check phase 3 db migration status

#### Cut over DNS for phase 3 services

### Phase 4

#### Show the list of phase 4 services, topics, databases

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="4" type=App --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="4" type=Database --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="4" type=Kafka --maxworkers 10
```

#### Execute Phase 4 Orchestration

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --phase 4 --maxworkers 10
```

#### Swap & Cut over phase 4 databases

> This happens automatically at the end of Phase 4

#### Check phase 4 db migration status

#### phase 4 DNS cutover

### Phase 5

#### Show the list of phase 5 services, topics, databases, buckets

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="5" type=App --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="5" type=Database --maxworkers 10
```

```bash
./orchestrate.sh --datafiles orchestration_datafiles --gettree phase="5" type=Kafka --maxworkers 10
```

#### Execute Phase 5 Orchestration

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --phase 5 --maxworkers 10
```

#### Swap & Cut over phase 5 databases

> This happens automatically at the end of Phase 5

#### Check db migration status

#### Final DNS cutover

#### Clean up databases (cutover)

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action cleanup --maxworkers 10 --force
```

## Rollback Activities

### Scale down all services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force
```

### Scale AWS back to original

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action rollbacksource --maxworkers 10 --force
```

### Un-swap databases

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action unswap --maxworkers 10 --force
```

### Clean up databases (rollback)

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action cleanup --maxworkers 10 --force
```

### Scale all services on GCP to targets

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletarget --maxworkers 10 --force
```

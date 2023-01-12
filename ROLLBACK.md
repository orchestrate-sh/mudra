# Example Rollback

- [Example Rollback](#example-rollback)
  - [Phase 1 Rollback](#phase-1-rollback)
    - [Phase 1 Complete Rollback](#phase-1-complete-rollback)
  - [Phase 2 Rollback](#phase-2-rollback)
    - [Phase 2 Stage Rollback](#phase-2-stage-rollback)
      - [Scale down all Phase 2 services on GCP](#scale-down-all-phase-2-services-on-gcp)
    - [Un-swap Phase 2 databases](#un-swap-phase-2-databases)
    - [Cleanup Phase 2 databases](#cleanup-phase-2-databases)
    - [Phase 2 Complete Rollback](#phase-2-complete-rollback)
  - [Phase 3 Rollback](#phase-3-rollback)
    - [Phase 3 Stage Rollback](#phase-3-stage-rollback)
      - [Scale down all Phase 3 services on GCP](#scale-down-all-phase-3-services-on-gcp)
    - [Un-swap Phase 3 databases](#un-swap-phase-3-databases)
    - [Cleanup Phase 3 databases](#cleanup-phase-3-databases)
    - [Phase 3 Complete Rollback](#phase-3-complete-rollback)
  - [Phase 4 Rollback](#phase-4-rollback)
    - [Phase 4 Stage Rollback](#phase-4-stage-rollback)
      - [Scale down all Phase 4 services on GCP](#scale-down-all-phase-4-services-on-gcp)
    - [Un-swap Phase 4 databases](#un-swap-phase-4-databases)
    - [Cleanup Phase 4 databases](#cleanup-phase-4-databases)
    - [Phase 4 Complete Rollback](#phase-4-complete-rollback)
  - [Phase 5 Rollback](#phase-5-rollback)
    - [Phase 5 Stage Rollback](#phase-5-stage-rollback)
      - [Scale down all Phase 5 services on GCP](#scale-down-all-phase-5-services-on-gcp)
    - [Un-swap Phase 5 databases](#un-swap-phase-5-databases)
    - [Un-cutover Phase 5 databases](#un-cutover-phase-5-databases)
    - [Phase 5 Complete Rollback](#phase-5-complete-rollback)
  - [Complete Rollback](#complete-rollback)
    - [Scale Down All Services on GCP](#scale-down-all-services-on-gcp)
    - [Scale AWS Back to Original](#scale-aws-back-to-original)
    - [Switch Kafka to Un-mirrored Cluster](#switch-kafka-to-un-mirrored-cluster)
    - [Un-swap Databases](#un-swap-databases)
    - [Cleanup Databases](#cleanup-databases)
    - [Scale All Services on GCP to Targets](#scale-all-services-on-gcp-to-targets)

## Phase 1 Rollback

These are the steps to perform a rollback of just `Phase 1` to the previous phase.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

### Phase 1 Complete Rollback

These are the steps to perform a rollback of `Phase 1` back to a clean environment.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

## Phase 2 Rollback

### Phase 2 Stage Rollback

These are the steps to perform a rollback of just `Phase 2` to the previous phase.

#### Scale down all Phase 2 services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force --phase 2
```

### Un-swap Phase 2 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(unswap)` to the top of the `preswap` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action preswap --maxworkers 10 --phase 2
```

### Cleanup Phase 2 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(cleanup)` to the top of the `precutover` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action precutover --maxworkers 10 --phase 2
```

### Phase 2 Complete Rollback

These are the steps to perform a rollback of `Phase 2` back to a clean environment.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

## Phase 3 Rollback

### Phase 3 Stage Rollback

These are the steps to perform a rollback of just `Phase 3` to the previous phase.

#### Scale down all Phase 3 services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force --phase 3
```

### Un-swap Phase 3 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(unswap)` to the top of the `preswap` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action preswap --maxworkers 10 --phase 3
```

### Cleanup Phase 3 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(cleanup)` to the top of the `precutover` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action precutover --maxworkers 10 --phase 3
```

### Phase 3 Complete Rollback

These are the steps to perform a rollback of `Phase 3` back to a clean environment.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

## Phase 4 Rollback

### Phase 4 Stage Rollback

These are the steps to perform a rollback of just `Phase 4` to the previous phase.

#### Scale down all Phase 4 services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force --phase 4
```

### Un-swap Phase 4 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(unswap)` to the top of the `preswap` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action preswap --maxworkers 10 --phase 4
```

### Cleanup Phase 4 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(cleanup)` to the top of the `precutover` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action precutover --maxworkers 10 --phase 4
```

### Phase 4 Complete Rollback

These are the steps to perform a rollback of `Phase 4` back to a clean environment.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

## Phase 5 Rollback

### Phase 5 Stage Rollback

These are the steps to perform a rollback of just `Phase 5` to the previous phase.

#### Scale down all Phase 5 services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force --phase 5
```

### Un-swap Phase 5 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(unswap)` to the top of the `preswap` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action preswap --maxworkers 10 --phase 5
```

### Un-cutover Phase 5 databases

1. Edit `node_interfaces/Database.py` and add `ctx.forward(cleanup)` to the top of the `precutover` method.
2. Execute the following command to swap databases:

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action precutover --maxworkers 10 --phase 5
```

### Phase 5 Complete Rollback

These are the steps to perform a rollback of `Phase 5` back to a clean environment.

Refer to [Complete Rollback](#complete-rollback) for complete rollback steps.

## Complete Rollback

### Scale Down All Services on GCP

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletargetdown --maxworkers 10 --force
```

### Scale AWS Back to Original

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action rollbacksource --maxworkers 10 --force
```

### Switch Kafka to Un-mirrored Cluster

### Un-swap Databases

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --node data-key-service-db --action unswap-dks --maxworkers 10 --force
```

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action unswap --maxworkers 10 --force
```

### Cleanup Databases

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype Database --action cleanup --maxworkers 10 --force
```

### Scale All Services on GCP to Targets

```bash
./orchestrate.sh --environment ${MUDRA_ENVIRONMENT} --datafiles orchestration_datafiles --nodetype App --action scaletarget --maxworkers 10 --force
```

# Multi-Region Failover Procedures

This document outlines the architecture and constraints for handling a primary region (e.g. `us-east-1`) failure. A network partition or zone failure will result in infrastructure timeouts and dropped communication. 

## 1. Failover Capabilities

When a region degrades, you may use the `failover` action specifying the `target_region` (e.g., `us-west-2`). **Not all services support failover.** 

| Service | Supports Failover? | Details & Constraints |
|---|---|---|
| `api-gateway` | **YES** | us-west-2 standby available, stateless, safe to switch. |
| `cdn-service` | **YES** | us-west-2 standby available, stateless, safe to switch. |
| `order-service` | **YES** | us-west-2 standby available, 30-second data lag acceptable. |
| `redis-cache` | **YES** | us-west-2 standby available, cache can be natively rebuilt. |
| `postgres-primary` | **NO** | Replication lag detected. Failover will induce Split-Brain risk. |
| `payment-service` | **NO** | PCI-DSS Compliance dictates single-region requirement. |

## 2. Split-Brain Risk
A split-brain scenario occurs if a secondary database is promoted while the primary is still accepting writes in a partitioned network, or if the secondary has not received the latest sync. **Never failover a primary database during an active partition unless explicitly directed by a Database Administrator.** Doing so guarantees data consistency violations.

## 3. Compliance Constraints
Due to Payment Card Industry Data Security Standard (PCI-DSS) regulations, our `payment-service` endpoints are restricted to specific audited regions. Attempting to failover the `payment-service` into an unauthorized region is a critical compliance violation.

## 4. Required Escalation
For any services that **cannot** be failed over automatically, you must use the `alert_oncall` action referencing the specific down services (e.g., `payment`, `postgres`, `database`) to engage the infrastructure and DBA teams for manual recovery.

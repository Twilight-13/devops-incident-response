# Runbook: Database Connection Pool Exhaustion

## Symptoms
- `HikariPool - Connection is not available, request timed out` in logs
- `Connection pool exhausted (max=N, active=N, waiting=M)` in logs
- Very high P99 latency (10–60 seconds) on the affected service
- High CPU from thread pool saturation
- Downstream services timing out and opening circuit breakers

## Diagnosis Steps
1. Check logs of the slow service for HikariCP / connection pool errors
2. Check metrics: P99 latency will be extremely high (>10s)
3. Check if a recent deployment occurred (new version = likely cause)
4. Trace the cascade: which upstream service triggered downstream failures?

## Root Cause
Connection pool exhaustion occurs when:
- A new deployment introduced a connection leak (connections not returned to pool)
- A slow query is holding connections open longer than expected
- Pool size is misconfigured for current load

## Remediation

**If caused by a bad deployment (most common):**
Rollback the service to the previous known-good version.

```
action: rollback
service: <affected-service>
version: <previous-version>
```

**If not deployment-related:**
Restart the service to clear the pool, then investigate query performance.

## Do NOT
- Restart downstream services first (they are victims, not the cause)
- Ignore the cascade — fix the root service, not the symptoms

## Recovery
After rollback, downstream circuit breakers will reset within 30–60 seconds.

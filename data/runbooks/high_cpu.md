# Runbook: High CPU

## Symptoms
- CPU > 80% sustained for more than 5 minutes
- Increased latency as threads compete for CPU cycles
- Possible OOM if CPU contention causes GC pressure

## Common Causes
1. **Batch job running** — check if CPU spike is scheduled (e.g., email sends, report generation)
2. **Traffic spike** — check request rate metrics
3. **Infinite loop / CPU leak** — check for runaway threads in logs
4. **GC pressure** — look for GC log entries alongside high CPU

## Remediation
- If batch job: no action needed, wait for completion
- If traffic spike: scale_up the service
- If CPU leak / bad code: rollback to previous version

## Important
High CPU on a service that is otherwise healthy (error_rate=0, P99 normal)
is almost always a scheduled batch job. Do NOT restart it unnecessarily.

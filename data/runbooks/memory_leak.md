# Runbook: Memory Leak / OOMKilled

## Symptoms
- Pod restarting repeatedly with reason `OOMKilled`
- Memory usage > 90% in metrics
- `java.lang.OutOfMemoryError: Java heap space` in logs
- GC overhead limit exceeded warnings before crash

## Diagnosis Steps
1. Check memory metrics: `read_metrics <service>`
2. Check logs for OOM errors: `read_logs <service>`
3. Confirm restart loop in alerts (OOMKilled N times in M minutes)

## Root Cause
The service has a memory leak — objects are allocated but not released,
causing heap exhaustion and JVM crash. This can also occur if the pod's
memory limit is set too low for the current load.

## Remediation
**Immediate fix:** Restart the affected service. This clears the heap
and restores service. The pod will start fresh.

```
action: restart_service
service: <affected-service>
```

**After restart:** Monitor memory over the next 30 minutes. If memory
climbs again rapidly, escalate to the service team for a heap dump analysis.

## Do NOT
- Restart other healthy services (collateral damage)
- Scale up replicas (all new pods will also OOM)

## Expected Recovery Time
2–5 minutes after restart.

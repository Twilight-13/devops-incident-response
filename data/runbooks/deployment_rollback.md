# Runbook: Deployment Rollback

## When to Rollback
- Error rate spike immediately following a deployment
- Latency increase correlated with a new version going live
- A service was recently deployed (`last_deployed` within the last hour)
- Logs show errors that did not exist before the deployment

## How to Identify the Bad Deployment
1. Check `current_version` and `last_deployed` in service metrics
2. Correlate the deployment timestamp with the incident start time
3. Read the service logs — new errors after deployment = likely cause

## Remediation

```
action: rollback
service: <service-that-was-deployed>
version: <previous-stable-version>
```

If you don't know the exact previous version, use `previous` and the
system will revert to the last known-good artifact.

## Post-Rollback
- Monitor error rate for 5 minutes to confirm recovery
- Downstream services should recover automatically as upstream stabilises
- Alert the owning team so they can investigate the bad release

## Do NOT
- Rollback services that were NOT recently deployed
- Rollback before confirming the new deployment is actually the cause
- Restart services instead of rolling back (restart keeps the bad version)

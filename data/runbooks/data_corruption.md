# Runbook: Silent Data Corruption

## What Makes This Hard
Silent data corruption does NOT trigger standard error-rate or latency alerts.
All services appear healthy. The signal is in business-logic metrics:
- Price mismatches in validation logs (WARN level, not ERROR)
- Anomalous average order values in analytics
- Write operations succeeding (HTTP 200) but writing wrong values

## How to Detect
1. Read logs for price-validation-service — look for PRICE_MISMATCH warnings
2. Read metrics for analytics-service — look for avg_order_value anomalies
3. Read logs for data-pipeline-service — check for recent deployment
4. Correlate: did the mismatch rate spike immediately after a pipeline deployment?

## Root Cause Pattern
A data pipeline deployment introduced a bug that writes incorrect values
to the product catalog. Writes succeed at the DB level (no errors),
but the values are wrong (e.g., decimal point off by 10x).

## Remediation — Two Steps Required

### Step 1: Stop the corruption
Rollback the pipeline service to stop new corrupt writes.

```
action: rollback
service: data-pipeline-service
version: previous
```

### Step 2: Audit existing corrupt data
Rollback stops NEW corruption but does NOT fix data already written.
You MUST page the data engineering team to run a correction job.

```
action: alert_oncall
reason: Data corruption detected — price-validation mismatch rate 15%. 
        Pipeline rolled back. Need audit and correction of product-catalog prices.
```

## Do NOT
- Restart services (won't fix written data)
- Scale up services (more replicas = more corrupt writes)
- Close the incident after rollback only — corrupted data persists until corrected

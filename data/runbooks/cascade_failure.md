# Runbook: Cascading Service Failure

## Pattern
Service A fails → Service B times out calling A → Service C sees errors from B.
Alerts fire on B and C (downstream victims), NOT on A (the root cause).

## How to Find the Root Cause
1. Map the dependency chain: which service does the failing service call?
2. The root cause is the DEEPEST failing service in the chain
3. Look for the service with the most recent deployment OR the highest internal error rate

## Signals
- Circuit breakers opening in downstream services (log: "Circuit breaker OPEN for X")
- Upstream timeout errors (log: "call to X timed out")
- The root service will have high P99 latency or error rate itself

## Remediation
Fix the root cause service ONLY. Downstream services will recover automatically
once the upstream is healthy. Do not restart downstream victims.

## Anti-patterns to Avoid
- Restarting B and C when A is broken — they will fail again immediately
- Scaling up victims — more replicas of a broken caller doesn't help
- Treating all alerts as equal — alerts on downstream services are symptoms

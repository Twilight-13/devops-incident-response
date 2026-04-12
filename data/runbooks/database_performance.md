# Database Performance Degradation

This runbook outlines the recommended procedure for handling database performance issues, specifically focusing on slow queries, high CPU caused by sequential table scans, and missing query indexes.

## 1. Diagnose Database Load
If the database (`postgres-primary`) is exhibiting high CPU or degraded performance without actual service crashes, use the `read_metrics` action on the database.
- Look at the `Sequential scans/min`. 
- If this value is massively elevated (e.g. 500+ instead of single digits), it means queries are scanning entire tables instead of looking up rows in an index.

## 2. Check Slow Query Logs
Use `read_logs` on the database to verify the slow queries.
- Slow query logs will identify specific query strings taking >1000ms.
- They will likely append `[seq_scan]` indicating they hit the table sequentially.
- The logs may also include automated schema anomaly warnings, such as "MISSING INDEX DETECTED".

## 3. Resolving Missing Indexes
If a missing index is detected, it is highly likely that a recent schema migration added a field but forgot the index.
- **Action Option 1:** Use the `create_index` action, specifying the target `table` and `column` (e.g. `table="orders"`, `column="user_segment"`). This is the best approach if the data is already deployed, as it fixes the issue instantly without breaking backend code.
- **Action Option 2:** Use the `rollback` action on the database service. This will revert the schema migration. It fixes the performance, but causes downstream code applying to the new schema to error until patched. 

## 4. What NOT to do
- Do **NOT** `restart_service`. Connection pool exhaustion is a symptom, not the cause. Restarting only temporarily drops connections before being immediately overwhelmed again.
- Do **NOT** `scale_up`. Adding more replicas/workers will only hammer the slow database harder, increasing lock contention and further starving the CPU.

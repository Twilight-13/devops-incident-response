# Thundering Herd Runbook

## Overview
A thundering herd occurs when a large number of processes simultaneously attempt to access
a resource that was previously cached or unavailable. This runbook covers how thundering
herds happen during cache node removal, how to mitigate them, and how to safely restore
cache infrastructure.

---

## What Is a Thundering Herd?

In distributed systems, a **thundering herd** happens when:
1. A shared resource (cache, rate limiter, connection pool) becomes unavailable
2. All clients simultaneously fall through to the underlying system
3. The underlying system cannot handle the sudden full load
4. The underlying system degrades, causing cascading failures

### The Cache Stampede (most common variant):
- Normal: 95% of requests served by cache (e.g., Redis) → only 5% hit the database
- Cache removed: 100% of requests hit the database simultaneously
- Database connection pool exhausts immediately
- Query timeouts cause app servers to retry → further amplifying load

---

## Why Simultaneous Cache Removal Causes Thundering Herds

When cache nodes are removed **gradually** (e.g., one node at a time with a 5-minute wait):
- Cache hit rate drops incrementally (95% → 80% → 60%...)
- Database load increases gradually, allowing it to scale or absorb the change
- Engineers can observe the impact and abort if needed

When cache nodes are removed **simultaneously**:
- Cache hit rate drops from 100% to 0% in milliseconds
- Every app server, on every request, misses cache and queries the database
- The database receives N × (1/cache_hit_rate) times its normal load instantly
- At typical hit rates (90%+), this is a 10× sudden load spike

---

## Diagnosing a Thundering Herd

### Signs:
- Cache hit rate drops to 0% (alerts from Redis/Memcached)
- Immediate database CPU spike (not gradual)
- Database connection pool exhausted messages in logs
- All app servers reporting DB query timeouts simultaneously
- The timing correlates with a cache node removal or cache flush

### Diagnostic steps:
1. Check Redis/cache cluster logs — look for node removals or flushes
2. Check database logs — look for sudden query rate spikes (e.g., 28× normal)
3. Check app server logs — look for simultaneous "connection refused" from DB
4. Check infrastructure logs — look for automation tasks that removed cache nodes

---

## Mitigation Strategy

### Immediate response (in order):
1. **Scale up the database first** — expand connection pool capacity, add read replicas
2. **Restore cache nodes** — do NOT restart all at once (they'll be cold, thundering herd again)
3. **Implement cache warming** — pre-populate the cache before directing full traffic to it

> ⚠️ **Do NOT restore cache nodes before scaling the database.**
> Cold cache nodes + full traffic = same thundering herd.

### Connection pool emergency expansion:
```bash
# Vitess: increase connection pool temporarily
vtctldclient --server localhost:15999 SetMaxNumRowsToScanForQuery \
  --max_connections 1000 keyspace/-
```

---

## Safe Cache Node Removal Procedure

### Gradual removal (correct approach):
```
Step 1: Remove 1 node → Monitor DB load for 5 minutes
Step 2: If DB load stable, remove 1 more node → Monitor 5 minutes
Step 3: Repeat until target node count reached
```

### Minimum time between node removals:
- At 3 cache nodes: 10 minutes between each removal
- At 10+ cache nodes: 5 minutes between each removal
- Always: abort if DB connection pool utilization exceeds 70%

---

## Cache Warming Strategies

Before re-enabling full traffic to a cold cache:

### Option 1: Read-through warming
- Route 5% of traffic to cold cache
- Let it warm naturally as requests are made
- Gradually increase traffic percentage over 15-30 minutes

### Option 2: Pre-populate from database
```python
# Fetch hot keys from DB and pre-load into cache
hot_keys = db.query("SELECT key, value FROM cache_table WHERE access_count > 1000")
for key, value in hot_keys:
    redis.set(key, value, ex=3600)
```

### Option 3: Snapshot restore
- If you have a recent Redis snapshot (RDB file), restore it to the new nodes
- This gives immediate partial hit rate from the snapshot's timestamp

---

## Post-mortem Checklist
- [ ] Root cause confirmed (simultaneous removal? cache flush? TTL expiry?)
- [ ] Database capacity restored to normal
- [ ] Cache nodes restored and warmed
- [ ] Gradual removal procedure documented and enforced in runbook
- [ ] Monitoring alert added: "cache hit rate drops >20% in 60 seconds"

---

## Real-World Reference
**Slack Outage — February 22, 2022**
- Cause: Simultaneous removal of multiple Vitess connection cache nodes
- Impact: Thundering herd on Vitess primary cluster, 67% query failure rate
- Duration: Several hours of degraded service
- Fix: Restored cache nodes, scaled Vitess cluster
- Post-mortem: https://slack.engineering/slacks-incident-on-2-22-22/

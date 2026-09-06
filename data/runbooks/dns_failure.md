# DNS Failure Runbook

## Overview
DNS failures can be some of the most catastrophic production incidents because nearly every
service depends on name resolution. This runbook covers diagnosing DNS failures,
understanding the difference between authoritative and caching nameservers, and safe
recovery procedures.

---

## Authoritative vs. Caching Nameservers

**Authoritative nameserver** (`named` / BIND authoritative mode):
- Holds the canonical zone file (the source of truth for all DNS records)
- Receives zone transfer requests from caching nameservers
- Must be restarted after any IP or zone configuration change

**Caching nameserver** (`unbound`, `named` caching mode):
- Serves DNS queries to clients (app servers, api-gateways, etc.)
- Caches records from the authoritative server for the configured TTL
- **Must also be restarted** after the authoritative nameserver receives a new zone

> ⚠️ **Critical**: Restarting only the authoritative nameserver is NOT sufficient. The
> caching nameserver will continue serving stale or conflicting records until it is also
> restarted and performs a fresh zone transfer.

---

## Diagnosing a DNS Failure

### Signs of DNS failure:
- Widespread `NXDOMAIN` responses for previously-working hostnames
- Services failing to connect to upstream dependencies
- Logs showing "DNS resolution failed" or "connection refused" to `.internal` domains
- API gateways showing high error rates immediately after a config change

### Step-by-step diagnosis:
1. Check the caching nameserver logs first — it serves all app queries
2. Check the authoritative nameserver logs for zone transfer status
3. Look for recent Puppet runs or nameserver restarts in the deployment log
4. Check whether both nameservers were restarted or only one

---

## Danger: Re-deploying During a DNS Incident

> ⛔ **NEVER run a deploy during an active DNS incident.**

Deployment scripts commonly:
- Call internal APIs to fetch configuration
- Look up service endpoints via DNS
- Write zone files using data fetched over DNS

If DNS is broken, a deploy will:
1. Fail to resolve its own configuration endpoint
2. Proceed with null/empty data
3. Write a corrupt or empty zone file, making the situation worse

**Real example (GitHub DNS outage, Jan 2016):**
The zone-rebuild script called an internal API at `zone-manager.internal` → DNS returned NXDOMAIN
→ zone rebuild wrote an empty zone → 847 records began returning NXDOMAIN.

---

## Recovery Procedure

### Immediate mitigation:
1. **DO NOT re-deploy** until DNS is restored
2. Restart the **caching nameserver** (not just the authoritative one)
3. Verify zone transfer succeeds from authoritative → caching
4. Check that DNS resolution works: `dig payment.internal @<caching-nameserver-ip>`

### Prevent recurrence:
1. Rollback the Puppet manifest that caused the incorrect restart sequence
2. Update the manifest to restart BOTH nameservers in the correct order:
   - Step 1: Update and restart authoritative nameserver
   - Step 2: Wait for zone transfer confirmation
   - Step 3: Restart caching nameserver
3. Add automated smoke tests after nameserver restarts

### Safe nameserver restart sequence:
```bash
# 1. Restart authoritative nameserver
systemctl restart named-authoritative
# 2. Verify zone is healthy
named-checkzone internal /etc/named/zones/internal.db
# 3. Wait for zone transfer
sleep 5
# 4. Restart caching nameserver
systemctl restart unbound
# 5. Verify resolution works
dig +short payment.internal
```

---

## Post-mortem Checklist
- [ ] Root cause identified (which nameserver was skipped?)
- [ ] Puppet manifest rolled back or fixed
- [ ] Zone file integrity verified
- [ ] All NXDOMAIN alerts cleared
- [ ] Deploy runbooks updated with "DNS health check before deploy" gate

# Security Incident Response

This runbook outlines the recommended procedure for handling suspected security incidents, particularly Distributed Denial of Service (DDoS) and automated credential stuffing attacks.

## 1. Identify the Attack
Not all traffic spikes are legitimate user traffic. Distinguish between a spike and an attack:
- **Traffic Spike:** Sustained increase across multiple endpoints, proportional to user growth or a marketing event.
- **DDoS/Botnet Attack:** Extreme spikes (e.g. 10x-100x normal baseline) often originating from a single IP range or targeting a single endpoint (like `/api/v1/login`).

## 2. Reading Access Logs
Investigate the `api-gateway` logs to identify malicious patterns:
- Check for high volume requests returning 429 (Rate Limited) or 401/403.
- Identify common IP subnets. E.g. `185.x.x.x` appearing thousands of times per second.
- Check downstream `auth-service` logs for failed logins with `NULL` user IDs or recycled passwords (Credential Stuffing).

## 3. Mitigation Strategies
Rate Limiters are effective against single-IP actors but often fail against distributed botnets because the attack is spread across thousands of distinct IPs within a rented subnet.
- **DO NOT** restart services. This will only temporarily clear connection pools before being immediately overwhelmed again.
- **DO NOT** rollback. This is an external attack, not a bad deployment.
- **DO:** Apply a firewall block to the offending IP range (CIDR format). Example: `185.220.0.0/16`.

## 4. Escalation
**CRITICAL:** Always alert the security team for any attacks (`alert_oncall` with a reason mentioning 'security' or 'ddos'). Mitigation alone is not enough; the security operations center (SOC) must investigate potential data exfiltration and apply network-level web application firewall (WAF) rules.

# WAF CPU Exhaustion Runbook

## Overview
WAF (Web Application Firewall) rules can cause catastrophic CPU exhaustion if they contain
poorly written regular expressions. A single bad rule can take an entire edge tier offline
within seconds. This runbook covers identifying catastrophic regex backtracking, why restarting
won't fix it, and the correct rollback procedure.

---

## Understanding Catastrophic Regex Backtracking (ReDoS)

Regular expression engines use backtracking to find matches. Most regexes are fast, but
certain patterns can cause **exponential backtracking** (ReDoS — Regular Expression Denial of Service).

**Dangerous patterns:**
- `(a+)+` — nested quantifiers
- `(a|aa)+` — alternation with overlap
- `(.*a)+` — greedy wildcard with repetition

**Example from Cloudflare 2019 outage:**
```
Pattern: ^(a+)+$
Input:   aaaaaaaaaaaab
```
The regex engine tries every possible grouping of the `a` characters before concluding no match,
causing **exponential time complexity**. On a string of length N, this takes O(2^N) steps.

**Impact:** A single URL with ~20 matching characters will peg one CPU core at 100% indefinitely.

---

## Diagnosing WAF CPU Exhaustion

### Signs:
- CPU spike immediately after WAF rule deployment
- CPU goes to 100% and stays there (not a transient spike)
- High request latency at the edge, but origin servers are healthy
- Timing correlates exactly with a rule deployment event

### Diagnostic steps:
1. Check WAF service logs for recent rule deployments
2. Check CPU metrics on WAF service — sustained 100% is the signature
3. Look for log entries mentioning specific rule IDs or regex patterns
4. Check the rule manager logs for fast-track or staging-skipped deployments

---

## Why Restarting the WAF Does NOT Fix This

> ⚠️ **Critical misconception**: Many engineers instinctively restart the affected service.
> For WAF CPU exhaustion, this does NOT work.

When the WAF service restarts:
1. It loads its rule configuration on startup
2. The bad rule is still in the active rule-set
3. The first HTTP request triggers the catastrophic backtracking again
4. CPU returns to 100% within seconds

**Restarting is a waste of precious time during an active outage.**

---

## WAF Rule Deployment Best Practices

### Before deploying any WAF rule:
1. **Static analysis**: Check for nested quantifiers, alternation overlap, greedy wildcards
2. **Staging test**: Deploy to a staging environment that mirrors production traffic patterns
3. **Canary deployment**: Deploy to 1% of production traffic, monitor CPU for 5 minutes
4. **Rate limits on deployment**: No fast-tracking security rules to 100% of production

### Testing for ReDoS risk:
```python
import re, time, signal

def test_redos(pattern, test_input, timeout_sec=2):
    """Returns True if pattern is safe, False if it appears vulnerable."""
    def handler(signum, frame):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout_sec)
    try:
        re.match(pattern, test_input)
        signal.alarm(0)
        return True
    except TimeoutError:
        return False

# Test the dangerous Cloudflare pattern:
test_redos(r'^(a+)+$', 'a' * 20 + 'b')  # Should return False (vulnerable)
```

---

## Recovery Procedure

### Immediate mitigation (DO NOT restart first):
1. **Rollback the WAF rule-set** to the last known-good version
2. Specify the exact version if available (e.g., `v2.4.0`)
3. Verify CPU drops below 50% within 30 seconds of rollback
4. Confirm edge nodes begin processing requests normally

### Rollback command example:
```bash
# Roll back to previous rule-set
waf-rule-manager rollback --version v2.4.0
# Verify CPU normalized
kubectl top pods -l app=waf-service
```

### After incident:
1. Pull the offending rule from all environments
2. Static-analyze the regex: identify the backtracking path
3. Fix the regex or replace with a non-backtracking equivalent
4. Add the test case to the WAF test suite
5. Update deployment policy: no fast-tracking WAF rules to production

---

## Real-World Reference
**Cloudflare Global Outage — July 2, 2019**
- Pattern: `(?:(?:\"|'|\]|\}|\\|\d|(?:nan|infinity|true|false|null|undefined|symbol|math)|\`|\-|\+)+[)]*;?((?:\s|-|~|!|\{\}|\|\||\+)*.*(?:.*=.*)))`
- Impact: 27 minutes of global downtime, ~100% CPU across all 180 PoPs worldwide
- Fix: Rollback to previous rule-set within 27 minutes
- Post-mortem: https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/

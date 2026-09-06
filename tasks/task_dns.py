from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

# Based on real GitHub DNS Outage (January 2016)
# Post-mortem: https://github.blog/news-insights/the-library/dns-outage-post-mortem/
# A Puppet manifest bug restarted only the authoritative nameserver (not the caching one).
# A follow-up re-deploy corrupted the zone file further because the zone rebuild
# script depended on DNS itself — which was already broken.

INCIDENT_TIME = "2016-01-28T09:14:22Z"

DEPENDENCIES = [
    {"service": "api-gateway",       "calls": ["dns-caching"],          "called_by": []},
    {"service": "dns-caching",       "calls": ["dns-authoritative"],    "called_by": ["api-gateway"]},
    {"service": "dns-authoritative", "calls": [],                       "called_by": ["dns-caching", "deploy-service"]},
    {"service": "deploy-service",    "calls": ["dns-authoritative"],    "called_by": []},
    {"service": "puppet-master",     "calls": [],                       "called_by": []},
]

DNS_AUTH_LOGS = [
    "[09:14:22] INFO  Puppet run started: nameserver-ip-update manifest",
    "[09:14:45] INFO  Restarting authoritative nameserver... done",
    "[09:14:46] WARN  Caching nameserver NOT restarted (not in manifest scope)",
    "[09:14:47] INFO  Zone transfer initiated to caching nameserver",
    "[09:14:52] ERROR Zone transfer failed: caching nameserver has no new config",
    "[09:15:01] ERROR deploy-service called zone-rebuild API during incident",
    "[09:15:03] ERROR zone-rebuild API made DNS query → got NXDOMAIN → built corrupt zone",
    "[09:15:04] FATAL Zone file now corrupt: 847 records returning NXDOMAIN",
]

DNS_CACHING_LOGS = [
    "[09:14:22] INFO  Serving cached zone: last updated 09:00:00",
    "[09:14:47] WARN  Zone transfer attempted from authoritative — rejected (version mismatch)",
    "[09:14:50] WARN  Continuing to serve stale zone (30+ minutes old)",
    "[09:14:55] ERROR api-gateway queries failing: NXDOMAIN for payment.internal",
    "[09:14:57] ERROR api-gateway queries failing: NXDOMAIN for orders.internal",
    "[09:15:10] CRIT  847 DNS queries/min returning NXDOMAIN — zone corrupted",
]

DEPLOY_SERVICE_LOGS = [
    "[09:15:00] INFO  Attempting re-deploy to fix DNS issue",
    "[09:15:02] INFO  Calling zone-rebuild API at zone-manager.internal",
    "[09:15:03] ERROR DNS resolution failed for zone-manager.internal: NXDOMAIN",
    "[09:15:03] WARN  Zone rebuild called with null zone data — wrote empty zone",
    "[09:15:04] CRIT  Zone rebuild made situation worse — do not re-deploy",
]

PUPPET_LOGS = [
    "[09:14:22] INFO  Puppet agent run triggered: nameserver-ip-update",
    "[09:14:45] INFO  Resource File[/etc/named.conf] updated",
    "[09:14:45] INFO  Service[named-authoritative] restarted",
    "[09:14:46] INFO  Puppet run completed successfully",
    "[09:14:46] WARN  Note: named-caching.service not in manifest — skipped",
]

API_GATEWAY_LOGS = [
    "[09:14:53] WARN  DNS lookup failed: payment.internal → NXDOMAIN",
    "[09:14:54] WARN  DNS lookup failed: orders.internal → NXDOMAIN",
    "[09:14:55] ERROR 94% of service-discovery lookups returning NXDOMAIN",
    "[09:14:56] CRIT  Upstream services unreachable — DNS failure cascade",
]


class DnsTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "dns-authoritative": DNS_AUTH_LOGS[:],
            "dns-caching":       DNS_CACHING_LOGS[:],
            "deploy-service":    DEPLOY_SERVICE_LOGS[:],
            "puppet-master":     PUPPET_LOGS[:],
            "api-gateway":       API_GATEWAY_LOGS[:],
        }

        services: Dict[str, dict] = {
            "dns-authoritative": {
                "name": "dns-authoritative", "status": "down",
                "cpu_percent": 12.0, "memory_percent": 88.0,
                "error_rate": 847.0, "latency_p99_ms": 0.0,
                "replicas_running": 0, "replicas_desired": 1,
                "current_version": "bind-9.11.3-puppet-r142",
                "last_deployed": "2016-01-28T09:14:45Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "dns-caching": {
                "name": "dns-caching", "status": "degraded",
                "cpu_percent": 45.0, "memory_percent": 62.0,
                "error_rate": 94.0, "latency_p99_ms": 5200.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "unbound-1.5.8",
                "last_deployed": "2016-01-10T00:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "puppet-master": {
                "name": "puppet-master", "status": "healthy",
                "cpu_percent": 22.0, "memory_percent": 35.0,
                "error_rate": 0.0, "latency_p99_ms": 120.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "puppet-4.3.2-r142",
                "last_deployed": "2016-01-28T09:14:22Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "api-gateway": {
                "name": "api-gateway", "status": "down",
                "cpu_percent": 18.0, "memory_percent": 41.0,
                "error_rate": 94.0, "latency_p99_ms": 30000.0,
                "replicas_running": 0, "replicas_desired": 5,
                "current_version": "v2.4.0",
                "last_deployed": "2016-01-20T08:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "deploy-service": {
                "name": "deploy-service", "status": "degraded",
                "cpu_percent": 33.0, "memory_percent": 28.0,
                "error_rate": 12.0, "latency_p99_ms": 8000.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v1.8.0",
                "last_deployed": "2016-01-28T09:15:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "A001", "severity": "critical", "service": "api-gateway",
                "message": "94% DNS queries returning NXDOMAIN — services unreachable",
                "timestamp": "2016-01-28T09:14:55Z", "acknowledged": False,
            },
            {
                "id": "A002", "severity": "critical", "service": "dns-authoritative",
                "message": "Zone file corrupted — 847 records returning NXDOMAIN",
                "timestamp": "2016-01-28T09:15:04Z", "acknowledged": False,
            },
            {
                "id": "A003", "severity": "warning", "service": "dns-caching",
                "message": "Serving stale zone — zone transfer rejected (version mismatch)",
                "timestamp": "2016-01-28T09:14:47Z", "acknowledged": False,
            },
            {
                "id": "A004", "severity": "info", "service": "puppet-master",
                "message": "Puppet run completed successfully (manifest bug already applied)",
                "timestamp": "2016-01-28T09:14:46Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()),
            task_id="dns",
            step=0,
            max_steps=20,
            services=services,
            alerts=alerts,
            logs=logs,
            action_history=[],
            total_reward=0.0,
            incident_resolved=False,
            ground_truth_root_cause="puppet_manifest_bug_restarted_wrong_nameserver_corrupt_dns_zone",
            ground_truth_fix="restart dns-caching nameserver AND rollback puppet manifest",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["puppet-master"],
            service_dependencies=DEPENDENCIES,
        )
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        state.step += 1
        state._apply_sla_degradation()
        at = action.action_type
        svc = action.service or ""
        reward = 0.0
        done = False
        info: Dict[str, Any] = {}

        result_text, error_text = self._apply_action_to_logs(state, action)

        # --- Information-gathering rewards ---
        gather_map = {
            ("read_logs",   "dns-authoritative"): ("rl_dns_auth",  0.10),
            ("search_logs", "dns-authoritative"): ("rl_dns_auth",  0.10),
            ("read_logs",   "dns-caching"):        ("rl_dns_cache", 0.10),
            ("search_logs", "dns-caching"):        ("rl_dns_cache", 0.10),
            ("read_logs",   "deploy-service"):     ("rl_deploy",    0.05),
            ("search_logs", "deploy-service"):     ("rl_deploy",    0.05),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r
                state.rewards_given.add(tag)

        if at == ActionType.READ_RUNBOOK:
            if "runbook" not in state.rewards_given:
                reward += 0.05
                state.rewards_given.add("runbook")

        # --- Diagnose ---
        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            dns_keywords = ["puppet", "manifest", "nameserver", "dns", "zone", "nxdomain", "caching", "corrupt"]
            if semantic_match(rc, dns_keywords, threshold=1):
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20
                    state.rewards_given.add("diagnose_correct")
            result_text = f"Diagnosis recorded: {rc}"

        # --- Fix 1: Restart dns-caching (primary fix — restarts with new config) ---
        if at == ActionType.RESTART_SERVICE and svc == "dns-caching":
            blind_penalty = self._penalty_blind_remediation(state, action, "fix_cache_restart")
            reward += blind_penalty
            if "fix_cache_restart" not in state.rewards_given:
                reward += 0.25
                state.rewards_given.add("fix_cache_restart")
                state.services["dns-caching"]["status"] = "healthy"
                state.services["dns-caching"]["error_rate"] = 0.0
                state.services["dns-caching"]["latency_p99_ms"] = 5.0
                state.services["api-gateway"]["error_rate"] = 0.0
                state.services["api-gateway"]["status"] = "healthy"
                state.services["api-gateway"]["replicas_running"] = 5
                state.alerts = [a for a in state.alerts if a["id"] not in ("A002", "A003")]
                result_text = (
                    "dns-caching restarted. Loaded fresh config from authoritative nameserver. "
                    "Zone transfer successful. DNS resolution restored. "
                    "api-gateway recovering — NXDOMAIN rate dropping."
                )
                if "fix_puppet_rollback" in state.rewards_given:
                    state.incident_resolved = True
                    done = True
                    info["resolution"] = "incident_resolved"

        # --- Fix 2: Rollback puppet-master (prevents recurrence) ---
        if at == ActionType.ROLLBACK and svc == "puppet-master":
            if "fix_puppet_rollback" not in state.rewards_given:
                reward += 0.15
                state.rewards_given.add("fix_puppet_rollback")
                state.services["puppet-master"]["current_version"] = "puppet-4.3.2-r141"
                result_text = (
                    "Puppet manifest rolled back to r141. "
                    "The nameserver-ip-update manifest has been reverted. "
                    "Future Puppet runs will restart both authoritative AND caching nameservers."
                )
                if "fix_cache_restart" in state.rewards_given:
                    state.incident_resolved = True
                    done = True
                    info["resolution"] = "incident_resolved"

        # --- Penalty: Running deploy-service makes it worse ---
        if at == ActionType.RESTART_SERVICE and svc == "deploy-service":
            reward -= 0.20
            result_text = (
                "CRITICAL: Re-running deploy-service triggered another zone rebuild attempt. "
                "zone-rebuild API made DNS query → got NXDOMAIN → zone corruption worsened. "
                "DO NOT re-deploy during a DNS incident — the deploy script depends on DNS."
            )

        # Penalty: restarting healthy puppet-master without diagnosis
        if at == ActionType.RESTART_SERVICE and svc == "puppet-master":
            reward -= 0.05
            result_text = "puppet-master restarted. The manifest bug is still present — use rollback instead."

        # Penalty: collateral damage on healthy services
        if at == ActionType.RESTART_SERVICE and svc in state.healthy_services:
            reward -= 0.10
            error_text = f"Collateral damage: {svc} was healthy. Unnecessary restart."

        if at == ActionType.NOOP and state.step > 4:
            reward -= 0.04

        if at in (ActionType.BLOCK_IP_RANGE, ActionType.CREATE_INDEX, ActionType.FAILOVER):
            reward -= 0.10
            error_text = f"Action {at.value} is not applicable to a DNS configuration incident."

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True
            info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

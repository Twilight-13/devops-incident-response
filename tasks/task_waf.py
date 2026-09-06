from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

# Based on real Cloudflare Global Outage (July 2, 2019)
# Post-mortem: https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/
# A single WAF rule with a catastrophically backtracking regex ('^(a+)+$')
# was fast-tracked to production without staging testing. CPU exhaustion
# across all edge nodes caused ~27 minutes of global downtime.

INCIDENT_TIME = "2019-07-02T14:02:15Z"

DEPENDENCIES = [
    {"service": "waf-service",      "calls": [],              "called_by": ["edge-node-us", "edge-node-eu"]},
    {"service": "edge-node-us",     "calls": ["waf-service", "origin-api"], "called_by": []},
    {"service": "edge-node-eu",     "calls": ["waf-service", "origin-api"], "called_by": []},
    {"service": "origin-api",       "calls": [],              "called_by": ["edge-node-us", "edge-node-eu"]},
    {"service": "waf-rule-manager", "calls": ["waf-service"], "called_by": []},
]

WAF_SERVICE_LOGS = [
    "[14:02:15] INFO  WAF rule deployment: rule-set v2.4.1 applied (47 rules)",
    "[14:02:16] INFO  New rule SIG-2019-07-02: pattern='^(a+)+$' applied to URI matching",
    "[14:02:17] WARN  CPU spike detected: 45% → 78% immediately after rule deployment",
    "[14:02:20] ERROR CPU at 98% — regex engine backtracking on URI: /api/search?q=aaaaaaaaab",
    "[14:02:21] ERROR Rule SIG-2019-07-02 triggering catastrophic backtracking",
    "[14:02:22] FATAL CPU 100% — all worker threads blocked in regex evaluation",
    "[14:02:23] FATAL Dropping 100% of incoming requests — WAF unresponsive",
]

EDGE_US_LOGS = [
    "[14:02:18] WARN  WAF processing time: avg 4200ms (was 12ms pre-deployment)",
    "[14:02:20] ERROR Requests timing out waiting for WAF verdict",
    "[14:02:22] ERROR Error rate: 87% — WAF saturation",
    "[14:02:24] CRIT  All requests being dropped — circuit breaker open",
]

EDGE_EU_LOGS = [
    "[14:02:18] WARN  WAF processing time: avg 4700ms (was 11ms pre-deployment)",
    "[14:02:20] ERROR Requests timing out waiting for WAF verdict (EU edge)",
    "[14:02:21] ERROR Error rate: 91% — WAF saturation",
    "[14:02:23] CRIT  All requests being dropped — circuit breaker open",
]

WAF_RULE_MANAGER_LOGS = [
    "[14:02:15] INFO  Deployed rule-set v2.4.1 to production (fast-track, no staging test)",
    "[14:02:15] INFO  New rule SIG-2019-07-02 added: ReDoS risk not evaluated",
    "[14:02:17] WARN  CPU spike on waf-service detected post-deploy",
    "[14:02:20] INFO  Previous rule-set v2.4.0 available for rollback",
]

ORIGIN_API_LOGS = [
    "[14:02:15] INFO  Healthy — serving 4200 req/s at avg 28ms",
    "[14:02:23] WARN  Incoming request rate dropped: 4200 → 0 req/s",
    "[14:02:24] INFO  No requests reaching origin — edge layer saturated by WAF",
]


class WafTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "waf-service":       WAF_SERVICE_LOGS[:],
            "edge-node-us":      EDGE_US_LOGS[:],
            "edge-node-eu":      EDGE_EU_LOGS[:],
            "waf-rule-manager":  WAF_RULE_MANAGER_LOGS[:],
            "origin-api":        ORIGIN_API_LOGS[:],
        }

        services: Dict[str, dict] = {
            "waf-service": {
                "name": "waf-service", "status": "down",
                "cpu_percent": 100.0, "memory_percent": 55.0,
                "error_rate": 100.0, "latency_p99_ms": 0.0,
                "replicas_running": 0, "replicas_desired": 12,
                "current_version": "rule-set-v2.4.1",
                "last_deployed": "2019-07-02T14:02:15Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "edge-node-us": {
                "name": "edge-node-us", "status": "degraded",
                "cpu_percent": 97.0, "memory_percent": 70.0,
                "error_rate": 87.0, "latency_p99_ms": 4200.0,
                "replicas_running": 8, "replicas_desired": 8,
                "current_version": "v5.1.0",
                "last_deployed": "2019-06-28T10:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "edge-node-eu": {
                "name": "edge-node-eu", "status": "degraded",
                "cpu_percent": 98.0, "memory_percent": 72.0,
                "error_rate": 91.0, "latency_p99_ms": 4700.0,
                "replicas_running": 6, "replicas_desired": 6,
                "current_version": "v5.1.0",
                "last_deployed": "2019-06-28T10:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "origin-api": {
                "name": "origin-api", "status": "healthy",
                "cpu_percent": 12.0, "memory_percent": 28.0,
                "error_rate": 0.0, "latency_p99_ms": 28.0,
                "replicas_running": 10, "replicas_desired": 10,
                "current_version": "v4.0.2",
                "last_deployed": "2019-07-01T06:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "waf-rule-manager": {
                "name": "waf-rule-manager", "status": "healthy",
                "cpu_percent": 8.0, "memory_percent": 15.0,
                "error_rate": 0.0, "latency_p99_ms": 35.0,
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "rule-set-v2.4.1",
                "last_deployed": "2019-07-02T14:02:15Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "A001", "severity": "critical", "service": "waf-service",
                "message": "CPU 100% sustained — all request processing halted (regex backtracking)",
                "timestamp": "2019-07-02T14:02:22Z", "acknowledged": False,
            },
            {
                "id": "A002", "severity": "critical", "service": "edge-node-us",
                "message": "87% request error rate — WAF unresponsive",
                "timestamp": "2019-07-02T14:02:22Z", "acknowledged": False,
            },
            {
                "id": "A003", "severity": "critical", "service": "edge-node-eu",
                "message": "91% request error rate — WAF unresponsive",
                "timestamp": "2019-07-02T14:02:23Z", "acknowledged": False,
            },
            {
                "id": "A004", "severity": "warning", "service": "waf-rule-manager",
                "message": "Rule deployment v2.4.1 correlates with CPU spike — rollback available",
                "timestamp": "2019-07-02T14:02:17Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()),
            task_id="waf",
            step=0,
            max_steps=18,
            services=services,
            alerts=alerts,
            logs=logs,
            action_history=[],
            total_reward=0.0,
            incident_resolved=False,
            ground_truth_root_cause="malformed_waf_regex_rule_cpu_exhaustion_excessive_backtracking",
            ground_truth_fix="rollback waf-rule-manager to previous rule set",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["origin-api", "waf-rule-manager"],
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
            ("read_logs",    "waf-service"):      ("rl_waf",     0.10),
            ("search_logs",  "waf-service"):      ("rl_waf",     0.10),
            ("read_logs",    "waf-rule-manager"): ("rl_wafmgr",  0.10),
            ("search_logs",  "waf-rule-manager"): ("rl_wafmgr",  0.10),
            ("read_metrics", "waf-service"):      ("rm_waf",     0.05),
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
            waf_keywords = ["regex", "waf", "rule", "backtrack", "cpu", "pattern", "redos", "sig-2019", "exhaustion"]
            if semantic_match(rc, waf_keywords, threshold=1):
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20
                    state.rewards_given.add("diagnose_correct")
            result_text = f"Diagnosis recorded: {rc}"

        # --- Correct fix: Rollback waf-rule-manager ---
        if at == ActionType.ROLLBACK and svc == "waf-rule-manager":
            blind_penalty = self._penalty_blind_remediation(state, action, "fix_rollback")
            reward += blind_penalty
            if "fix_rollback" not in state.rewards_given:
                reward += 0.35
                state.rewards_given.add("fix_rollback")
                # Bonus for specifying the correct rollback version
                version = (action.version or "").lower()
                if "v2.4.0" in version or "previous" in version:
                    if "bonus_version" not in state.rewards_given:
                        reward += 0.15
                        state.rewards_given.add("bonus_version")
                # Apply the fix
                state.services["waf-service"]["status"] = "healthy"
                state.services["waf-service"]["cpu_percent"] = 38.0
                state.services["waf-service"]["error_rate"] = 0.0
                state.services["waf-service"]["latency_p99_ms"] = 12.0
                state.services["waf-service"]["replicas_running"] = 12
                state.services["edge-node-us"]["status"] = "healthy"
                state.services["edge-node-us"]["error_rate"] = 0.0
                state.services["edge-node-eu"]["status"] = "healthy"
                state.services["edge-node-eu"]["error_rate"] = 0.0
                state.services["waf-rule-manager"]["current_version"] = "rule-set-v2.4.0"
                state.alerts = []
                state.incident_resolved = True
                done = True
                info["resolution"] = "incident_resolved"
                result_text = (
                    "WAF rule-set rolled back to v2.4.0. "
                    "SIG-2019-07-02 (catastrophic backtracking regex) removed. "
                    "CPU normalized: 100% → 38%. All edge nodes recovering. "
                    "Request processing resumed globally."
                )

        # --- Penalty: Restarting waf-service won't fix it — rule reloads on start ---
        if at == ActionType.RESTART_SERVICE and svc == "waf-service":
            reward -= 0.15
            result_text = (
                "waf-service restarted — but the bad WAF rule is still in rule-set v2.4.1. "
                "Restarting reloads the same rule configuration. CPU immediately hit 100% again. "
                "Restart does not fix a bad regex rule — you must rollback the rule-set."
            )

        # Penalty: scaling up edge nodes with same bad rule = same problem
        if at == ActionType.RESTART_SERVICE and svc in ("edge-node-us", "edge-node-eu"):
            reward -= 0.10
            result_text = f"{svc}: New nodes joined but inherited the same WAF rule-set v2.4.1. CPU still 100%."

        # Penalty: collateral damage
        if at == ActionType.RESTART_SERVICE and svc in state.healthy_services:
            reward -= 0.10
            error_text = f"Collateral damage: {svc} was healthy. Unnecessary restart."

        if at == ActionType.NOOP and state.step > 3:
            reward -= 0.04

        if at in (ActionType.BLOCK_IP_RANGE, ActionType.CREATE_INDEX, ActionType.FAILOVER):
            reward -= 0.10
            error_text = f"Action {at.value} is not applicable to a WAF CPU exhaustion incident."

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True
            info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

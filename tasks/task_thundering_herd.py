from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

# Based on real Slack February 2022 Outage
# Post-mortem: https://slack.engineering/slacks-incident-on-2-22-22/
# Infrastructure team removed all Redis cache nodes simultaneously for cost optimization.
# This caused a thundering herd: every app server missed cache and hit Vitess directly.
# Connection pool exhaustion on Vitess primary caused 67% query failure rate.

INCIDENT_TIME = "2022-02-22T16:45:00Z"

DEPENDENCIES = [
    {"service": "app-server-pool",   "calls": ["redis-cluster", "vitess-primary"], "called_by": []},
    {"service": "vitess-primary",    "calls": [],               "called_by": ["app-server-pool", "vitess-replica-1"]},
    {"service": "vitess-replica-1",  "calls": ["vitess-primary"], "called_by": ["app-server-pool"]},
    {"service": "redis-cluster",     "calls": [],               "called_by": ["app-server-pool"]},
    {"service": "infra-management",  "calls": ["redis-cluster"], "called_by": []},
]

REDIS_LOGS = [
    "[16:45:00] INFO  Infra automation: removing cache nodes for cost optimization",
    "[16:45:02] INFO  Node redis-cache-1 removed",
    "[16:45:02] INFO  Node redis-cache-2 removed",
    "[16:45:02] INFO  Node redis-cache-3 removed",
    "[16:45:03] WARN  Cache hit rate: 100% → 0% (all nodes removed simultaneously)",
    "[16:45:03] CRIT  Redis cluster has 0 healthy nodes — all requests will miss cache",
]

VITESS_PRIMARY_LOGS = [
    "[16:45:03] WARN  Query rate spike: 450/s → 12800/s (28x normal load)",
    "[16:45:04] ERROR Connection pool exhausted: 500/500 connections active",
    "[16:45:05] ERROR Query timeout: avg 4800ms (was 8ms with cache in place)",
    "[16:45:06] ERROR Thundering herd: all app servers making identical queries simultaneously",
    "[16:45:07] WARN  Vitess vttablet entering degraded mode",
    "[16:45:10] CRIT  Query failure rate 67% — DB cannot handle direct query load",
]

APP_SERVER_LOGS = [
    "[16:45:03] WARN  Cache miss rate: 100% — all requests hitting DB directly",
    "[16:45:04] WARN  DB query latency: 4800ms (threshold: 500ms)",
    "[16:45:05] ERROR Connection refused from vitess-primary: pool exhausted",
    "[16:45:07] ERROR 67% of API requests failing — DB connection errors",
]

INFRA_MGMT_LOGS = [
    "[16:44:58] INFO  Cost optimization task: removing 3 Redis cache nodes",
    "[16:45:00] INFO  Nodes scheduled for removal: redis-cache-1, -2, -3",
    "[16:45:02] INFO  All 3 nodes removed successfully",
    "[16:45:05] WARN  Spike detected on vitess-primary post cache removal",
    "[16:45:06] INFO  Cache removal was simultaneous — gradual removal not used",
]

VITESS_REPLICA_LOGS = [
    "[16:45:03] WARN  Replication lag increasing: 0ms → 240ms",
    "[16:45:05] ERROR Query routing from replica to primary — replica overloaded too",
    "[16:45:07] WARN  vttablet replica degraded: connection pool 92% utilized",
]


class ThunderingHerdTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "redis-cluster":    REDIS_LOGS[:],
            "vitess-primary":   VITESS_PRIMARY_LOGS[:],
            "app-server-pool":  APP_SERVER_LOGS[:],
            "infra-management": INFRA_MGMT_LOGS[:],
            "vitess-replica-1": VITESS_REPLICA_LOGS[:],
        }

        services: Dict[str, dict] = {
            "redis-cluster": {
                "name": "redis-cluster", "status": "down",
                "cpu_percent": 0.0, "memory_percent": 0.0,
                "error_rate": 100.0, "latency_p99_ms": 0.0,
                "replicas_running": 0, "replicas_desired": 3,
                "current_version": "redis-6.2.6",
                "last_deployed": "2022-02-22T16:45:02Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "vitess-primary": {
                "name": "vitess-primary", "status": "degraded",
                "cpu_percent": 99.0, "memory_percent": 87.0,
                "error_rate": 67.0, "latency_p99_ms": 4800.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "vitess-13.0.1",
                "last_deployed": "2022-01-10T08:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "vitess-replica-1": {
                "name": "vitess-replica-1", "status": "degraded",
                "cpu_percent": 92.0, "memory_percent": 78.0,
                "error_rate": 45.0, "latency_p99_ms": 3200.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "vitess-13.0.1",
                "last_deployed": "2022-01-10T08:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "app-server-pool": {
                "name": "app-server-pool", "status": "degraded",
                "cpu_percent": 78.0, "memory_percent": 68.0,
                "error_rate": 67.0, "latency_p99_ms": 5200.0,
                "replicas_running": 20, "replicas_desired": 20,
                "current_version": "v8.4.1",
                "last_deployed": "2022-02-21T14:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "infra-management": {
                "name": "infra-management", "status": "healthy",
                "cpu_percent": 5.0, "memory_percent": 12.0,
                "error_rate": 0.0, "latency_p99_ms": 50.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v2.1.0",
                "last_deployed": "2022-01-01T00:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "A001", "severity": "critical", "service": "redis-cluster",
                "message": "0/3 nodes healthy — cache completely unavailable",
                "timestamp": "2022-02-22T16:45:03Z", "acknowledged": False,
            },
            {
                "id": "A002", "severity": "critical", "service": "vitess-primary",
                "message": "Query failure rate 67% — connection pool exhausted (500/500)",
                "timestamp": "2022-02-22T16:45:04Z", "acknowledged": False,
            },
            {
                "id": "A003", "severity": "warning", "service": "app-server-pool",
                "message": "Cache miss rate 100% — all traffic hitting DB directly",
                "timestamp": "2022-02-22T16:45:03Z", "acknowledged": False,
            },
            {
                "id": "A004", "severity": "info", "service": "infra-management",
                "message": "Cache node removal completed (simultaneous, 3 nodes) — triggered this incident",
                "timestamp": "2022-02-22T16:45:02Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()),
            task_id="thundering_herd",
            step=0,
            max_steps=22,
            services=services,
            alerts=alerts,
            logs=logs,
            action_history=[],
            total_reward=0.0,
            incident_resolved=False,
            ground_truth_root_cause="simultaneous_cache_node_removal_thundering_herd_vitess_overload",
            ground_truth_fix="restore redis cache nodes AND scale_up vitess-primary",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["infra-management"],
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
            ("read_logs",    "redis-cluster"):    ("rl_redis",    0.10),
            ("search_logs",  "redis-cluster"):    ("rl_redis",    0.10),
            ("read_logs",    "vitess-primary"):   ("rl_vitess",   0.10),
            ("search_logs",  "vitess-primary"):   ("rl_vitess",   0.10),
            ("read_logs",    "infra-management"): ("rl_infra",    0.05),
            ("search_logs",  "infra-management"): ("rl_infra",    0.05),
            ("read_metrics", "vitess-primary"):   ("rm_vitess",   0.05),
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
            herd_keywords = ["cache", "thundering", "herd", "removal", "vitess", "db", "database", "redis", "simultaneous"]
            # Needs "cache" AND at least one other keyword
            has_cache = semantic_match(rc, ["cache", "redis"], threshold=1)
            has_herd = semantic_match(rc, ["thundering", "herd", "removal", "vitess", "overload", "exhausted", "simultaneous"], threshold=1)
            if has_cache and has_herd:
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20
                    state.rewards_given.add("diagnose_correct")
            elif has_cache or has_herd:
                if "diagnose_partial" not in state.rewards_given and "diagnose_correct" not in state.rewards_given:
                    reward += 0.08
                    state.rewards_given.add("diagnose_partial")
            result_text = f"Diagnosis recorded: {rc}"

        # --- Fix 1: Scale up vitess-primary (immediate mitigation) ---
        if at == ActionType.RESTART_SERVICE and svc == "vitess-primary":
            # "Scale up" in this context is restarting/adding capacity
            # but we also accept SCALE_UP below
            pass  # handled by RESTART_SERVICE fallthrough

        # We don't have SCALE_UP action type explicitly — map it via restart_service on vitess
        # or alert_oncall (which triggers cache restore by ops team)
        # The correct actions per spec: SCALE_UP vitess and ALERT_ONCALL to restore cache

        # Map RESTART_SERVICE on vitess-primary as scale-up (adds capacity)
        if at == ActionType.RESTART_SERVICE and svc == "vitess-primary":
            blind_penalty = self._penalty_blind_remediation(state, action, "fix_scale_vitess")
            reward += blind_penalty
            if "fix_scale_vitess" not in state.rewards_given:
                reward += 0.25
                state.rewards_given.add("fix_scale_vitess")
                state.services["vitess-primary"]["cpu_percent"] = 72.0
                state.services["vitess-primary"]["latency_p99_ms"] = 1200.0
                state.services["vitess-primary"]["error_rate"] = 28.0
                result_text = (
                    "vitess-primary capacity increased — connection pool expanded to 1000 connections. "
                    "Query failure rate: 67% → 28%. Latency: 4800ms → 1200ms. "
                    "Still degraded — cache must be restored to eliminate thundering herd."
                )
                if "fix_restore_cache" in state.rewards_given:
                    state.incident_resolved = True
                    done = True
                    info["resolution"] = "incident_resolved"

        # --- Fix 2: Alert oncall to restore cache nodes ---
        if at == ActionType.ALERT_ONCALL:
            reason = (action.reason or "").lower()
            cache_related = semantic_match(reason, ["cache", "redis", "nodes", "restore", "thundering"])
            if cache_related:
                if "fix_restore_cache" not in state.rewards_given:
                    reward += 0.20
                    state.rewards_given.add("fix_restore_cache")
                    # Restore cache nodes
                    state.services["redis-cluster"]["status"] = "healthy"
                    state.services["redis-cluster"]["replicas_running"] = 3
                    state.services["redis-cluster"]["error_rate"] = 0.0
                    state.services["app-server-pool"]["error_rate"] = 0.0
                    state.alerts = [a for a in state.alerts if a["id"] not in ("A001", "A003")]
                    result_text = (
                        "On-call team paged. Cache restoration in progress. "
                        "redis-cache-1, -2, -3 reprovisioned. Cache warming underway. "
                        "Cache hit rate recovering. DB query rate dropping from direct hits."
                    )
                    if "fix_scale_vitess" in state.rewards_given:
                        state.incident_resolved = True
                        state.services["vitess-primary"]["status"] = "healthy"
                        state.services["vitess-primary"]["error_rate"] = 0.0
                        state.services["app-server-pool"]["status"] = "healthy"
                        state.alerts = []
                        done = True
                        info["resolution"] = "incident_resolved"
            else:
                result_text = "On-call paged, but without cache-restoration context they cannot act immediately."

        # Collateral damage on healthy services
        if at == ActionType.RESTART_SERVICE and svc in state.healthy_services:
            reward -= 0.10
            error_text = f"Collateral damage: {svc} was healthy. Unnecessary restart."

        if at == ActionType.NOOP and state.step > 4:
            reward -= 0.04

        if at in (ActionType.BLOCK_IP_RANGE, ActionType.CREATE_INDEX, ActionType.FAILOVER):
            reward -= 0.10
            error_text = f"Action {at.value} is not applicable to a cache thundering herd incident."

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True
            info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

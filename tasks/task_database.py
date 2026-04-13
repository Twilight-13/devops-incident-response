from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-04-12T14:22:00Z"

DEPENDENCIES = [
    {"service": "api-gateway", "calls": ["order-service", "user-service"], "called_by": []},
    {"service": "order-service", "calls": ["postgres-primary"], "called_by": ["api-gateway"]},
    {"service": "analytics-service", "calls": ["postgres-primary"], "called_by": []},
    {"service": "postgres-primary", "calls": [], "called_by": ["order-service", "analytics-service"]},
    {"service": "user-service", "calls": [], "called_by": ["api-gateway"]},
]

POSTGRES_LOGS = [
    "[14:22:01] SLOW_QUERY 4281ms: SELECT * FROM orders WHERE user_segment='premium' LIMIT 100 [seq_scan: 18M rows]",
    "[14:22:03] SLOW_QUERY 4190ms: SELECT COUNT(*) FROM orders WHERE user_segment='standard' [seq_scan: 18M rows]",
    "[14:22:05] SLOW_QUERY 4350ms: SELECT order_id, total FROM orders WHERE user_segment='enterprise' [seq_scan: 18M rows]",
    "[14:22:07] INFO MISSING INDEX DETECTED: orders.user_segment has no index (added in migration 20260425_add_user_segment)",
    "[14:22:08] WARN Table scan count: 847/min (normal: 2/min) — index missing on hot column",
    "[14:22:09] SLOW_QUERY 4401ms: SELECT * FROM orders WHERE user_segment='premium' AND created_at > '2026-04-01' [seq_scan]",
]

ORDER_LOGS = [
    "[14:22:01] WARN DB query timeout: getOrdersBySegment() exceeded 5000ms",
    "[14:22:02] ERROR Failed to fetch orders for dashboard: upstream DB timeout",
    "[14:22:05] WARN Retry 1/3: getOrdersBySegment() - 4300ms",
    "[14:22:09] ERROR Circuit breaker OPEN for postgres-primary read replica",
]

ANALYTICS_LOGS = [
    "[14:22:00] INFO Starting hourly aggregation job: orders by user_segment",
    "[14:22:04] WARN Aggregation query running slow: 4100ms elapsed (expected: 80ms)",
    "[14:22:08] ERROR Aggregation job timed out after 300s — will retry in 60min",
    "[14:22:09] INFO Root cause likely: orders table scan (no index on user_segment)",
]


class DatabaseTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "postgres-primary": POSTGRES_LOGS[:],
            "order-service": ORDER_LOGS[:],
            "analytics-service": ANALYTICS_LOGS[:],
            "api-gateway": ["[14:22:05] WARN Upstream order-service latency 4600ms"],
            "user-service": ["[14:22:00] INFO  Service normal"],
        }

        services = {
            "postgres-primary": {
                "name": "postgres-primary", "status": "degraded",
                "cpu_percent": 94.0, "memory_percent": 65.0,
                "error_rate": 0.0, "latency_p99_ms": 4401.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v14.1", "last_deployed": "2025-01-01T00:00:00Z",
                "minutes_degraded": 15, "sla_breach": False,
            },
            "order-service": {
                "name": "order-service", "status": "degraded",
                "cpu_percent": 35.0, "memory_percent": 45.0,
                "error_rate": 2.5, "latency_p99_ms": 4800.0,
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": "v2.1.0", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 15, "sla_breach": False,
            },
            "analytics-service": {
                "name": "analytics-service", "status": "degraded",
                "cpu_percent": 25.0, "memory_percent": 30.0,
                "error_rate": 5.0, "latency_p99_ms": 300000.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v1.5.0", "last_deployed": "2026-04-10T11:00:00Z",
                "minutes_degraded": 15, "sla_breach": False,
            },
            "api-gateway": {
                "name": "api-gateway", "status": "degraded",
                "cpu_percent": 45.0, "memory_percent": 45.0,
                "error_rate": 1.5, "latency_p99_ms": 4600.0,
                "replicas_running": 5, "replicas_desired": 5,
                "current_version": "v3.1.0", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 15, "sla_breach": False,
            },
            "user-service": {
                "name": "user-service", "status": "healthy",
                "cpu_percent": 15.0, "memory_percent": 30.0,
                "error_rate": 0.0, "latency_p99_ms": 25.0,
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v1.1.2", "last_deployed": "2026-03-01T00:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "D001", "severity": "critical", "service": "order-service",
                "message": "P99 latency 4800ms (threshold: 500ms)",
                "timestamp": "2026-04-12T14:22:05Z", "acknowledged": False,
            },
            {
                "id": "D002", "severity": "critical", "service": "analytics-service",
                "message": "Hourly aggregation job timed out",
                "timestamp": "2026-04-12T14:22:08Z", "acknowledged": False,
            },
            {
                "id": "D003", "severity": "warning", "service": "postgres-primary",
                "message": "CPU 94% sustained 15min, high sequential scan rate",
                "timestamp": "2026-04-12T14:22:07Z", "acknowledged": False,
            },
            {
                "id": "D004", "severity": "warning", "service": "api-gateway",
                "message": "Upstream order-service latency 4600ms",
                "timestamp": "2026-04-12T14:22:09Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="database", step=0, max_steps=20,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause="missing_index_orders_user_segment_column_migration",
            ground_truth_fix="create index on orders.user_segment OR rollback migration",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["user-service"],
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

        # Custom read_metrics response for postgres-primary
        if at == ActionType.READ_METRICS and svc == "postgres-primary":
            s = state.services[svc]
            result_text = (
                f"=== Metrics: postgres-primary ===\n"
                f"Status:       {s['status'].upper()}\n"
                f"CPU:          {s['cpu_percent']:.1f}% (normal: 15%)\n"
                f"Memory:       {s['memory_percent']:.1f}%\n"
                f"Sequential scans/min: 847 (normal: 2)\n"
                f"Index scans/min: 12 (normal: 890)\n"
                f"Active queries: 48 (normal: 8)\n"
                f"Longest running query: {s['latency_p99_ms']:.0f}ms\n"
                f"Last migration: 20260425_add_user_segment (14:07:00, 15 min ago)\n"
            )
            state.evidence_log.append({
                "step": state.step,
                "source": f"metrics:{svc}",
                "summary": "postgres-primary: cpu=94%, seq_scans=847/min, normal=2/min",
                "raw": result_text,
            })

        gather_map = {
            ("read_logs", "postgres-primary"):      ("rl_pg", 0.10),
            ("search_logs", "postgres-primary"):    ("rl_pg", 0.10),
            ("read_metrics", "postgres-primary"):   ("rm_pg", 0.10),
            ("read_logs", "analytics-service"):     ("rl_ana", 0.05),
            ("search_logs", "analytics-service"):   ("rl_ana", 0.05),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r; state.rewards_given.add(tag)

        if at == ActionType.READ_RUNBOOK:
            if "runbook_any" not in state.rewards_given:
                reward += 0.05; state.rewards_given.add("runbook_any")

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            if semantic_match(rc, ["index", "migration", "user_segment", "seq_scan", "table scan"]):
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("diagnose_correct")
            result_text = f"Diagnosis recorded: {rc}"

        if at == ActionType.CREATE_INDEX:
            table = (action.table or "").lower()
            column = (action.column or "").lower()
            if table == "orders" and "user_segment" in column:
                if "fix_index" not in state.rewards_given:
                    reward += 0.30; state.rewards_given.add("fix_index")
                    result_text = f"Successfully created index on {table}.{column}. Sequential scans dropped. Query latency normalizing."
                    state.services["postgres-primary"]["cpu_percent"] = 18.0
                    state.services["postgres-primary"]["latency_p99_ms"] = 12.0
                    state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"
            else:
                reward -= 0.10
                result_text = f"Created index on {table}.{column}, but it had no effect on the ongoing sequential scans."

        if at == ActionType.ROLLBACK and svc == "postgres-primary":
            if "fix_index" not in state.rewards_given:
                reward += 0.20; state.rewards_given.add("fix_index")
                result_text = "Migration rolled back. user_segment column removed. Service queries failing back to old schema, but database CPU returning to normal."
                state.services["postgres-primary"]["cpu_percent"] = 18.0
                state.services["postgres-primary"]["latency_p99_ms"] = 12.0
                state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"

        if at == ActionType.RESTART_SERVICE:
            reward -= 0.10
            result_text = f"Restarted {svc}. Connection pool dropped but immediately overwhelmed again by slow queries missing index."

        if at == ActionType.SCALE_UP:
            reward -= 0.08
            result_text = f"Scaled up {svc}. More workers are now hitting the database, worsening the CPU starvation."

        if at == ActionType.NOOP and state.step > 5:
            reward -= 0.03


        if at in (ActionType.BLOCK_IP_RANGE, ActionType.FAILOVER):
            reward -= 0.10
            error_text = f"Action {at.value} is not applicable to this incident."

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

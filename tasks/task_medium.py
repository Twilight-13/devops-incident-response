from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-03-30T10:32:01Z"

DEPENDENCIES = [
    {"service": "api-gateway",          "calls": ["order-service", "user-service"],          "called_by": []},
    {"service": "order-service",        "calls": ["inventory-service"],                       "called_by": ["api-gateway"]},
    {"service": "inventory-service",    "calls": ["db-primary"],                              "called_by": ["order-service"]},
    {"service": "notification-service", "calls": [],                                          "called_by": []},
    {"service": "user-service",         "calls": [],                                          "called_by": ["api-gateway"]},
]

# Cascading scenarios — 3 different root services that can fail
SCENARIOS = [
    {
        "root_service": "inventory-service",
        "root_cause_template": "connection_pool_exhaustion_{service}_{version}",
        "fix_template": "rollback {service}",
        "error_type": "connection_pool",
        "diagnosis_keywords": ["connection", "pool", "hikari", "db", "database", "exhaustion", "inventory"],
        "fix_action": ActionType.ROLLBACK,
    },
    {
        "root_service": "inventory-service",
        "root_cause_template": "null_pointer_exception_{service}_{version}",
        "fix_template": "rollback {service}",
        "error_type": "null_pointer",
        "diagnosis_keywords": ["null", "nullpointer", "npe", "exception", "inventory", "bug", "crash"],
        "fix_action": ActionType.ROLLBACK,
    },
]

INV_LOGS_CONNECTION = [
    "[10:31:58] INFO  Deployment inventory-service:{version} complete - 12 pods running",
    "[10:32:01] INFO  Health check passed for inventory-service:{version}",
    "[10:32:38] ERROR Failed to acquire connection from pool: timeout after 30000ms",
    "[10:32:39] ERROR HikariPool-1 - Connection is not available, request timed out",
    "[10:32:40] ERROR Connection pool exhausted (max=10, active=10, waiting=47)",
    "[10:32:42] WARN  Retry attempt 1/3 failed for getInventory(productId=1982)",
    "[10:32:46] WARN  Retry attempt 3/3 failed - returning error upstream",
    "[10:32:48] ERROR Thread pool saturation: 98/100 threads active, queue depth 412",
]

INV_LOGS_NPE = [
    "[10:31:58] INFO  Deployment inventory-service:{version} complete",
    "[10:32:01] INFO  Health check passed for inventory-service:{version}",
    "[10:32:35] ERROR NullPointerException: Cannot invoke method getStock() on null object",
    "[10:32:35] ERROR   at InventoryService.checkAvailability(InventoryService.java:218)",
    "[10:32:36] ERROR   at InventoryController.getInventory(InventoryController.java:87)",
    "[10:32:37] WARN  Exception rate 38/min - circuit breaker threshold approaching",
    "[10:32:42] ERROR Circuit breaker OPEN - too many NullPointerExceptions",
    "[10:32:45] ERROR getInventory returning 500 for all requests",
]

ORDER_LOGS = [
    "[10:32:30] INFO  Order created: order_id=ORD-8821 status=confirmed",
    "[10:32:45] WARN  inventory-service call timed out after 5000ms",
    "[10:32:49] ERROR Order creation failed: upstream dependency unavailable",
    "[10:32:50] ERROR Circuit breaker OPEN for inventory-service endpoint",
    "[10:32:51] WARN  Falling back to cached inventory data (may be stale)",
]

GATEWAY_LOGS = [
    "[10:32:20] INFO  POST /api/v1/orders 200 142ms",
    "[10:32:50] WARN  POST /api/v1/orders upstream latency 5800ms",
    "[10:32:55] ERROR POST /api/v1/orders 503 Service Unavailable",
    "[10:32:56] WARN  Error rate for /api/v1/orders: 18% (threshold: 5%)",
]

NOTIF_LOGS = [
    "[10:30:00] INFO  Batch email job started: 48000 recipients",
    "[10:31:30] INFO  Sent 24000/48000 emails",
    "[10:33:00] INFO  Batch email job complete: 48000 sent, 0 failed",
]

USER_LOGS = ["[10:32:00] INFO  GET /users/profile 200 9ms",
             "[10:33:00] INFO  GET /users/profile 200 10ms"]


class MediumTask(BaseTask):
    def initialize(self) -> InternalState:
        scenario = SCENARIOS[self.rng.randint(0, len(SCENARIOS) - 1)]
        bad_ver = f"v2.3.{self.rng.randint(1, 5)}"
        root_svc = scenario["root_service"]

        if scenario["error_type"] == "connection_pool":
            inv_logs = [l.replace("{version}", bad_ver) for l in INV_LOGS_CONNECTION]
        else:
            inv_logs = [l.replace("{version}", bad_ver) for l in INV_LOGS_NPE]

        logs = {
            "inventory-service": inv_logs,
            "order-service": ORDER_LOGS[:],
            "api-gateway": GATEWAY_LOGS[:],
            "notification-service": NOTIF_LOGS[:],
            "user-service": USER_LOGS[:],
        }

        services = {
            "api-gateway": {
                "name": "api-gateway", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(55, 70), 1),
                "memory_percent": round(self.rng.uniform(48, 60), 1),
                "error_rate": round(self.rng.uniform(3.5, 6.0), 2),
                "latency_p99_ms": round(self.rng.uniform(4500, 6500), 0),
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v3.1.0", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "order-service": {
                "name": "order-service", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(60, 75), 1),
                "memory_percent": round(self.rng.uniform(55, 68), 1),
                "error_rate": round(self.rng.uniform(4.0, 8.0), 2),
                "latency_p99_ms": round(self.rng.uniform(5000, 7000), 0),
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": "v1.8.2", "last_deployed": "2026-03-22T10:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "inventory-service": {
                "name": "inventory-service", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(80, 95), 1),
                "memory_percent": round(self.rng.uniform(70, 85), 1),
                "error_rate": round(self.rng.uniform(12.0, 20.0), 2),
                "latency_p99_ms": round(self.rng.uniform(28000, 35000), 0),
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": bad_ver, "last_deployed": "2026-03-30T10:31:58Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "notification-service": {
                "name": "notification-service", "status": "healthy",
                "cpu_percent": round(self.rng.uniform(82, 92), 1),
                "memory_percent": round(self.rng.uniform(55, 65), 1),
                "error_rate": 0.0,
                "latency_p99_ms": round(self.rng.uniform(20, 45), 0),
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v1.2.0", "last_deployed": "2026-03-15T16:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "user-service": {
                "name": "user-service", "status": "healthy",
                "cpu_percent": round(self.rng.uniform(20, 35), 1),
                "memory_percent": round(self.rng.uniform(30, 42), 1),
                "error_rate": 0.0,
                "latency_p99_ms": round(self.rng.uniform(8, 20), 0),
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v3.0.5", "last_deployed": "2026-03-18T09:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "A010", "severity": "critical", "service": "api-gateway",
                "message": "Error rate on /api/v1/orders exceeded 15% threshold",
                "timestamp": "2026-03-30T10:32:56Z", "acknowledged": False,
            },
            {
                "id": "A011", "severity": "critical", "service": "order-service",
                "message": "Order creation failure rate 31% - circuit breaker triggered for inventory-service",
                "timestamp": "2026-03-30T10:32:51Z", "acknowledged": False,
            },
            {
                "id": "A012", "severity": "warning", "service": "inventory-service",
                "message": f"P99 latency 32100ms (threshold: 5000ms) - deployed {bad_ver} at 10:31",
                "timestamp": "2026-03-30T10:32:48Z", "acknowledged": False,
            },
            # Red herring
            {
                "id": "A013", "severity": "warning", "service": "notification-service",
                "message": "CPU usage 88% - batch email job running (scheduled, not an incident)",
                "timestamp": "2026-03-30T10:30:00Z", "acknowledged": False,
            },
        ]

        rc = scenario["root_cause_template"].format(service=root_svc, version=bad_ver)
        fix = scenario["fix_template"].format(service=root_svc)

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="medium", step=0, max_steps=20,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause=rc, ground_truth_fix=fix,
            incident_start_time=INCIDENT_TIME,
            healthy_services=["notification-service", "user-service"],
            service_dependencies=DEPENDENCIES,
        )
        state._scenario = scenario
        state._bad_ver = bad_ver
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        state.step += 1
        state._apply_sla_degradation()
        at = action.action_type
        svc = action.service or ""
        scenario = state._scenario
        keywords = scenario["diagnosis_keywords"]
        bad_ver = state._bad_ver
        reward = 0.0
        done = False
        info: Dict[str, Any] = {}

        result_text, error_text = self._apply_action_to_logs(state, action)

        if at == ActionType.READ_LOGS and svc == "inventory-service":
            if "read_logs_inv" not in state.rewards_given:
                reward += 0.10; state.rewards_given.add("read_logs_inv")
        if at == ActionType.READ_METRICS and svc == "inventory-service":
            if "read_metrics_inv" not in state.rewards_given:
                reward += 0.10; state.rewards_given.add("read_metrics_inv")
        if at == ActionType.READ_METRICS and svc == "order-service":
            if "read_metrics_ord" not in state.rewards_given:
                reward += 0.05; state.rewards_given.add("read_metrics_ord")
        if at == ActionType.READ_RUNBOOK:
            if "runbook" not in state.rewards_given:
                reward += 0.05; state.rewards_given.add("runbook")

        # Red herring penalty
        if at == ActionType.RESTART_SERVICE and svc == "notification-service":
            reward -= 0.05
            error_text = "notification-service was healthy — high CPU is a scheduled batch job, not an incident."
        # Treating symptom before root cause
        if at == ActionType.RESTART_SERVICE and svc == "order-service":
            if "diagnose_correct" not in state.rewards_given:
                reward -= 0.10
                error_text = "order-service is a downstream victim. Fix inventory-service first."

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            has_service = semantic_match(rc, ["inventory"])
            has_cause = semantic_match(rc, keywords, threshold=1)
            result_text = f"Diagnosis recorded: {rc}"
            if has_service and has_cause:
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.25; state.rewards_given.add("diagnose_correct")
            elif has_service or has_cause:
                if "diagnose_partial" not in state.rewards_given and "diagnose_correct" not in state.rewards_given:
                    reward += 0.10; state.rewards_given.add("diagnose_partial")

        if at == ActionType.ROLLBACK and svc == "inventory-service":
            reward += self._penalty_blind_remediation(state, action, "rollback_done")
            if "rollback_done" not in state.rewards_given:
                reward += 0.30; state.rewards_given.add("rollback_done")
                ver = action.version or ""
                if "v2.3.0" in ver or ver in ("previous", "last"):
                    reward += 0.10
                state.services["inventory-service"]["status"] = "healthy"
                state.services["inventory-service"]["error_rate"] = 0.0
                state.services["inventory-service"]["latency_p99_ms"] = 85.0
                state.services["inventory-service"]["current_version"] = "v2.3.0"
                state.services["order-service"]["status"] = "healthy"
                state.services["order-service"]["error_rate"] = 0.0
                state.services["api-gateway"]["status"] = "healthy"
                state.services["api-gateway"]["error_rate"] = 0.1
                state.alerts = [a for a in state.alerts if a["id"] not in ("A010", "A011", "A012")]
                state.incident_resolved = True
                result_text = f"inventory-service rolled back. Downstream services recovering."
                done = True; info["resolution"] = "incident_resolved"

        if at in (ActionType.RESTART_SERVICE, ActionType.ROLLBACK) and svc in state.healthy_services:
            reward -= 0.10
        if at == ActionType.NOOP and state.step > 4:
            reward -= 0.03

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

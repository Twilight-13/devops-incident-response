from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-04-13T09:22:00Z"

DEPENDENCIES = [
    {"service": "api-gateway", "calls": ["order-service", "payment-service", "cdn-service"], "called_by": []},
    {"service": "order-service", "calls": ["postgres-primary", "redis-cache"], "called_by": ["api-gateway"]},
    {"service": "payment-service", "calls": ["postgres-primary"], "called_by": ["api-gateway"]},
    {"service": "cdn-service", "calls": [], "called_by": ["api-gateway"]},
    {"service": "redis-cache", "calls": [], "called_by": ["order-service"]},
    {"service": "postgres-primary", "calls": [], "called_by": ["order-service", "payment-service"]},
]

API_LOGS = [
    "[09:15:00] INFO Health check passed: all upstreams responding",
    "[09:22:34] WARN Network timeout to us-east-1 peers: 3 consecutive failures",
    "[09:22:35] ERROR us-east-1 availability zone us-east-1b unreachable",
    "[09:22:36] INFO Multi-region failover available: us-west-2 (last sync: 2min ago)",
    "[09:22:37] WARN Activating degraded mode — some requests failing",
]

POSTGRES_LOGS = [
    "[09:22:34] FATAL Network partition detected: cannot reach 2/3 replicas",
    "[09:22:35] FATAL Entering read-only mode to prevent split-brain",
    "[09:22:36] CRIT Do NOT failover postgres — us-west-2 replica is 45 seconds behind",
    "[09:22:37] CRIT Automatic failover would cause data loss of ~45 seconds of transactions",
    "[09:22:38] INFO Manual DBA intervention required for safe failover procedure",
]

PAYMENT_LOGS = [
    "[09:22:35] FATAL Cannot reach postgres-primary: all writes failing",
    "[09:22:36] CRIT Payment processing SUSPENDED — data integrity protection active",
    "[09:22:37] INFO payment-service is single-region by PCI-DSS compliance requirement",
    "[09:22:38] INFO Do NOT attempt failover — contact payment infrastructure team",
]


class FailoverTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "api-gateway": API_LOGS[:],
            "postgres-primary": POSTGRES_LOGS[:],
            "payment-service": PAYMENT_LOGS[:],
            "order-service": ["[09:22:35] WARN DB connection failed (read-only mode)"],
            "cdn-service": ["[09:22:35] ERROR us-east-1 POP nodes unavailable"],
            "redis-cache": ["[09:22:34] WARN Node partitioned across zone boundary"],
        }

        services = {
            "api-gateway": {
                "name": "api-gateway", "status": "degraded",
                "cpu_percent": 15.0, "memory_percent": 25.0,
                "error_rate": 45.0, "latency_p99_ms": 5000.0,
                "replicas_running": 4, "replicas_desired": 4,
                "current_version": "v1.2", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 5, "sla_breach": False,
            },
            "cdn-service": {
                "name": "cdn-service", "status": "degraded",
                "cpu_percent": 10.0, "memory_percent": 15.0,
                "error_rate": 35.0, "latency_p99_ms": 3000.0,
                "replicas_running": 5, "replicas_desired": 5,
                "current_version": "v1.1", "last_deployed": "2026-02-15T00:00:00Z",
                "minutes_degraded": 5, "sla_breach": False,
            },
            "order-service": {
                "name": "order-service", "status": "degraded",
                "cpu_percent": 5.0, "memory_percent": 20.0,
                "error_rate": 100.0, "latency_p99_ms": 8000.0,
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": "v3.0", "last_deployed": "2026-04-10T11:00:00Z",
                "minutes_degraded": 5, "sla_breach": False,
            },
            "payment-service": {
                "name": "payment-service", "status": "down",
                "cpu_percent": 0.0, "memory_percent": 50.0,
                "error_rate": 100.0, "latency_p99_ms": 10000.0,
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v4.5", "last_deployed": "2025-11-01T00:00:00Z",
                "minutes_degraded": 5, "sla_breach": True,
            },
            "postgres-primary": {
                "name": "postgres-primary", "status": "down",
                "cpu_percent": 90.0, "memory_percent": 65.0,
                "error_rate": 100.0, "latency_p99_ms": 0.0,
                "replicas_running": 1, "replicas_desired": 3,
                "current_version": "v14.1", "last_deployed": "2025-01-01T00:00:00Z",
                "minutes_degraded": 5, "sla_breach": True,
            },
            "redis-cache": {
                "name": "redis-cache", "status": "degraded",
                "cpu_percent": 10.0, "memory_percent": 25.0,
                "error_rate": 50.0, "latency_p99_ms": 200.0,
                "replicas_running": 2, "replicas_desired": 3,
                "current_version": "v6.2", "last_deployed": "2024-01-15T00:00:00Z",
                "minutes_degraded": 5, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "F001", "severity": "critical", "service": "api-gateway",
                "message": "us-east-1 network partition — 45% request failure rate",
                "timestamp": "2026-04-13T09:22:36Z", "acknowledged": False,
            },
            {
                "id": "F002", "severity": "critical", "service": "payment-service",
                "message": "DOWN — all payment processing suspended",
                "timestamp": "2026-04-13T09:22:37Z", "acknowledged": False,
            },
            {
                "id": "F003", "severity": "critical", "service": "postgres-primary",
                "message": "Read-only mode — write operations failing",
                "timestamp": "2026-04-13T09:22:35Z", "acknowledged": False,
            },
            {
                "id": "F004", "severity": "warning", "service": "order-service",
                "message": "Degraded — upstream DB in read-only mode",
                "timestamp": "2026-04-13T09:22:38Z", "acknowledged": False,
            },
            {
                "id": "F005", "severity": "warning", "service": "cdn-service",
                "message": "us-east-1 CDN nodes unreachable",
                "timestamp": "2026-04-13T09:22:36Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="failover", step=0, max_steps=25,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause="us_east_1_network_partition_partial_region_failure",
            ground_truth_fix="failover api-gateway, cdn-service, order-service, redis-cache to us-west-2 AND alert_oncall for payment-service and postgres-primary which cannot auto-failover",
            incident_start_time=INCIDENT_TIME,
            healthy_services=[],
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

        gather_map = {
            ("read_logs", "api-gateway"):      ("rl_api", 0.05),
            ("search_logs", "api-gateway"):    ("rl_api", 0.05),
            ("read_logs", "postgres-primary"): ("rl_pg", 0.05),
            ("search_logs", "postgres-primary"):("rl_pg", 0.05),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r; state.rewards_given.add(tag)

        if at == ActionType.READ_METRICS:
            if "rm_any" not in state.rewards_given:
                reward += 0.05; state.rewards_given.add("rm_any")

        if at == ActionType.READ_RUNBOOK:
            rb = action.runbook or ""
            if rb.endswith("failover_procedures.md"):
                if "runbook_failover" not in state.rewards_given:
                    reward += 0.05; state.rewards_given.add("runbook_failover")

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            if semantic_match(rc, ["network partition", "us-east-1", "region"]):
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("diagnose_correct")
            result_text = f"Diagnosis recorded: {rc}"

        if at == ActionType.FAILOVER:
            target = action.target_region or ""
            if "us-west-2" not in target:
                reward -= 0.05
                result_text = f"Failed to failover to {target}. Region not recognized or not available."
            elif svc == "api-gateway":
                if "fail_api" not in state.rewards_given:
                    reward += 0.12; state.rewards_given.add("fail_api")
                    state.services["api-gateway"]["status"] = "healthy"
                    state.services["api-gateway"]["error_rate"] = 0.0
                    result_text = "api-gateway successfully failed over to us-west-2. Traffic is routing normally."
                else:
                    result_text = "api-gateway already failed over."
            elif svc == "cdn-service":
                if "fail_cdn" not in state.rewards_given:
                    reward += 0.10; state.rewards_given.add("fail_cdn")
                    state.services["cdn-service"]["status"] = "healthy"
                    state.services["cdn-service"]["error_rate"] = 0.0
                    result_text = "cdn-service successfully failed over to us-west-2."
                else:
                    result_text = "cdn-service already failed over."
            elif svc == "order-service":
                if "fail_order" not in state.rewards_given:
                    reward += 0.12; state.rewards_given.add("fail_order")
                    state.services["order-service"]["status"] = "healthy"
                    state.services["order-service"]["error_rate"] = 0.0
                    result_text = "order-service successfully failed over to us-west-2."
                else:
                    result_text = "order-service already failed over."
            elif svc == "redis-cache":
                if "fail_redis" not in state.rewards_given:
                    reward += 0.10; state.rewards_given.add("fail_redis")
                    state.services["redis-cache"]["status"] = "healthy"
                    state.services["redis-cache"]["error_rate"] = 0.0
                    result_text = "redis-cache successfully failed over to us-west-2. Starting sync."
                else:
                    result_text = "redis-cache already failed over."
            elif svc == "payment-service":
                if "fail_pay" not in state.rewards_given:
                    reward -= 0.25; state.rewards_given.add("fail_pay")
                    result_text = "CRITICAL COMPLIANCE VIOLATION: Failed over payment-service despite PCI-DSS single-region requirement. Data integrity compromised."
            elif svc == "postgres-primary":
                if "fail_pg" not in state.rewards_given:
                    reward -= 0.25; state.rewards_given.add("fail_pg")
                    result_text = "CRITICAL DATA LOSS: Forced failover of postgres-primary while secondary was out of sync. Split-brain condition induced."
            else:
                reward -= 0.05
                result_text = f"Service {svc} is not configured for failover or does not exist."

        if at == ActionType.ALERT_ONCALL:
            reason = (action.reason or "").lower()
            if semantic_match(reason, ["payment", "postgres", "database"]):
                if "alert_team" not in state.rewards_given:
                    reward += 0.15; state.rewards_given.add("alert_team")
                    result_text = "Relevant teams paged for payment-service and postgres-primary manual recovery."
            else:
                result_text = "On-call paged without specific service context. Escalation delayed."

        # Check resolution
        has_all_fails = all(t in state.rewards_given for t in ["fail_api", "fail_cdn", "fail_order", "fail_redis"])
        has_alert = "alert_team" in state.rewards_given
        if has_all_fails and has_alert:
            state.incident_resolved = True
            done = True
            info["resolution"] = "incident_resolved"

        if at in (ActionType.RESTART_SERVICE, ActionType.ROLLBACK):
            reward -= 0.05
            result_text = f"Command issued to {svc}, but network communication to us-east-1 is failing. Action timed out."

        if at == ActionType.NOOP and state.step > 5:
            reward -= 0.03

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-04-12T11:37:00Z"

DEPENDENCIES = [
    {"service": "api-gateway", "calls": ["auth-service", "user-service"], "called_by": []},
    {"service": "auth-service", "calls": ["backend-db", "rate-limiter"], "called_by": ["api-gateway"]},
    {"service": "rate-limiter", "calls": [], "called_by": ["auth-service"]},
    {"service": "user-service", "calls": ["backend-db"], "called_by": ["api-gateway"]},
    {"service": "backend-db", "calls": [], "called_by": ["auth-service", "user-service"]},
]

API_LOGS = [
    "[11:37:00] INFO Traffic normal: 820 req/s",
    "[11:37:30] WARN Traffic spike: 2400 req/s - monitoring",
    "[11:38:00] WARN Traffic spike: 5800 req/s - alert fired",
    "[11:38:30] ERROR Traffic: 12000 req/s - rate limiter overwhelmed",
    "[11:38:45] ERROR 94.2% of requests from 185.x.x.x IP range",
    "[11:38:46] ERROR 99.8% of high-volume requests targeting POST /api/v1/login",
    "[11:38:47] WARN Dropping 78% of requests - circuit breaker opening",
    "[11:39:00] ERROR Connection pool to auth-service exhausted: 500/500 connections active",
    "[11:45:01] INFO GET /api/v1/products 200 12ms 203.0.113.42",
    "[11:45:01] WARN POST /api/v1/login 429 8ms 185.220.101.45 [rate-limited]",
    "[11:45:01] WARN POST /api/v1/login 429 8ms 185.220.101.46 [rate-limited]",
    "[11:45:02] INFO GET /api/v1/health 200 3ms 10.0.0.1",
]

AUTH_LOGS = [
    "[11:37:45] INFO Login attempt: user_id=NULL ip=185.220.101.45 (failed - no such user)",
    "[11:37:45] INFO Login attempt: user_id=NULL ip=185.220.101.46 (failed - no such user)",
    "[11:38:00] WARN 98% of login attempts are credential stuffing pattern (NULL user_ids)",
    "[11:38:30] ERROR Thread pool saturation: 498/500 threads active",
    "[11:38:45] ERROR Response time degraded: avg 4200ms (normal: 45ms)",
    "[11:39:00] CRIT Auth service overwhelmed - dropping 60% of legitimate login attempts",
]

RATE_LIMITER_LOGS = [
    "[11:38:00] INFO Rate limit config: 100 req/min per IP (no subnet blocking configured)",
    "[11:38:30] WARN 185.220.101.x subnet generating 8400 req/min across 84 IPs",
    "[11:38:45] WARN Per-IP rate limiting ineffective against distributed botnet",
    "[11:38:46] INFO Subnet 185.220.101.0/24: 84 active IPs, avg 100 req/min each = bypassing limit",
]


class SecurityTask(BaseTask):
    def initialize(self) -> InternalState:
        logs = {
            "api-gateway": API_LOGS[:],
            "auth-service": AUTH_LOGS[:],
            "rate-limiter": RATE_LIMITER_LOGS[:],
            "user-service": ["[11:37:00] INFO  Service normal"],
            "backend-db": ["[11:38:30] WARN High connection count detected from auth-service"],
        }

        services = {
            "api-gateway": {
                "name": "api-gateway", "status": "degraded",
                "cpu_percent": 95.0, "memory_percent": 45.0,
                "error_rate": 78.0, "latency_p99_ms": 3500.0,
                "replicas_running": 5, "replicas_desired": 5,
                "current_version": "v3.1.0", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 8, "sla_breach": False,
            },
            "auth-service": {
                "name": "auth-service", "status": "degraded",
                "cpu_percent": 99.0, "memory_percent": 80.0,
                "error_rate": 60.0, "latency_p99_ms": 4200.0,
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": "v1.5.0", "last_deployed": "2026-04-10T11:00:00Z",
                "minutes_degraded": 8, "sla_breach": False,
            },
            "backend-db": {
                "name": "backend-db", "status": "degraded",
                "cpu_percent": 82.0, "memory_percent": 65.0,
                "error_rate": 0.0, "latency_p99_ms": 150.0,
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v14.1", "last_deployed": "2025-01-01T00:00:00Z",
                "minutes_degraded": 5, "sla_breach": False,
            },
            "rate-limiter": {
                "name": "rate-limiter", "status": "healthy",
                "cpu_percent": 40.0, "memory_percent": 25.0,
                "error_rate": 0.0, "latency_p99_ms": 5.0,
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v2.0.0", "last_deployed": "2026-01-15T00:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
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
                "id": "A001", "severity": "critical", "service": "api-gateway",
                "message": "Error rate 78% - requests being dropped (traffic: 12000 req/s)",
                "timestamp": "2026-04-12T11:38:47Z", "acknowledged": False,
            },
            {
                "id": "A002", "severity": "critical", "service": "auth-service",
                "message": "Response time 4200ms (threshold: 500ms) - connection pool exhausted",
                "timestamp": "2026-04-12T11:38:45Z", "acknowledged": False,
            },
            {
                "id": "A003", "severity": "warning", "service": "backend-db",
                "message": "Connection pool 89% utilized - auth query storm",
                "timestamp": "2026-04-12T11:38:50Z", "acknowledged": False,
            },
            {
                "id": "A004", "severity": "info", "service": "rate-limiter",
                "message": "Per-IP rate limits being bypassed by distributed source",
                "timestamp": "2026-04-12T11:38:46Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="security", step=0, max_steps=20,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause="ddos_attack_185.x.x.x_botnet_targeting_login_endpoint",
            ground_truth_fix="block_ip_range_185.x.x.x AND alert_oncall security team",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["rate-limiter", "user-service"],
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
            ("read_logs", "api-gateway"):      ("rl_api", 0.10),
            ("search_logs", "api-gateway"):    ("rl_api", 0.10),
            ("read_logs", "auth-service"):     ("rl_auth", 0.10),
            ("search_logs", "auth-service"):   ("rl_auth", 0.10),
            ("read_logs", "rate-limiter"):     ("rl_rate", 0.05),
            ("search_logs", "rate-limiter"):   ("rl_rate", 0.05),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r; state.rewards_given.add(tag)

        if at == ActionType.READ_RUNBOOK:
            rb = action.runbook or ""
            if rb.endswith("security_incident.md"):
                if "runbook_security" not in state.rewards_given:
                    reward += 0.05; state.rewards_given.add("runbook_security")

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            if semantic_match(rc, ["ddos", "botnet", "185", "attack", "credential stuffing"]):
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("diagnose_correct")
            result_text = f"Diagnosis recorded: {rc}"

        if at == ActionType.BLOCK_IP_RANGE:
            ip_range = action.ip_range or ""
            if "185" in ip_range:
                if "fix_block" not in state.rewards_given:
                    reward += 0.30; state.rewards_given.add("fix_block")
                    if ip_range == "185.0.0.0/8" or ip_range == "185.220.0.0/16":
                        if "bonus_cidr" not in state.rewards_given:
                            reward += 0.10; state.rewards_given.add("bonus_cidr")
                    result_text = f"Successfully applied firewall block rule for IP range {ip_range}."
                    
                    if "fix_alert" in state.rewards_given:
                        state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"
            else:
                reward -= 0.10
                result_text = f"Blocked IP range {ip_range}, but it did not stop the attack."

        if at == ActionType.ALERT_ONCALL:
            reason = (action.reason or "").lower()
            if semantic_match(reason, ["security", "ddos", "attack"]):
                if "fix_alert" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("fix_alert")
                    result_text = "Security team paged. They are actively monitoring the situation."
                    
                    if "fix_block" in state.rewards_given:
                        state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"
            else:
                result_text = "On-call paged, but without security context they cannot escalate."

        if at == ActionType.RESTART_SERVICE:
            reward -= 0.15
            result_text = f"Restarted {svc}. Connection pool dropped but immediately overwhelmed again by DDoS."

        if at == ActionType.ROLLBACK:
            reward -= 0.10
            result_text = f"Rolled back {svc}, but this is an external attack, not a bad deployment."

        if at == ActionType.NOOP and state.step > 5:
            reward -= 0.03

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

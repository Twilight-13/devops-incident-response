from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-03-30T10:14:47Z"

SCENARIOS = [
    {
        "failing_service": "payment-service",
        "root_cause": "memory_leak_payment_service",
        "fix": "restart payment-service",
        "alert_msg": "payment-service pod restarting (OOMKilled)",
        "language": "java",
        "diagnosis_keywords": ["memory", "oom", "heap", "leak", "outofmemory", "kill"],
    },
    {
        "failing_service": "order-service",
        "root_cause": "memory_leak_order_service",
        "fix": "restart order-service",
        "alert_msg": "order-service pod restarting (OOMKilled)",
        "language": "python",
        "diagnosis_keywords": ["memory", "oom", "heap", "leak", "segfault", "kill", "allocat"],
    },
    {
        "failing_service": "user-service",
        "root_cause": "memory_leak_user_service",
        "fix": "restart user-service",
        "alert_msg": "user-service pod restarting (OOMKilled)",
        "language": "node",
        "diagnosis_keywords": ["memory", "heap", "oom", "leak", "javascript", "kill"],
    },
]

ALL_SERVICES = ["payment-service", "order-service", "user-service", "api-gateway"]
VERSIONS = {
    "payment-service": "v4.2.1", "order-service": "v1.8.2",
    "user-service": "v3.0.5", "api-gateway": "v2.1.0",
}
DEPENDENCIES = [
    {"service": "api-gateway", "calls": ["payment-service", "order-service", "user-service"], "called_by": []},
    {"service": "payment-service", "calls": [], "called_by": ["api-gateway"]},
    {"service": "order-service", "calls": [], "called_by": ["api-gateway"]},
    {"service": "user-service", "calls": [], "called_by": ["api-gateway"]},
]

def _make_logs(scenario, heap1, heap2, restart_count):
    svc = scenario["failing_service"]
    lang = scenario["language"]
    if lang == "java":
        failing = [
            "[10:13:55] INFO  Request processed 200 38ms",
            f"[10:14:35] WARN  Heap usage at {heap1}% - approaching threshold",
            f"[10:14:41] WARN  Heap usage at {heap2}%",
            "[10:14:45] WARN  GC overhead limit exceeded - major GC running",
            "[10:14:47] ERROR java.lang.OutOfMemoryError: Java heap space",
            "[10:14:47] ERROR   at com.payments.ChargeProcessor.process(ChargeProcessor.java:142)",
            f"[10:14:48] FATAL Service entering crash loop - pod restart #{restart_count}",
        ]
    elif lang == "python":
        failing = [
            "[10:13:55] INFO  POST /orders 200 55ms",
            f"[10:14:35] WARN  RSS memory {heap1}% of pod limit",
            f"[10:14:41] WARN  RSS memory {heap2}% of pod limit - approaching OOM",
            "[10:14:46] ERROR Memory allocator: no more pages available",
            "[10:14:47] ERROR Fatal Python error: Segmentation fault (memory allocator exhausted)",
            f"[10:14:48] FATAL Pod killed by OOM killer - restart #{restart_count}",
        ]
    else:
        failing = [
            "[10:13:55] INFO  GET /users/profile 200 9ms",
            f"[10:14:35] WARN  Heap used: {heap1}% ({heap1 * 2}MB / 200MB)",
            f"[10:14:41] WARN  Heap used: {heap2}% - GC pressure increasing",
            "[10:14:47] ERROR FATAL ERROR: Reached heap limit - JavaScript heap out of memory",
            f"[10:14:48] FATAL Container OOMKilled - restart #{restart_count}",
        ]
    logs = {svc: failing}
    for name in ALL_SERVICES:
        if name == svc: continue
        if name == "api-gateway":
            logs[name] = [
                "[10:14:30] INFO  GET /api/v1/health 200 3ms",
                f"[10:14:48] WARN  Upstream {svc} returned 503",
                f"[10:14:49] WARN  Circuit breaker OPEN for {svc}",
            ]
        else:
            logs[name] = ["[10:14:30] INFO  Service healthy - 0 errors"]
    return logs


class EasyTask(BaseTask):
    def initialize(self) -> InternalState:
        scenario = SCENARIOS[self.rng.randint(0, len(SCENARIOS) - 1)]
        failing = scenario["failing_service"]
        heap1 = self.rng.randint(74, 83)
        heap2 = heap1 + self.rng.randint(5, 10)
        restart_count = self.rng.randint(2, 6)

        services: Dict[str, dict] = {}
        for name in ALL_SERVICES:
            if name == failing:
                services[name] = {
                    "name": name, "status": "down",
                    "cpu_percent": round(self.rng.uniform(5, 20), 1),
                    "memory_percent": round(self.rng.uniform(93, 99), 1),
                    "error_rate": round(self.rng.uniform(8.0, 15.0), 2),
                    "latency_p99_ms": round(self.rng.uniform(5000, 9000), 0),
                    "replicas_running": 0, "replicas_desired": 3,
                    "current_version": VERSIONS[name],
                    "last_deployed": "2026-03-28T14:00:00Z",
                    "minutes_degraded": 0, "sla_breach": False,
                }
            elif name == "api-gateway":
                services[name] = {
                    "name": name, "status": "degraded",
                    "cpu_percent": round(self.rng.uniform(35, 55), 1),
                    "memory_percent": round(self.rng.uniform(40, 55), 1),
                    "error_rate": round(self.rng.uniform(2.0, 5.0), 2),
                    "latency_p99_ms": round(self.rng.uniform(800, 1500), 0),
                    "replicas_running": 2, "replicas_desired": 2,
                    "current_version": VERSIONS[name],
                    "last_deployed": "2026-03-25T09:00:00Z",
                    "minutes_degraded": 0, "sla_breach": False,
                }
            else:
                services[name] = {
                    "name": name, "status": "healthy",
                    "cpu_percent": round(self.rng.uniform(20, 40), 1),
                    "memory_percent": round(self.rng.uniform(30, 48), 1),
                    "error_rate": 0.0,
                    "latency_p99_ms": round(self.rng.uniform(8, 30), 0),
                    "replicas_running": 2, "replicas_desired": 2,
                    "current_version": VERSIONS[name],
                    "last_deployed": "2026-03-20T11:00:00Z",
                    "minutes_degraded": 0, "sla_breach": False,
                }

        alerts = [
            {
                "id": "A001", "severity": "critical", "service": failing,
                "message": f"{scenario['alert_msg']} - {restart_count} times in 5 minutes",
                "timestamp": "2026-03-30T10:14:48Z", "acknowledged": False,
            },
            {
                "id": "A002", "severity": "warning", "service": "api-gateway",
                "message": f"Upstream {failing} returning 503 - circuit breaker open",
                "timestamp": "2026-03-30T10:14:52Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="easy", step=0, max_steps=15,
            services=services, alerts=alerts,
            logs=_make_logs(scenario, heap1, heap2, restart_count),
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause=scenario["root_cause"],
            ground_truth_fix=scenario["fix"],
            incident_start_time=INCIDENT_TIME,
            healthy_services=[s for s in ALL_SERVICES if s != failing],
            service_dependencies=DEPENDENCIES,
        )
        state._scenario = scenario
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        state.step += 1
        state._apply_sla_degradation()
        at = action.action_type
        svc = action.service or ""
        scenario = state._scenario
        failing = scenario["failing_service"]
        keywords = scenario["diagnosis_keywords"]
        reward = 0.0
        done = False
        info: Dict[str, Any] = {}

        result_text, error_text = self._apply_action_to_logs(state, action)

        if at in (ActionType.READ_LOGS, ActionType.SEARCH_LOGS) and svc == failing:
            if "logs_investigated" not in state.rewards_given:
                reward += 0.15
                state.rewards_given.add("logs_investigated")

        if at == ActionType.READ_METRICS and svc == failing:
            if "read_metrics" not in state.rewards_given:
                reward += 0.10
                state.rewards_given.add("read_metrics")

        if at == ActionType.READ_RUNBOOK:
            if "runbook" not in state.rewards_given:
                reward += 0.05
                state.rewards_given.add("runbook")

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            correct_type = semantic_match(rc, keywords, threshold=1)
            correct_svc = semantic_match(rc, [failing, failing.split("-")[0]])
            result_text = f"Diagnosis recorded: {rc}"
            if correct_type and correct_svc:
                if "diagnose_correct" not in state.rewards_given:
                    # Give full reward, remove partial if already given
                    bonus = 0.30 if "diagnose_partial" not in state.rewards_given else 0.15
                    reward += bonus
                    state.rewards_given.add("diagnose_correct")
            elif correct_type:
                if "diagnose_partial" not in state.rewards_given and "diagnose_correct" not in state.rewards_given:
                    reward += 0.15
                    state.rewards_given.add("diagnose_partial")

        if at == ActionType.RESTART_SERVICE:
            blind_penalty = self._penalty_blind_remediation(state, action, "restarted")
            reward += blind_penalty
            if svc == failing:
                reward += 0.40
                state.services[svc]["status"] = "healthy"
                state.services[svc]["memory_percent"] = round(self.rng.uniform(38, 48), 1)
                state.services[svc]["error_rate"] = 0.0
                state.services[svc]["latency_p99_ms"] = round(self.rng.uniform(20, 60), 0)
                state.services[svc]["replicas_running"] = state.services[svc]["replicas_desired"]
                state.alerts = [a for a in state.alerts if a["id"] != "A001"]
                state.incident_resolved = True
                result_text = f"{svc} restarted. Memory cleared. All pods healthy."
                done = True
                info["resolution"] = "incident_resolved"
            elif svc in state.healthy_services:
                reward -= 0.10
                error_text = f"Collateral damage: {svc} was healthy. Unnecessary restart."

        if at == ActionType.NOOP and state.step > 3:
            reward -= 0.04

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True
            info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

import random
import uuid
from datetime import datetime
from tasks.base import BaseTask, InternalState, StepOutput
from models import Action, StepResult, ServiceStatus, Alert, ActionType

class GeneratedTask(BaseTask):
    def __init__(self, incident_dict: dict):
        self.incident = incident_dict
        self.task_id = "generated"
        self.max_steps = 20
        # For compatibility with BaseTask which expects rng in __init__
        super().__init__(random.Random(incident_dict.get("seed", 42)))

    def initialize(self) -> InternalState:
        affected = self.incident["affected_service"]
        failure_mode = self.incident["failure_mode"]
        
        services_dict = {}
        SERVICES = ["payment-service", "order-service", "user-service", 
                    "inventory-service", "api-gateway", "notification-service", 
                    "data-pipeline", "ml-inference-service"]
        
        for svc in SERVICES:
            if svc == affected:
                services_dict[svc] = {
                    "name": svc,
                    "status": "degraded",
                    "cpu_percent": 85.0,
                    "memory_percent": 92.0,
                    "error_rate": 0.35,
                    "latency_p99_ms": 2800.0,
                    "replicas_running": 2,
                    "replicas_desired": 3,
                    "current_version": "v1.2.4",
                    "last_deployed": (datetime.utcnow()).isoformat(),
                    "minutes_degraded": 0,
                    "sla_breach": False
                }
            else:
                services_dict[svc] = {
                    "name": svc,
                    "status": "healthy",
                    "cpu_percent": 25.0,
                    "memory_percent": 40.0,
                    "error_rate": 0.01,
                    "latency_p99_ms": 120.0,
                    "replicas_running": 3,
                    "replicas_desired": 3,
                    "current_version": "v1.2.3",
                    "last_deployed": (datetime.utcnow()).isoformat(),
                    "minutes_degraded": 0,
                    "sla_breach": False
                }

        active_alerts = []
        # One CRITICAL alert
        active_alerts.append({
            "id": str(uuid.uuid4())[:8],
            "service": affected,
            "severity": "critical",
            "message": self.incident["description"],
            "timestamp": datetime.utcnow().isoformat(),
            "acknowledged": False
        })
        
        # Noise alerts
        for noise in self.incident["noise_alerts"]:
            active_alerts.append({
                "id": str(uuid.uuid4())[:8],
                "service": "notification-service",
                "severity": "warning",
                "message": noise,
                "timestamp": datetime.utcnow().isoformat(),
                "acknowledged": False
            })

        log_lines = {
            "oom": ["ERROR OutOfMemoryError: Java heap space", 
                    "WARN Memory usage at 98%, GC overhead limit exceeded"],
            "cascade": ["ERROR Connection pool exhausted: timeout after 30s",
                        "ERROR Failed to acquire connection from pool"],
            "corruption": ["WARN Price mismatch detected: expected 29.99 got 299.9",
                           "WARN Data validation failed for 847 records"],
            "security": ["WARN 1847 failed login attempts in 60s",
                         "WARN Rate limit exceeded from 185.220.101.x"],
            "database": ["WARN Slow query: seq_scan on orders (847ms)",
                         "WARN Query planner chose sequential scan, missing index"],
            "network_partition": ["ERROR Connection timeout to us-east-1",
                                  "ERROR Health check failed: unreachable"]
        }
        
        logs = {}
        for svc in SERVICES:
            if svc == affected:
                logs[svc] = log_lines.get(failure_mode, ["INFO Service running normally"])
            else:
                logs[svc] = ["INFO Service running normally", "INFO Health check passed"]

        state = InternalState(
            episode_id=str(uuid.uuid4()),
            task_id="generated",
            step=0,
            max_steps=self.max_steps,
            services=services_dict,
            alerts=active_alerts,
            logs=logs,
            action_history=[],
            total_reward=0.0,
            incident_resolved=False,
            ground_truth_root_cause=self.incident["ground_truth_root_cause"],
            ground_truth_fix=self.incident["ground_truth_fix"],
            incident_start_time=datetime.utcnow().isoformat(),
            rewards_given=set()
        )
        state._scenario = self.incident
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        reward = 0.0
        result_text, error_text = self._apply_action_to_logs(state, action)
        
        # ActionType can be enum or string
        at = action.action_type
        at_val = at.value if hasattr(at, "value") else str(at)
        
        if at_val == "read_logs":
            if action.service == self.incident["affected_service"]:
                if "read_logs" not in state.rewards_given:
                    reward += 0.10
                    state.rewards_given.add("read_logs")
        
        if at_val == "diagnose":
            diagnosis = action.diagnosis or action.root_cause or ""
            if state.ground_truth_root_cause.lower() in diagnosis.lower():
                if "diagnose" not in state.rewards_given:
                    reward += 0.30
                    state.rewards_given.add("diagnose")
        
        if at_val == self.incident["ground_truth_fix"]:
            if action.service == self.incident["affected_service"] and "fix" not in state.rewards_given:
                reward += 0.45
                state.rewards_given.add("fix")
                state.incident_resolved = True
                state.services[self.incident["affected_service"]]["status"] = "healthy"
                state.services[self.incident["affected_service"]]["cpu_percent"] = 25.0
                state.services[self.incident["affected_service"]]["memory_percent"] = 40.0
                state.services[self.incident["affected_service"]]["error_rate"] = 0.01
                state.services[self.incident["affected_service"]]["latency_p99_ms"] = 120.0
        
        state.step += 1
        state.total_reward = self._clamp(state.total_reward + reward)
        
        done = state.incident_resolved or state.step >= self.max_steps
        info = {}
        if state.incident_resolved: info["resolution"] = "incident_resolved"
        if state.step >= self.max_steps: info["reason"] = "max_steps_reached"
        
        state.action_history.append({
            "step": state.step,
            "action": action.model_dump(),
            "reward": round(reward, 4)
        })
        
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

from __future__ import annotations
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from models import (
    Action, ActionType, Observation, State, StepResult,
    ServiceStatus, Alert, ServiceDependency, EvidenceEntry,
)


AVAILABLE_RUNBOOKS = [
    "high_cpu.md",
    "memory_leak.md",
    "db_connection.md",
    "deployment_rollback.md",
    "cascade_failure.md",
    "data_corruption.md",
]

TASK_DESCRIPTIONS = {
    "easy": (
        "PRODUCTION INCIDENT — One service is crash-looping. "
        "Read its logs and metrics to find the root cause, diagnose precisely, "
        "then apply the correct single-service fix. "
        "Avoid restarting healthy services — collateral damage is penalised."
    ),
    "medium": (
        "PRODUCTION INCIDENT — Multiple services are degraded. "
        "Use the service dependency map to trace the failure to its origin. "
        "A recent deployment is likely involved. One alert is a red herring. "
        "Fix the root service only — downstream victims will self-heal."
    ),
    "hard": (
        "PRODUCTION INCIDENT — All services show green health. No error-rate alerts. "
        "Look for anomalies in business-logic metrics and WARN-level logs. "
        "Correlate signals across services to find silent data corruption. "
        "Two actions are required for full credit: rollback AND alert_oncall."
    ),
    "bonus": (
        "PRODUCTION INCIDENT — Two independent failures are active simultaneously. "
        "They are unrelated — fixing one will NOT fix the other. "
        "Identify both root causes and remediate each independently. "
        "Full credit requires resolving both."
    ),
}


@dataclass
class InternalState:
    episode_id: str
    task_id: str
    step: int
    max_steps: int
    services: Dict[str, dict]
    alerts: list
    logs: Dict[str, List[str]]
    action_history: List[Dict[str, Any]]
    total_reward: float
    incident_resolved: bool
    ground_truth_root_cause: str
    ground_truth_fix: str
    incident_start_time: str
    rewards_given: Set[str] = field(default_factory=set)
    healthy_services: List[str] = field(default_factory=list)
    evidence_log: List[dict] = field(default_factory=list)
    service_dependencies: List[dict] = field(default_factory=list)
    _scenario: Any = field(default=None, repr=False)
    _ml_version: Any = field(default=None, repr=False)

    def to_state_snapshot(self) -> State:
        obs = self._build_observation()
        return State(
            episode_id=self.episode_id,
            task_id=self.task_id,
            step=self.step,
            current_observation=obs,
            action_history=self.action_history,
            total_reward=round(self.total_reward, 4),
            incident_resolved=self.incident_resolved,
            ground_truth_root_cause=self.ground_truth_root_cause,
            ground_truth_fix=self.ground_truth_fix,
            info={
                "rewards_unlocked": sorted(self.rewards_given),
                "evidence_gathered": len(self.evidence_log),
            },
        )

    def _build_sla_status(self) -> Dict[str, str]:
        status = {}
        for name, svc in self.services.items():
            if svc["status"] == "down":
                mins = self.step * 2
                if mins >= 10:
                    status[name] = "breached"
                elif mins >= 5:
                    status[name] = "warning"
                else:
                    status[name] = "ok"
            elif svc["status"] == "degraded":
                mins = self.step * 2
                if mins >= 20:
                    status[name] = "breached"
                elif mins >= 10:
                    status[name] = "warning"
                else:
                    status[name] = "ok"
            else:
                status[name] = "ok"
        return status

    def _apply_sla_degradation(self) -> None:
        """Services get progressively worse if not fixed — adds urgency."""
        if self.incident_resolved:
            return
        for name, svc in self.services.items():
            if svc["status"] == "down":
                svc["minutes_degraded"] = svc.get("minutes_degraded", 0) + 2
                # Error rate creeps up
                svc["error_rate"] = min(svc["error_rate"] * 1.05, 50.0)
            elif svc["status"] == "degraded":
                svc["minutes_degraded"] = svc.get("minutes_degraded", 0) + 2
                # Latency grows
                svc["latency_p99_ms"] = min(svc["latency_p99_ms"] * 1.03, 60000.0)
                if svc["latency_p99_ms"] > 30000 and svc["error_rate"] < 1.0:
                    svc["error_rate"] = round(svc["error_rate"] + 0.5, 2)

    def _build_observation(
        self,
        last_action_result: Optional[str] = None,
        last_action_error: Optional[str] = None,
    ) -> Observation:
        services = []
        for name, s in self.services.items():
            services.append(ServiceStatus(
                name=s["name"],
                status=s["status"],
                cpu_percent=s["cpu_percent"],
                memory_percent=s["memory_percent"],
                error_rate=round(s["error_rate"], 3),
                latency_p99_ms=round(s["latency_p99_ms"], 0),
                replicas_running=s["replicas_running"],
                replicas_desired=s["replicas_desired"],
                current_version=s["current_version"],
                last_deployed=s["last_deployed"],
                sla_breach=s.get("sla_breach", False),
                minutes_degraded=s.get("minutes_degraded", 0),
            ))

        alerts = [Alert(**a) for a in self.alerts]
        deps = [ServiceDependency(**d) for d in self.service_dependencies]
        evidence = [EvidenceEntry(**e) for e in self.evidence_log]
        sla = self._build_sla_status()

        return Observation(
            step=self.step,
            max_steps=self.max_steps,
            task_id=self.task_id,
            task_description=TASK_DESCRIPTIONS.get(self.task_id, ""),
            services=services,
            active_alerts=alerts,
            recent_logs=self.logs,
            available_runbooks=AVAILABLE_RUNBOOKS,
            service_dependencies=deps,
            evidence_log=evidence,
            sla_status=sla,
            last_action_result=last_action_result,
            last_action_error=last_action_error,
            incident_start_time=self.incident_start_time,
            elapsed_minutes=self.step * 2,
        )


@dataclass
class StepOutput:
    next_state: InternalState
    reward: float
    done: bool
    info: Dict[str, Any]


def semantic_match(candidate: str, keywords: List[str], threshold: int = 1) -> bool:
    """
    Returns True if candidate contains at least `threshold` keywords.
    Case-insensitive, handles hyphens/underscores.
    """
    if not candidate:
        return False
    c = candidate.lower().replace("-", " ").replace("_", " ")
    hits = sum(1 for kw in keywords if kw.lower().replace("-", " ") in c)
    return hits >= threshold


class BaseTask(ABC):
    def __init__(self, rng: random.Random):
        self.rng = rng

    @abstractmethod
    def initialize(self) -> InternalState:
        pass

    @abstractmethod
    def step(self, state: InternalState, action: Action) -> StepOutput:
        pass

    def _apply_action_to_logs(
        self, state: InternalState, action: Action
    ) -> tuple[Optional[str], Optional[str]]:
        at = action.action_type.value

        if at == "read_logs":
            svc = action.service
            if svc and svc in state.logs:
                lines = state.logs[svc]
                result = "\n".join(lines)
                # Add to evidence log
                state.evidence_log.append({
                    "step": state.step,
                    "source": f"logs:{svc}",
                    "summary": f"Read {len(lines)} log lines from {svc}",
                    "raw": result,
                })
                return result, None
            return None, f"No logs found for service '{svc}'"

        if at == "read_metrics":
            svc = action.service
            if svc and svc in state.services:
                s = state.services[svc]
                result = (
                    f"=== Metrics: {svc} ===\n"
                    f"Status:       {s['status'].upper()}\n"
                    f"CPU:          {s['cpu_percent']:.1f}%\n"
                    f"Memory:       {s['memory_percent']:.1f}%\n"
                    f"Error rate:   {s['error_rate']:.3f}/s\n"
                    f"P99 latency:  {s['latency_p99_ms']:.0f}ms\n"
                    f"Replicas:     {s['replicas_running']}/{s['replicas_desired']}\n"
                    f"Version:      {s['current_version']}\n"
                    f"Last deploy:  {s['last_deployed']}\n"
                    f"Degraded for: {s.get('minutes_degraded', 0)} minutes"
                )
                state.evidence_log.append({
                    "step": state.step,
                    "source": f"metrics:{svc}",
                    "summary": (
                        f"{svc}: {s['status']}, cpu={s['cpu_percent']:.0f}%, "
                        f"mem={s['memory_percent']:.0f}%, err={s['error_rate']:.2f}/s, "
                        f"ver={s['current_version']}"
                    ),
                    "raw": result,
                })
                return result, None
            return None, f"Unknown service '{svc}'"

        if at == "read_runbook":
            rb = action.runbook
            if rb in AVAILABLE_RUNBOOKS:
                content = self._load_runbook(rb)
                state.evidence_log.append({
                    "step": state.step,
                    "source": f"runbook:{rb}",
                    "summary": f"Read runbook: {rb}",
                    "raw": content[:200],
                })
                return content, None
            return None, f"Runbook '{rb}' not found. Available: {AVAILABLE_RUNBOOKS}"

        if at == "acknowledge":
            alert_id = action.service
            for a in state.alerts:
                if a["id"] == alert_id:
                    a["acknowledged"] = True
                    return f"Alert {alert_id} acknowledged.", None
            return None, f"Alert '{alert_id}' not found."

        if at == "noop":
            return "No action taken.", None

        return None, None

    def _load_runbook(self, name: str) -> str:
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "runbooks", name)
        try:
            with open(path) as f:
                return f.read()
        except FileNotFoundError:
            return f"[Runbook '{name}' not found]"

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _penalty_blind_remediation(
        self, state: InternalState, action: Action, fix_key: str
    ) -> float:
        """
        Small penalty if agent remediates without any prior diagnosis.
        Encourages evidence-gathering before action.
        """
        if fix_key in state.rewards_given:
            return 0.0
        if "diagnose_correct" not in state.rewards_given and \
           "diagnose_partial" not in state.rewards_given:
            return -0.05
        return 0.0

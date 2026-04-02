from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum


class ActionType(str, Enum):
    DIAGNOSE = "diagnose"
    READ_LOGS = "read_logs"
    READ_METRICS = "read_metrics"
    READ_RUNBOOK = "read_runbook"
    RESTART_SERVICE = "restart_service"
    ROLLBACK = "rollback"
    SCALE_UP = "scale_up"
    ALERT_ONCALL = "alert_oncall"
    ACKNOWLEDGE = "acknowledge"
    NOOP = "noop"
    SEARCH_LOGS = "search_logs"


class Action(BaseModel):
    action_type: ActionType
    service: Optional[str] = None
    root_cause: Optional[str] = None
    runbook: Optional[str] = None
    version: Optional[str] = None
    reason: Optional[str] = None
    query: Optional[str] = None  # used with search_logs


class Alert(BaseModel):
    id: str
    severity: Literal["critical", "warning", "info"]
    service: str
    message: str
    timestamp: str
    acknowledged: bool = False


class ServiceStatus(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "down", "unknown"]
    cpu_percent: float
    memory_percent: float
    error_rate: float
    latency_p99_ms: float
    replicas_running: int
    replicas_desired: int
    current_version: str
    last_deployed: str
    # SLA tracking — updated each step if unresolved
    sla_breach: bool = False
    minutes_degraded: int = 0


class ServiceDependency(BaseModel):
    """Describes which services call which — critical for cascade diagnosis."""
    service: str
    calls: List[str]  # services this one depends on
    called_by: List[str]  # services that depend on this one


class EvidenceEntry(BaseModel):
    """One piece of gathered evidence — accumulated across steps."""
    step: int
    source: str       # e.g. "logs:payment-service" or "metrics:inventory-service"
    summary: str      # short digest of what was found
    raw: str          # full content returned by read action


class Observation(BaseModel):
    step: int
    max_steps: int
    task_id: str
    task_description: str
    services: List[ServiceStatus]
    active_alerts: List[Alert]
    recent_logs: Dict[str, List[str]]
    available_runbooks: List[str]
    # NEW: dependency topology so agent can reason about cascades
    service_dependencies: List[ServiceDependency] = []
    # NEW: accumulated evidence from all previous read actions
    evidence_log: List[EvidenceEntry] = []
    # NEW: SLA status — shows urgency
    sla_status: Dict[str, str] = {}   # service -> "ok" | "warning" | "breached"
    last_action_result: Optional[str] = None
    last_action_error: Optional[str] = None
    incident_start_time: str
    elapsed_minutes: int


class StepResult(BaseModel):
    observation: Observation
    reward: float
    done: bool
    info: Dict[str, Any] = {}


class State(BaseModel):
    episode_id: str
    task_id: str
    step: int
    current_observation: Observation
    action_history: List[Dict[str, Any]]
    total_reward: float
    incident_resolved: bool
    ground_truth_root_cause: str
    ground_truth_fix: str
    info: Dict[str, Any] = {}

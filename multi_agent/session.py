from __future__ import annotations

import copy
import uuid

from env import DevOpsIncidentEnv
from models import Action


class DualAgentSession:
    def __init__(self, task_id: str, seed: int = 42):
        self.session_id = str(uuid.uuid4())
        self.task_id = task_id
        self.seed = seed
        self.env = DevOpsIncidentEnv(task_id=task_id, seed=seed)
        self.full_obs = self.env.reset(seed=seed)
        self.findings_log = []
        self.step_count = 0
        self.done = False

    def _observation_dict(self) -> dict:
        if hasattr(self.full_obs, "model_dump"):
            return self.full_obs.model_dump()
        if hasattr(self.full_obs, "dict"):
            return self.full_obs.dict()
        return copy.deepcopy(self.full_obs)

    def get_observation_a(self) -> dict:
        obs = self._observation_dict()
        return {
            "step": obs["step"],
            "max_steps": obs["max_steps"],
            "task_id": obs["task_id"],
            "task_description": obs["task_description"],
            "active_alerts": copy.deepcopy(obs.get("active_alerts", [])),
            "recent_logs": copy.deepcopy(obs.get("recent_logs", {})),
            "evidence_log": copy.deepcopy(obs.get("evidence_log", [])),
            "last_action_result": obs.get("last_action_result"),
            "last_action_error": obs.get("last_action_error"),
            "elapsed_minutes": obs["elapsed_minutes"],
            "incident_start_time": obs["incident_start_time"],
            "role": "observer",
            "instructions": (
                "You are the Observer. You can ONLY call share_finding. "
                "Read logs and alerts carefully, then share findings with "
                "the Responder agent."
            ),
            "findings_from_b": [],
        }

    def get_observation_b(self) -> dict:
        obs = self._observation_dict()
        return {
            "step": obs["step"],
            "max_steps": obs["max_steps"],
            "task_id": obs["task_id"],
            "task_description": obs["task_description"],
            "services": copy.deepcopy(obs.get("services", [])),
            "service_dependencies": copy.deepcopy(obs.get("service_dependencies", [])),
            "sla_status": copy.deepcopy(obs.get("sla_status", {})),
            "last_action_result": obs.get("last_action_result"),
            "last_action_error": obs.get("last_action_error"),
            "elapsed_minutes": obs["elapsed_minutes"],
            "incident_start_time": obs["incident_start_time"],
            "role": "responder",
            "instructions": (
                "You are the Responder. Use Agent A findings plus service "
                "metrics to diagnose and fix the incident."
            ),
            "agent_a_findings": copy.deepcopy(self.findings_log),
        }

    def step_a(self, finding_text: str) -> dict:
        if self.done:
            return {"error": "episode complete"}
        if not finding_text or len(finding_text.strip()) < 5:
            return {"error": "finding too short", "reward": 0.0}
        entry = {
            "agent": "A",
            "step": self.step_count,
            "finding": finding_text.strip(),
        }
        self.findings_log.append(entry)
        return {
            "accepted": True,
            "reward": 0.05,
            "finding_recorded": entry,
            "total_findings": len(self.findings_log),
            "observation": self.get_observation_a(),
        }

    def step_b(self, action: Action) -> dict:
        if self.done:
            return {"error": "episode complete"}
        self.step_count += 1
        result = self.env.step(action)
        self.full_obs = result.observation
        if result.done:
            self.done = True
        return {
            "observation": self.get_observation_b(),
            "reward": result.reward,
            "done": result.done,
            "info": result.info,
            "agent_a_findings_count": len(self.findings_log),
        }

    def get_state(self) -> dict:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "seed": self.seed,
            "step": self.step_count,
            "done": self.done,
            "findings_log": copy.deepcopy(self.findings_log),
            "observation_a": self.get_observation_a(),
            "observation_b": self.get_observation_b(),
        }

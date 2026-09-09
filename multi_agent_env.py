"""
multi_agent_env.py — MultiAgentDevOpsEnv

Two agents collaborate on the same DevOps incident episode:

  Investigator  — gathers evidence and diagnoses
  Responder     — applies remediation actions

Both share one underlying DevOpsIncidentEnv. The Investigator's evidence
is visible to the Responder through the shared observation's evidence_log.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Optional

from env import DevOpsIncidentEnv
from models import Action, ActionType, Observation


# ---------------------------------------------------------------------------
# Role action sets
# ---------------------------------------------------------------------------

INVESTIGATOR_ACTIONS: frozenset[ActionType] = frozenset({
    ActionType.READ_LOGS,
    ActionType.READ_METRICS,
    ActionType.READ_RUNBOOK,
    ActionType.SEARCH_LOGS,
    ActionType.DIAGNOSE,
    ActionType.ACKNOWLEDGE,
    ActionType.NOOP,
})

RESPONDER_ACTIONS: frozenset[ActionType] = frozenset({
    ActionType.RESTART_SERVICE,
    ActionType.ROLLBACK,
    ActionType.BLOCK_IP_RANGE,
    ActionType.CREATE_INDEX,
    ActionType.FAILOVER,
    ActionType.SCALE_UP,
    ActionType.ALERT_ONCALL,
    ActionType.NOOP,
})


# ---------------------------------------------------------------------------
# Joint observation container
# ---------------------------------------------------------------------------

@dataclass
class MultiAgentObservation:
    """Holds both agents' views of the current environment state."""
    investigator_obs: Observation
    responder_obs: Observation
    step: int = 0
    done: bool = False

    def to_dict(self) -> dict:
        return {
            "investigator_obs": (
                self.investigator_obs.model_dump()
                if hasattr(self.investigator_obs, "model_dump")
                else self.investigator_obs.dict()
            ),
            "responder_obs": (
                self.responder_obs.model_dump()
                if hasattr(self.responder_obs, "model_dump")
                else self.responder_obs.dict()
            ),
            "step": self.step,
            "done": self.done,
        }


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class MultiAgentDevOpsEnv:
    """
    Multi-agent wrapper around DevOpsIncidentEnv.

    Two agents — Investigator and Responder — collaborate on the same
    incident episode.  They share one underlying environment (and thus
    one step counter) but are restricted to disjoint action sets.

    Usage::

        env = MultiAgentDevOpsEnv(task_id="bonus", seed=42)
        obs = env.reset()
        # obs is a MultiAgentObservation

        result = env.step_investigator(
            Action(action_type=ActionType.READ_LOGS, service="log-aggregator")
        )
        # result["investigator_reward"] > 0

        result = env.step_responder(
            Action(action_type=ActionType.ROLLBACK, service="ml-inference-service")
        )
        # result["responder_reward"] > 0

    Both agents may NOOP on any turn.  The episode ends when the
    underlying environment signals done (max_steps or resolution).
    """

    LEVELS = {
        "investigator": INVESTIGATOR_ACTIONS,
        "responder": RESPONDER_ACTIONS,
    }

    def __init__(self, task_id: str = "easy", seed: int = 42) -> None:
        self.task_id = task_id
        self.seed = seed
        self.session_id = str(uuid.uuid4())

        self._env = DevOpsIncidentEnv(task_id=task_id, seed=seed)
        self._obs: Optional[Observation] = None
        self._done: bool = False
        self._step: int = 0

        # Per-agent cumulative rewards
        self._investigator_reward: float = 0.0
        self._responder_reward: float = 0.0

        # History for debugging / logging
        self._investigator_actions: list[dict] = []
        self._responder_actions: list[dict] = []

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def reset(self) -> MultiAgentObservation:
        """Reset the environment.  Both agent views are returned."""
        self._obs = self._env.reset(seed=self.seed)
        self._done = False
        self._step = 0
        self._investigator_reward = 0.0
        self._responder_reward = 0.0
        self._investigator_actions.clear()
        self._responder_actions.clear()
        return self._make_obs()

    def step_investigator(self, action: Action) -> dict:
        """
        Investigator takes one step.

        Returns a dict with keys:
            investigator_obs   — updated Observation (after action)
            investigator_reward — float reward for this step
            done               — bool, episode over
            error              — str (only present if action was invalid)
        """
        if self._done:
            return {"error": "episode complete", "investigator_reward": 0.0, "done": True}

        if action.action_type not in INVESTIGATOR_ACTIONS:
            return {
                "error": (
                    f"Action '{action.action_type.value}' is not allowed for Investigator. "
                    f"Allowed: {[a.value for a in INVESTIGATOR_ACTIONS]}"
                ),
                "investigator_reward": 0.0,
                "done": False,
            }

        result = self._env.step(action)
        self._obs = result.observation
        self._step += 1
        if result.done:
            self._done = True

        # Investigator-specific reward scaling
        reward = self._compute_investigator_reward(action, result.reward)
        self._investigator_reward += reward
        self._investigator_actions.append({
            "step": self._step,
            "action_type": action.action_type.value,
            "service": action.service,
            "reward": reward,
        })

        return {
            "investigator_obs": (
                result.observation.model_dump()
                if hasattr(result.observation, "model_dump")
                else result.observation.dict()
            ),
            "investigator_reward": reward,
            "done": result.done,
            "info": result.info,
        }

    def step_responder(self, action: Action) -> dict:
        """
        Responder takes one step.

        Returns a dict with keys:
            responder_obs   — updated Observation (after action)
            responder_reward — float reward for this step
            done             — bool, episode over
            error            — str (only present if action was invalid)
        """
        if self._done:
            return {"error": "episode complete", "responder_reward": 0.0, "done": True}

        if action.action_type not in RESPONDER_ACTIONS:
            return {
                "error": (
                    f"Action '{action.action_type.value}' is not allowed for Responder. "
                    f"Allowed: {[a.value for a in RESPONDER_ACTIONS]}"
                ),
                "responder_reward": 0.0,
                "done": False,
            }

        result = self._env.step(action)
        self._obs = result.observation
        self._step += 1
        if result.done:
            self._done = True

        # Responder-specific reward scaling
        reward = self._compute_responder_reward(action, result.reward)
        self._responder_reward += reward
        self._responder_actions.append({
            "step": self._step,
            "action_type": action.action_type.value,
            "service": action.service,
            "reward": reward,
        })

        return {
            "responder_obs": (
                result.observation.model_dump()
                if hasattr(result.observation, "model_dump")
                else result.observation.dict()
            ),
            "responder_reward": reward,
            "done": result.done,
            "info": result.info,
        }

    # -----------------------------------------------------------------------
    # Reward accessors
    # -----------------------------------------------------------------------

    def get_investigator_reward(self) -> float:
        """Cumulative reward earned by the Investigator so far."""
        return self._investigator_reward

    def get_responder_reward(self) -> float:
        """Cumulative reward earned by the Responder so far."""
        return self._responder_reward

    def get_joint_reward(self) -> float:
        """Mean of both agents' cumulative rewards."""
        return (self._investigator_reward + self._responder_reward) / 2.0

    def get_state(self) -> dict:
        """Full environment state for logging / debugging."""
        s = self._env.state()
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "seed": self.seed,
            "step": self._step,
            "done": self._done,
            "investigator_reward": self._investigator_reward,
            "responder_reward": self._responder_reward,
            "joint_reward": self.get_joint_reward(),
            "investigator_actions": self._investigator_actions,
            "responder_actions": self._responder_actions,
            "ground_truth_root_cause": s.ground_truth_root_cause,
            "ground_truth_fix": s.ground_truth_fix,
            "incident_resolved": s.incident_resolved,
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _make_obs(self) -> MultiAgentObservation:
        """Build a MultiAgentObservation from the current env state."""
        assert self._obs is not None
        # Both agents see the full observation; role is distinguished by
        # which step_*() method they call, not by observation filtering.
        return MultiAgentObservation(
            investigator_obs=self._obs,
            responder_obs=self._obs,
            step=self._step,
            done=self._done,
        )

    @staticmethod
    def _compute_investigator_reward(action: Action, raw: float) -> float:
        """
        Scale raw env reward for the Investigator role.

        The Investigator is credited for gathering evidence and diagnosing.
        Remediation rewards are not credited to them (they'll be ≤0 anyway
        since the env penalises remediation without diagnosis).
        """
        if action.action_type == ActionType.READ_LOGS:
            return max(raw, 0.0)          # keep positive signal
        if action.action_type == ActionType.READ_METRICS:
            return max(raw, 0.0)
        if action.action_type == ActionType.READ_RUNBOOK:
            return max(raw * 0.5, 0.0)   # lower weight for runbook reads
        if action.action_type == ActionType.DIAGNOSE:
            return raw                    # full credit — can be negative too
        if action.action_type == ActionType.NOOP:
            return min(raw, 0.0)          # noop penalised as normal
        return max(raw, 0.0)

    @staticmethod
    def _compute_responder_reward(action: Action, raw: float) -> float:
        """
        Scale raw env reward for the Responder role.

        The Responder is credited for correct remediation and penalised for
        collateral damage.
        """
        if action.action_type == ActionType.NOOP:
            return min(raw, 0.0)
        # Pass through raw reward (includes collateral damage penalties)
        return raw

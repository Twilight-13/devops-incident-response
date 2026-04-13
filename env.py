from __future__ import annotations
import random
from typing import Optional
from models import Action, Observation, StepResult, State
from tasks import EasyTask, MediumTask, HardTask, BonusTask, SecurityTask, DatabaseTask, FailoverTask
from tasks.base import InternalState

TASK_MAP = {
    "easy": EasyTask,
    "medium": MediumTask,
    "hard": HardTask,
    "bonus": BonusTask,
    "security": SecurityTask,
    "database": DatabaseTask,
    "failover": FailoverTask,
}


class DevOpsIncidentEnv:
    """
    OpenEnv-compliant environment for DevOps incident response.

    Seven tasks of escalating and diverse difficulty:
      easy     - Single service OOM (rotating service by seed)
      medium   - Cascading failure from bad deployment (red-herring alert)
      hard     - Silent data corruption, no error-rate alerts
      bonus    - Two simultaneous independent failures, both must be fixed
      security - DDoS attack mitigation (blocking IPs)
      database - Missing indexes leading to performance degradation
      failover - Multi-region partition with partial failover constraints
    """

    def __init__(self, task_id: str = "easy", seed: Optional[int] = None):
        if task_id not in TASK_MAP:
            raise ValueError(
                f"task_id must be one of {list(TASK_MAP.keys())}, got '{task_id}'"
            )
        self.task_id = task_id
        self.seed = seed
        self._task = None
        self._internal_state: Optional[InternalState] = None

    def reset(self, seed: Optional[int] = None) -> Observation:
        if seed is not None:
            self.seed = seed
        rng = random.Random(self.seed)
        self._task = TASK_MAP[self.task_id](rng=rng)
        self._internal_state = self._task.initialize()
        return self._internal_state._build_observation()

    def step(self, action: Action) -> StepResult:
        if self._internal_state is None:
            raise RuntimeError("Call reset() before step()")
        output = self._task.step(self._internal_state, action)
        self._internal_state = output.next_state
        return StepResult(
            observation=self._internal_state._build_observation(),
            reward=output.reward,
            done=output.done,
            info=output.info,
        )

    def state(self) -> State:
        if self._internal_state is None:
            raise RuntimeError("Call reset() before state()")
        s = self._internal_state
        from graders.grader import grade_episode, get_episode_analytics
        snap = s.to_state_snapshot()
        analytics = get_episode_analytics(
            s.task_id, s.action_history,
            s.ground_truth_root_cause, s.incident_resolved,
        )
        current_score = grade_episode(
            s.task_id, s.action_history, s.ground_truth_root_cause,
            s.ground_truth_fix, s.incident_resolved, s.total_reward,
        )
        snap.info = {
            "rewards_unlocked": sorted(s.rewards_given),
            "current_score": current_score,
            "analytics": analytics,
        }
        return snap

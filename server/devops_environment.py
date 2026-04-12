import asyncio
from typing import Optional, Any
from openenv.core.env_server import Environment
from models import Action, Observation, StepResult, State
from env import DevOpsIncidentEnv as DevOpsIncidentLogic

class DevOpsEnvironment(Environment[Action, Observation, State]):
    """Server-side environment wrapper using openenv-core."""
    
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        super().__init__()
        self._logic: Optional[DevOpsIncidentLogic] = None

    async def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task_id: str = "easy",
        **kwargs: Any
    ) -> Observation:
        self._logic = DevOpsIncidentLogic(task_id=task_id, seed=seed)
        return self._logic.reset()

    async def step(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any
    ) -> StepResult:
        if self._logic is None:
            raise RuntimeError("Environment not reset")
        return self._logic.step(action)

    @property
    def state(self) -> State:
        if self._logic is None:
            raise RuntimeError("Environment not reset")
        return self._logic.state()

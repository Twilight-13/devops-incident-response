import json
from typing import Any, Dict, Optional
from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult
from models import Action, Observation, State

class DevOpsIncidentEnv(EnvClient[Action, Observation, State]):
    """Client for DevOps Incident Response OpenEnv."""
    
    def __init__(
        self,
        base_url: str = "https://arijit-07-devops-incident-response.hf.space",
        connect_timeout_s: float = 10.0,
        message_timeout_s: float = 60.0,
        max_message_size_mb: float = 100.0,
        provider: Optional[Any] = None,
        mode: Optional[str] = None,
    ):
        super().__init__(
            base_url=base_url,
            connect_timeout_s=connect_timeout_s,
            message_timeout_s=message_timeout_s,
            max_message_size_mb=max_message_size_mb,
            provider=provider,
            mode=mode,
        )

    def _step_payload(self, action: Action) -> Dict[str, Any]:
        """Convert Action to server payload."""
        return action.model_dump()

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[Observation]:
        """Convert server response to StepResult[Observation]."""
        return StepResult(
            observation=Observation(**payload.get("observation", {})),
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> State:
        """Convert server state to State model."""
        return State(**payload)

from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from env import DevOpsIncidentEnv
from models import Action, ActionType, Observation, StepResult, State

app = FastAPI(
    title="DevOps Incident Response — OpenEnv",
    description=(
        "An OpenEnv-compliant RL environment where AI agents diagnose and remediate "
        "production software incidents across a simulated microservices architecture. "
        "Four tasks: easy (OOM), medium (cascade), hard (silent corruption), "
        "bonus (dual simultaneous failure)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_TASKS = ("easy", "medium", "hard", "bonus")
_env: Optional[DevOpsIncidentEnv] = None


class ResetRequest(BaseModel):
    task_id: str = "easy"
    seed: Optional[int] = None


@app.get("/health")
def health():
    return {"status": "ok", "env": "devops-incident-response", "version": "1.0.0"}


@app.post("/reset", response_model=Observation)
def reset(req: ResetRequest):
    global _env
    if req.task_id not in VALID_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"task_id must be one of {VALID_TASKS}. Got: {req.task_id}",
        )
    _env = DevOpsIncidentEnv(task_id=req.task_id, seed=req.seed)
    return _env.reset()


@app.post("/step", response_model=StepResult)
def step(action: Action):
    if _env is None:
        raise HTTPException(status_code=400, detail="Call /reset before /step")
    return _env.step(action)


@app.get("/state", response_model=State)
def state():
    if _env is None:
        raise HTTPException(status_code=400, detail="Call /reset before /state")
    return _env.state()


@app.get("/tasks")
def list_tasks():
    return {
        "tasks": [
            {
                "id": "easy",
                "name": "Single Service OOM",
                "difficulty": "easy",
                "max_steps": 15,
                "description": "One service crash-loops from a memory leak. Which service varies by seed.",
            },
            {
                "id": "medium",
                "name": "Cascading Multi-Service Failure",
                "difficulty": "medium",
                "max_steps": 20,
                "description": (
                    "Bad deployment causes connection pool exhaustion cascading through 3 services. "
                    "One red-herring alert included."
                ),
            },
            {
                "id": "hard",
                "name": "Silent Data Corruption",
                "difficulty": "hard",
                "max_steps": 25,
                "description": (
                    "No error-rate alerts fire. Signals are WARN-level logs and a business metric anomaly. "
                    "Requires rollback + on-call alert for full credit."
                ),
            },
            {
                "id": "bonus",
                "name": "Simultaneous Dual Failure",
                "difficulty": "hard",
                "max_steps": 25,
                "description": (
                    "Two independent failures at once: disk full on log aggregator + "
                    "model reload CPU loop on ml-inference. Both must be fixed for full credit."
                ),
            },
        ]
    }


@app.get("/validate")
def validate():
    """
    Self-validation endpoint for judges.
    Runs a quick episode on each task and confirms graders return [0.0, 1.0].
    """
    import random
    from graders.grader import grade_episode
    results = []
    for task_id in VALID_TASKS:
        try:
            env = DevOpsIncidentEnv(task_id=task_id, seed=42)
            env.reset()
            done = False
            rng = random.Random(7)
            steps = 0
            import random as _random
            while not done and steps < 30:
                action = Action(action_type=_random.choice(list(ActionType)))
                result = env.step(action)
                done = result.done
                steps += 1
            s = env.state()
            score = grade_episode(
                task_id, s.action_history, s.ground_truth_root_cause,
                s.ground_truth_fix, s.incident_resolved, s.total_reward,
            )
            results.append({
                "task_id": task_id,
                "score": score,
                "in_range": 0.0 <= score <= 1.0,
                "resolved": s.incident_resolved,
                "steps": steps,
                "status": "ok",
            })
        except Exception as e:
            results.append({"task_id": task_id, "status": "error", "error": str(e)})

    all_ok = all(r.get("status") == "ok" and r.get("in_range") for r in results)
    return {"validation": "passed" if all_ok else "failed", "tasks": results}

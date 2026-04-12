from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from models import Action, ActionType, Observation, StepResult, State
from server.devops_environment import DevOpsEnvironment

# Attempt to load create_web_interface_app, fallback to ordinary FastAPI app
try:
    from openenv.core.env_server import create_web_interface_app
    HAS_WEB_INTERFACE = True
except ImportError:
    HAS_WEB_INTERFACE = False

VALID_TASKS = ("easy", "medium", "hard", "bonus", "security", "database")
_env = DevOpsEnvironment()
app = FastAPI(
    title="DevOps Incident Response — OpenEnv",
    description="An OpenEnv-compliant RL environment",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResetRequest(BaseModel):
    task_id: str = "easy"
    seed: Optional[int] = None


@app.get("/", response_class=HTMLResponse)
def dashboard():
    env_state = None
    if _env._logic is not None:
        try:
            env_state = _env.state
        except Exception:
            pass
    
    task_info = ""
    if env_state:
        task_info = f"""
        <div class="stat">
            <span class="label">Current Task</span>
            <span class="value">{env_state.task_id.upper()}</span>
        </div>
        <div class="stat">
            <span class="label">Step</span>
            <span class="value">{env_state.step} / {env_state.current_observation.max_steps}</span>
        </div>
        <div class="stat">
            <span class="label">Score So Far</span>
            <span class="value">{env_state.info.get('current_score', 0):.3f}</span>
        </div>
        <div class="stat">
            <span class="label">Resolved</span>
            <span class="value">{'YES' if env_state.incident_resolved else 'NO'}</span>
        </div>
        <div class="stat">
            <span class="label">Evidence Gathered</span>
            <span class="value">{len(env_state.current_observation.evidence_log)} items</span>
        </div>
        """
    else:
        task_info = '<div class="stat"><span class="label">Status</span><span class="value">No active episode — call /reset to start</span></div>'
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>DevOps Incident Response — OpenEnv</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="10">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e0e0e0; margin: 0; padding: 2rem; }}
        h1 {{ color: #ff6b35; font-size: 1.8rem; margin-bottom: 0.25rem; }}
        h2 {{ color: #888; font-size: 1rem; font-weight: 400; margin-bottom: 2rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .stat {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 1.25rem; }}
        .label {{ display: block; color: #888; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
        .value {{ display: block; font-size: 1.4rem; font-weight: 600; color: #fff; }}
        .tasks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .task {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 1.25rem; }}
        .task h3 {{ margin: 0 0 0.5rem; color: #ff6b35; font-size: 1rem; }}
        .task p {{ margin: 0; color: #aaa; font-size: 0.85rem; line-height: 1.5; }}
        .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-bottom: 0.5rem; }}
        .easy {{ background: #1a3a1a; color: #4caf50; }}
        .medium {{ background: #3a2a1a; color: #ff9800; }}
        .hard {{ background: #3a1a1a; color: #f44336; }}
        .bonus {{ background: #1a1a3a; color: #9c27b0; }}
        .security {{ background: #3a1a1a; color: #ff5252; }}
        .database {{ background: #1a2c3a; color: #4fc3f7; }}
        .endpoints {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 1.25rem; margin-bottom: 2rem; }}
        .endpoints h3 {{ margin: 0 0 1rem; color: #fff; }}
        .endpoint {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }}
        .method {{ background: #1e3a5f; color: #64b5f6; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; font-family: monospace; }}
        .path {{ color: #81c784; font-family: monospace; font-size: 0.85rem; }}
        .desc {{ color: #888; font-size: 0.8rem; }}
        .footer {{ color: #555; font-size: 0.8rem; text-align: center; margin-top: 2rem; }}
    </style>
</head>
<body>
    <h1>DevOps Incident Response</h1>
    <h2>OpenEnv — Meta x PyTorch x Hugging Face Hackathon Submission</h2>
    
    <div class="grid">
        {task_info}
    </div>
    
    <div class="tasks">
        <div class="task">
            <span class="badge easy">EASY</span>
            <h3>Single Service OOM</h3>
            <p>One service crash-loops from a memory leak. Which service varies by seed. Max 15 steps.</p>
        </div>
        <div class="task">
            <span class="badge medium">MEDIUM</span>
            <h3>Cascading Failure</h3>
            <p>Bad deployment cascades through 3 services. One red-herring alert included. Max 20 steps.</p>
        </div>
        <div class="task">
            <span class="badge hard">HARD</span>
            <h3>Silent Data Corruption</h3>
            <p>All services green. No error alerts. Requires correlating subtle business metric signals. Max 25 steps.</p>
        </div>
        <div class="task">
            <span class="badge bonus">BONUS</span>
            <h3>Dual Simultaneous Failure</h3>
            <p>Two independent failures at once. Both must be fixed for full credit. Max 25 steps.</p>
        </div>
        <div class="task">
            <span class="badge security">SECURITY</span>
            <h3>Security Incident (DDoS)</h3>
            <p>Botnet DDoS and credential stuffing attack. Requires traffic blocking and security escalation. Max 20 steps.</p>
        </div>
        <div class="task">
            <span class="badge database">DATABASE</span>
            <h3>Database Degradation</h3>
            <p>Missing schema index causing slow queries and full table scans. Fix via index creation or rollback. Max 20 steps.</p>
        </div>
    </div>
    
    <div class="endpoints">
        <h3>API Endpoints</h3>
        <div class="endpoint">
            <span class="method">GET</span>
            <span class="path">/health</span>
            <span class="desc">Health check</span>
        </div>
        <div class="endpoint">
            <span class="method">POST</span>
            <span class="path">/reset</span>
            <span class="desc">Start new episode — body: {{"task_id": "easy", "seed": 42}}</span>
        </div>
        <div class="endpoint">
            <span class="method">POST</span>
            <span class="path">/step</span>
            <span class="desc">Take one action — body: Action JSON</span>
        </div>
        <div class="endpoint">
            <span class="method">GET</span>
            <span class="path">/state</span>
            <span class="desc">Full state with ground truth and analytics</span>
        </div>
        <div class="endpoint">
            <span class="method">GET</span>
            <span class="path">/validate</span>
            <span class="desc">Self-validation report for all 4 tasks</span>
        </div>
        <div class="endpoint">
            <span class="method">GET</span>
            <span class="path">/docs</span>
            <span class="desc">Interactive API documentation (Swagger UI)</span>
        </div>
    </div>
    
    <div class="footer">
        Auto-refreshes every 10 seconds &nbsp;|&nbsp; 
        <a href="/docs" style="color:#ff6b35;">API Docs</a> &nbsp;|&nbsp;
        <a href="/validate" style="color:#ff6b35;">Run Validation</a> &nbsp;|&nbsp;
        <a href="/health" style="color:#ff6b35;">Health Check</a>
    </div>
</body>
</html>"""
    return html


@app.get("/health")
def health():
    return {"status": "ok", "env": "devops-incident-response", "version": "1.0.0"}


@app.post("/reset", response_model=Observation)
async def reset(req: Optional[ResetRequest] = None):
    if req is None:
        req = ResetRequest()
    if req.task_id not in VALID_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"task_id must be one of {VALID_TASKS}. Got: {req.task_id}",
        )
    return await _env.reset(seed=req.seed, task_id=req.task_id)


@app.post("/step", response_model=StepResult)
async def step(action: Action):
    if _env._logic is None:
        raise HTTPException(status_code=400, detail="Call /reset before /step")
    return await _env.step(action)


@app.get("/state", response_model=State)
def state():
    if _env._logic is None:
        raise HTTPException(status_code=400, detail="Call /reset before /state")
    return _env.state


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
            {
                "id": "security",
                "name": "Security Incident (DDoS)",
                "difficulty": "hard",
                "max_steps": 20,
                "description": (
                    "A botnet is performing a DDoS and credential stuffing attack against the login endpoint. "
                    "The agent must read access logs, diagnose the attack IP range, block the CIDR, and alert the security team."
                ),
            },
            {
                "id": "database",
                "name": "Database Performance Degradation",
                "difficulty": "hard",
                "max_steps": 20,
                "description": (
                    "A recent migration added a user_segment column to the orders table without an index. "
                    "Sequential table scans are spiking DB CPU. Discovered via read_metrics and the slow query log."
                ),
            },
        ]
    }


@app.get("/validate")
def validate():
    import random
    from graders.grader import grade_episode
    results = []
    # Temporarily save existing _logic
    old_logic = _env._logic
    for task_id in VALID_TASKS:
        try:
            import asyncio
            # Wait! Since we are in a sync endpoint, validating by instantiating the logic directly
            from env import DevOpsIncidentEnv as LogicClass
            env_logic = LogicClass(task_id=task_id, seed=42)
            env_logic.reset()
            done = False
            steps = 0
            import random as _random
            while not done and steps < 30:
                action = Action(action_type=_random.choice(list(ActionType)))
                result = env_logic.step(action)
                done = result.done
                steps += 1
            s = env_logic.state()
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

    _env._logic = old_logic
    all_ok = all(r.get("status") == "ok" and r.get("in_range") for r in results)
    return {"validation": "passed" if all_ok else "failed", "tasks": results}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Independent environment instance for this connection
    ws_env = DevOpsEnvironment()
    
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")
            
            print(f"WebSocket received: {data}")
            
            if command == "reset":
                task_id = data.get("task_id", "easy")
                seed = data.get("seed")
                obs = await ws_env.reset(seed=seed, task_id=task_id)
                await websocket.send_json({
                    "type": "observation",
                    "data": obs.model_dump() if hasattr(obs, "model_dump") else obs.dict()
                })
                
            elif command == "step":
                if ws_env._logic is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Call reset before step"
                    })
                    continue
                    
                action_data = data.get("action", {})
                try:
                    action = Action(**action_data)
                    step_result = await ws_env.step(action)
                    await websocket.send_json({
                        "type": "step_result",
                        "data": {
                            "observation": step_result.observation.model_dump() if hasattr(step_result.observation, "model_dump") else step_result.observation.dict(),
                            "reward": step_result.reward,
                            "done": step_result.done,
                            "info": step_result.info
                        }
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
                    
            elif command == "state":
                if ws_env._logic is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Call reset before state"
                    })
                    continue
                    
                state = ws_env.state
                await websocket.send_json({
                    "type": "state",
                    "data": state.model_dump() if hasattr(state, "model_dump") else state.dict()
                })
                
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unrecognized command: {command}"
                })
                
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
        await websocket.close()


from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from models import Action, ActionType, Observation, StepResult, State
from server.devops_environment import DevOpsEnvironment
from collections import deque
from datetime import datetime
import uuid
import statistics
from generator.incident_factory import IncidentFactory
from curriculum import CurriculumEngine
from multi_agent import DualAgentSession

_factory = IncidentFactory()
curriculum_engine = CurriculumEngine()
multi_agent_sessions: dict = {}

episode_history = deque(maxlen=1000)

def track_episode(state_obj: State):
    from graders.grader import grade_episode
    score = grade_episode(
        task_id=state_obj.task_id,
        action_history=state_obj.action_history,
        ground_truth_root_cause=state_obj.ground_truth_root_cause,
        ground_truth_fix=state_obj.ground_truth_fix,
        incident_resolved=state_obj.incident_resolved,
        total_reward=state_obj.total_reward
    )
    
    info_actions = {"read_logs", "read_metrics", "read_runbook", "search_logs"}
    info_count = 0
    diag_step = None
    
    for act in state_obj.action_history:
        at = act["action"].get("action_type")
        if at in info_actions:
            info_count += 1
        if at == "diagnose" and diag_step is None:
            diag_step = act["step"]
            
    info_ratio = info_count / len(state_obj.action_history) if state_obj.action_history else 0.0
    
    # Try to extract seed from info or fallback to 42 since seed is lost in State model
    seed = state_obj.info.get("seed", 42)
    
    record = {
        "episode_id": state_obj.episode_id or str(uuid.uuid4()),
        "task_id": state_obj.task_id,
        "seed": seed,
        "steps_taken": state_obj.step,
        "incident_resolved": state_obj.incident_resolved,
        "final_score": float(score),
        "steps_to_diagnosis": diag_step,
        "info_gathering_ratio": float(info_ratio),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    episode_history.append(record)


# Attempt to load create_web_interface_app, fallback to ordinary FastAPI app
try:
    from openenv.core.env_server import create_web_interface_app
    HAS_WEB_INTERFACE = True
except ImportError:
    HAS_WEB_INTERFACE = False

VALID_TASKS = ("easy", "medium", "hard", "bonus", "security", "database", "failover")
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


class CurriculumRecordRequest(BaseModel):
    task_id: str
    score: float


class MultiAgentResetRequest(BaseModel):
    task_id: str
    seed: int = 42


class AgentAStepRequest(BaseModel):
    finding: str


@app.get("/", response_class=HTMLResponse)
def dashboard():
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ARIA — DevOps Incident Response | OpenEnv</title>
    <meta charset="utf-8">
    <style>
        :root {{
            --bg: #0d1117;
            --accent: #58a6ff;
            --card-bg: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
            --grey: #8b949e;
            --purple: #bc8cff;
            --blue: #79c0ff;
            --teal: #7ee787;
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: var(--bg); color: var(--text); margin: 0; padding: 2rem; line-height: 1.5; }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        /* Layout */
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 3rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
        section {{ margin-bottom: 4rem; }}
        h1, h2, h3 {{ margin: 0; }}
        .section-title {{ font-size: 1.4rem; font-weight: 600; color: #fff; margin-bottom: 0.5rem; }}
        .section-subtitle {{ font-size: 0.95rem; color: var(--grey); margin-bottom: 1.5rem; }}

        /* Header */
        .brand h1 {{ font-size: 2.5rem; letter-spacing: -1px; color: #fff; }}
        .brand h2 {{ font-size: 1.1rem; color: var(--accent); font-weight: 500; margin-top: -5px; }}
        .brand p {{ font-size: 0.85rem; color: var(--grey); margin-top: 5px; }}
        .status-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; background: #1f242c; border: 1px solid var(--border); }}
        .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
        .status-live {{ background: var(--green); box-shadow: 0 0 8px var(--green); }}
        .status-down {{ background: var(--red); box-shadow: 0 0 8px var(--red); }}

        /* Grid & Cards */
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; margin-bottom: 0.75rem; text-transform: uppercase; }}

        /* Task Badges */
        .bg-green {{ background: rgba(63, 185, 80, 0.15); color: var(--green); border: 1px solid rgba(63, 185, 80, 0.3); }}
        .bg-yellow {{ background: rgba(210, 153, 34, 0.15); color: var(--yellow); border: 1px solid rgba(210, 153, 34, 0.3); }}
        .bg-orange {{ background: rgba(255, 165, 0, 0.15); color: #ffa500; border: 1px solid rgba(255, 165, 0, 0.3); }}
        .bg-red {{ background: rgba(248, 81, 73, 0.15); color: var(--red); border: 1px solid rgba(248, 81, 73, 0.3); }}
        .bg-purple {{ background: rgba(188, 140, 255, 0.15); color: var(--purple); border: 1px solid rgba(188, 140, 255, 0.3); }}
        .bg-blue {{ background: rgba(121, 192, 255, 0.15); color: var(--blue); border: 1px solid rgba(121, 192, 255, 0.3); }}
        .bg-teal {{ background: rgba(126, 231, 135, 0.15); color: var(--teal); border: 1px solid rgba(126, 231, 135, 0.3); }}
        .bg-grey {{ background: rgba(139, 148, 158, 0.15); color: var(--grey); border: 1px solid rgba(139, 148, 158, 0.3); }}

        .task-name {{ font-size: 1rem; font-weight: 600; color: #fff; margin-bottom: 0.4rem; }}
        .task-desc {{ font-size: 0.85rem; color: var(--grey); line-height: 1.4; }}
        .task-meta {{ font-size: 0.75rem; color: #58a6ff; font-family: monospace; margin-top: 10px; }}

        /* Table */
        .table-container {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; background: #21262d; padding: 12px 16px; font-size: 0.75rem; text-transform: uppercase; color: var(--grey); border-bottom: 1px solid var(--border); }}
        td {{ padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
        .stars {{ font-size: 1rem; letter-spacing: 2px; }}
        .star-gold {{ color: #ffd700; }}
        .star-silver {{ color: #c0c0c0; }}
        .star-bronze {{ color: #cd7f32; }}
        .star-empty {{ color: #484f58; }}

        .progress-wrap {{ display: flex; align-items: center; gap: 10px; width: 120px; }}
        .progress-bg {{ flex: 1; height: 6px; background: #30363d; border-radius: 3px; overflow: hidden; }}
        .progress-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }}
        .score-val {{ font-family: monospace; font-size: 0.8rem; color: var(--grey); min-width: 35px; }}

        .pill {{ padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 700; }}
        .pill-next {{ background: rgba(63, 185, 80, 0.2); color: var(--green); }}
        .pill-scaffold {{ background: rgba(248, 81, 73, 0.2); color: var(--red); }}

        /* Generator */
        .generator-input {{ display: flex; gap: 12px; margin-bottom: 2rem; }}
        .input-seed {{ background: #0d1117; border: 1px solid var(--border); color: #fff; padding: 8px 16px; border-radius: 6px; width: 120px; font-family: monospace; }}
        .btn {{ background: #21262d; border: 1px solid var(--border); color: #c9d1d9; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.9rem; }}
        .btn:hover {{ background: #30363d; border-color: #8b949e; }}
        .btn-primary {{ background: var(--accent); color: #fff; border: none; }}
        .btn-primary:hover {{ background: #79c0ff; }}

        .result-panel {{ background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; display: none; }}
        .res-top {{ display: flex; align-items: center; gap: 12px; margin-bottom: 1rem; }}
        .res-body {{ background: #161b22; border: 1px solid #30363d; padding: 1rem; border-radius: 6px; margin: 1rem 0; color: #c9d1d9; }}
        .res-tags {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .tag-pill {{ background: #21262d; border: 1px solid var(--border); padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; color: #8b949e; }}

        /* Dual Agent */
        .diagram-box {{ background: #010409; border: 1px solid var(--border); padding: 1.5rem; border-radius: 8px; font-family: monospace; color: #79c0ff; line-height: 1.2; overflow-x: auto; margin-bottom: 1.5rem; }}

        /* Quick Start */
        .code-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
        .code-box {{ background: #161b22; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
        .code-header {{ background: #21262d; padding: 8px 16px; font-size: 0.8rem; font-weight: 600; color: var(--grey); border-bottom: 1px solid var(--border); }}
        pre {{ margin: 0; padding: 1rem; font-size: 0.85rem; color: #d1d5da; overflow-x: auto; }}

        /* Footer */
        footer {{ border-top: 1px solid var(--border); padding-top: 2rem; margin-top: 4rem; text-align: center; }}
        .footer-links {{ display: flex; justify-content: center; gap: 20px; margin-bottom: 1rem; font-size: 0.9rem; }}
        .footer-text {{ font-size: 0.8rem; color: var(--grey); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>ARIA</h1>
                <h2>Adaptive Reward & Incident Architecture</h2>
                <p>DevOps Incident Response · OpenEnv · Meta × PyTorch × HuggingFace Hackathon</p>
            </div>
            <div style="text-align: right;">
                <div class="status-pill">
                    <div id="health-dot" class="status-dot"></div>
                    <span id="health-text">LOADING...</span>
                </div>
                <div class="mt-2" style="font-size: 0.9rem;">
                    <a href="/docs">Docs</a> &nbsp;|&nbsp; <a href="/validate">Validate</a>
                </div>
            </div>
        </header>

        <section id="environment">
            <h3 class="section-title">Environment — 7 Tasks</h3>
            <div class="grid">
                <div class="card">
                    <span class="badge bg-green">EASY</span>
                    <div class="task-name">Single Service OOM</div>
                    <div class="task-desc">One service crash-loops from a memory leak. Varies by seed.</div>
                    <div class="task-meta">max_steps: 15</div>
                </div>
                <div class="card">
                    <span class="badge bg-yellow">MEDIUM</span>
                    <div class="task-name">Cascading Failure</div>
                    <div class="task-desc">Bad deployment cascades through 3 services + red-herring.</div>
                    <div class="task-meta">max_steps: 20</div>
                </div>
                <div class="card">
                    <span class="badge bg-orange">HARD</span>
                    <div class="task-name">Silent Data Corruption</div>
                    <div class="task-desc">No alerts. Signal in WARN logs and business metric slippage.</div>
                    <div class="task-meta">max_steps: 25</div>
                </div>
                <div class="card">
                    <span class="badge bg-red">BONUS</span>
                    <div class="task-name">Dual Simultaneous Failure</div>
                    <div class="task-desc">Two independent failures at once. Both must be fixed.</div>
                    <div class="task-meta">max_steps: 25</div>
                </div>
                <div class="card">
                    <span class="badge bg-purple">SECURITY</span>
                    <div class="task-name">Security Incident (DDoS)</div>
                    <div class="task-desc">Botnet DDoS + credential stuffing. CIDR block required.</div>
                    <div class="task-meta">max_steps: 20</div>
                </div>
                <div class="card">
                    <span class="badge bg-blue">DATABASE</span>
                    <div class="task-name">Database Degradation</div>
                    <div class="task-desc">Missing schema index causing DB CPU spike and slow queries.</div>
                    <div class="task-meta">max_steps: 20</div>
                </div>
                <div class="card">
                    <span class="badge bg-teal">FAILOVER</span>
                    <div class="task-name">Multi-Region Failover</div>
                    <div class="task-desc">Region failure. Escalate or failover selective services.</div>
                    <div class="task-meta">max_steps: 25</div>
                </div>
                <div class="card" style="border-style: dashed;">
                    <span class="badge bg-grey">GENERATED</span>
                    <div class="task-name">Procedural Incident</div>
                    <div class="task-desc">Seed-based procedural incidents. Infinite unique scenarios.</div>
                    <div class="task-meta">max_steps: 20</div>
                </div>
            </div>
        </section>

        <section id="curriculum">
            <h3 class="section-title">Curriculum Engine</h3>
            <p class="section-subtitle">Adapts training difficulty to agent performance</p>
            <div id="curriculum-container">
                <div class="text-grey" style="padding: 2rem; text-align: center;">Loading curriculum data...</div>
            </div>
            <p class="text-grey" style="font-size: 0.8rem; margin-top: 15px;">
                Feed your training loop: <span class="font-mono">POST /curriculum/record</span> with <span class="font-mono">{{"task_id", "score"}}</span>
            </p>
        </section>

        <section id="generator">
            <h3 class="section-title">Incident Generator</h3>
            <p class="section-subtitle">Procedural incidents — infinite unique scenarios from seeds</p>
            <div class="generator-input">
                <input type="number" id="seed-input" class="input-seed" value="42">
                <button onclick="generate()" class="btn btn-primary">Generate Incident ▶</button>
            </div>
            <div id="gen-result" class="result-panel">
                <div class="res-top">
                    <span id="res-id" class="badge bg-grey font-mono" style="padding: 4px 10px; font-size: 0.85rem;"></span>
                    <span id="res-mode" class="badge"></span>
                    <span id="res-sev" class="badge"></span>
                    <div class="progress-wrap" style="width: 150px;">
                        <div class="progress-bg"><div id="res-diff-bar" class="progress-fill"></div></div>
                    </div>
                </div>
                <div id="res-affected" style="font-weight: 600; font-size: 1rem; color: #fff;"></div>
                <div id="res-desc" class="res-body"></div>
                <div id="res-noise-label" style="font-size: 0.8rem; color: var(--grey); margin-bottom: 8px;">Noise alerts:</div>
                <div id="res-noise" class="res-tags"></div>
                <div class="mt-2" style="font-size: 0.8rem; color: var(--grey); font-family: monospace; border-top: 1px solid var(--border); padding-top: 1rem;">
                    POST /reset {{"task_id":"generated","seed":<span id="res-seed-confirm"></span>}}
                </div>
            </div>
        </section>

        <section id="multi-agent">
            <h3 class="section-title">Dual-Agent Mode</h3>
            <p class="section-subtitle">Split observability — Observer sees logs, Responder sees metrics</p>
            <div class="diagram-box">
┌──────────────────┐   share_finding   ┌──────────────────┐
│  AGENT A         │ ────────────────▶ │  AGENT B         │
│  Observer        │                   │  Responder       │
│                  │                   │                  │
│  Sees:           │                   │  Sees:           │
│  · alerts        │                   │  · cpu/memory    │
│  · logs          │                   │  · error_rate    │
│  · evidence      │                   │  · dependencies  │
└──────────────────┘                   └──────────────────┘
         │                                      ▲
         └──────── Shared Findings Log ─────────┘
            </div>
            <button onclick="startMultiAgent()" class="btn btn-primary">Start Dual-Agent Session (easy task)</button>
            <div id="multi-agent-result" class="result-panel mt-2">
                <div id="ma-session" class="font-mono" style="color: var(--teal); margin-bottom: 10px;"></div>
                <div class="code-box">
                    <pre id="ma-hint" style="font-size: 0.8rem; color: #8b949e;"></pre>
                </div>
            </div>
        </section>

        <section id="quick-start">
            <h3 class="section-title">Quick Start</h3>
            <div class="code-grid">
                <div class="code-box">
                    <div class="code-header">Single Agent</div>
                    <pre># Install
pip install openenv

# Reset environment
curl -X POST .../reset \\
  -H "Content-Type: application/json" \\
  -d '{{"task_id":"easy","seed":42}}'

# Take an action
curl -X POST .../step \\
  -d '{{"action_type":"read_logs",
       "service":"payment-service"}}'

# Check curriculum
curl .../curriculum/next</pre>
                </div>
                <div class="code-box">
                    <div class="code-header">Dual Agent</div>
                    <pre># Start session
curl -X POST .../multi-agent/reset \\
  -d '{{"task_id":"easy","seed":42}}'

# Agent A shares finding
curl -X POST .../multi-agent/step/a/{{id}} \\
  -d '{{"finding":"payment-service OOM"}}'

# Agent B responds
curl -X POST .../multi-agent/step/b/{{id}} \\
  -d '{{"action_type":"restart_service",
       "service":"payment-service"}}'</pre>
                </div>
            </div>
        </section>

        <footer>
            <div class="footer-links">
                <a href="/docs">Docs</a>
                <a href="/validate">Validate</a>
                <a href="/metrics">Metrics</a>
                <a href="/leaderboard">Leaderboard</a>
                <a href="https://github.com/Twilight-13/devops-incident-response">GitHub</a>
                <a href="https://huggingface.co/spaces/Arijit-07/devops-incident-response">HuggingFace Space</a>
            </div>
            <div class="footer-text">
                Built solo for Meta × PyTorch × HuggingFace OpenEnv Hackathon · Bangalore April 25–26
            </div>
        </footer>
    </div>

    <script>
        // Health Check
        async function checkHealth() {{
            const dot = document.getElementById('health-dot');
            const txt = document.getElementById('health-text');
            try {{
                const r = await fetch('/health');
                if (r.ok) {{
                    dot.className = 'status-dot status-live';
                    txt.innerText = '● LIVE';
                    txt.style.color = 'var(--green)';
                }} else {{ throw new Error(); }}
            }} catch(e) {{
                dot.className = 'status-dot status-down';
                txt.innerText = '● DOWN';
                txt.style.color = 'var(--red)';
            }}
        }}

        // Curriculum
        async function loadCurriculum() {{
            const container = document.getElementById('curriculum-container');
            try {{
                const r = await fetch('/curriculum/status');
                const data = await r.json();

                if (Object.keys(data.tasks).length === 0) {{
                    container.innerHTML = '<div class="card" style="text-align:center; color:var(--grey);">No episodes recorded yet. Run episodes to see curriculum data.</div>';
                    return;
                }}

                let html = '<div class="table-container"><table><thead><tr><th>Task</th><th>Mastery</th><th>Avg Score</th><th>Status</th></tr></thead><tbody>';

                for (const [id, task] of Object.entries(data.tasks)) {{
                    const score = task.rolling_avg || 0;
                    const color = score < 0.3 ? 'var(--red)' : (score < 0.6 ? 'var(--yellow)' : 'var(--green)');
                    const mastery = task.mastery_level || 0;

                    let stars = '';
                    if (mastery === 0) stars = '<span class="star-empty">☆☆☆</span>';
                    else if (mastery === 1) stars = '<span class="star-bronze">★</span><span class="star-empty">☆☆</span>';
                    else if (mastery === 2) stars = '<span class="star-silver">★★</span><span class="star-empty">☆</span>';
                    else stars = '<span class="star-gold">★★★</span>';

                    let status = '';
                    if (id === data.recommended_task) status += '<span class="pill pill-next">NEXT</span> ';
                    if (task.scaffold_needed) status += '<span class="pill pill-scaffold">SCAFFOLD</span>';

                    html += `<tr>
                        <td class="font-mono" style="color:#fff; text-transform:capitalize;">${{id}}</td>
                        <td class="stars">${{stars}}</td>
                        <td>
                            <div class="progress-wrap">
                                <div class="progress-bg"><div class="progress-fill" style="width:${{score * 100}}%; background:${{color}};"></div></div>
                                <span class="score-val">${{score.toFixed(2)}}</span>
                            </div>
                        </td>
                        <td>${{status}}</td>
                    </tr>`;
                }}
                html += '</tbody></table></div>';
                container.innerHTML = html;
            }} catch(e) {{
                container.innerHTML = '<div class="card" style="text-align:center; color:var(--red);">Failed to fetch curriculum status.</div>';
            }}
        }}

        // Incident Generator
        async function generate() {{
            const seed = document.getElementById('seed-input').value;
            const res = await fetch(`/generate/preview?seed=${{seed}}`);
            const data = await res.json();

            document.getElementById('gen-result').style.display = 'block';
            document.getElementById('res-id').innerText = `INC-${{seed.toString().padStart(5, '0')}}`;
            document.getElementById('res-seed-confirm').innerText = seed;
            document.getElementById('res-affected').innerText = `Affected service: ${{data.affected_service}}`;
            document.getElementById('res-desc').innerText = data.description;

            const modeBadge = document.getElementById('res-mode');
            const modeColors = {{ oom: 'bg-red', cascade: 'bg-yellow', corruption: 'bg-orange', security: 'bg-purple', database: 'bg-blue', network_partition: 'bg-teal' }};
            modeBadge.innerText = data.failure_mode;
            modeBadge.className = 'badge ' + (modeColors[data.failure_mode] || 'bg-grey');

            const sevBadge = document.getElementById('res-sev');
            const sevColors = {{ sev1: 'bg-red', sev2: 'bg-yellow', sev3: 'bg-green' }};
            sevBadge.innerText = data.severity;
            sevBadge.className = 'badge ' + (sevColors[data.severity] || 'bg-grey');

            const diffBar = document.getElementById('res-diff-bar');
            diffBar.style.width = (data.difficulty_score * 100) + '%';
            diffBar.style.background = data.difficulty_score < 0.3 ? 'var(--green)' : (data.difficulty_score < 0.6 ? 'var(--yellow)' : 'var(--red)');

            const noise = document.getElementById('res-noise');
            if (data.noise_alerts.length === 0) {{
                noise.innerHTML = '<span class="text-grey" style="font-size:0.8rem;">None</span>';
            }} else {{
                noise.innerHTML = data.noise_alerts.map(n => `<span class="tag-pill">${{n}}</span>`).join("");
            }}

            document.getElementById('gen-result').scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }}

        // Multi Agent
        async function startMultiAgent() {{
            try {{
                const r = await fetch('/multi-agent/reset', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ task_id: 'easy', seed: 42 }})
                }});
                const data = await r.json();

                const panel = document.getElementById('multi-agent-result');
                panel.style.display = 'block';
                document.getElementById('ma-session').innerText = `Session ID: ${{data.session_id}}`;
                document.getElementById('ma-hint').innerText =
                    `Agent A: POST /multi-agent/step/a/${{data.session_id}}\\n` +
                    `         body: {{"finding": "your observation here"}}\\n\\n` +
                    `Agent B: POST /multi-agent/step/b/${{data.session_id}}\\n` +
                    `         body: {{"action_type": "...", ...}}\\n\\n` +
                    `Status:  GET  /multi-agent/state/${{data.session_id}}`;
            }} catch(e) {{
                alert('Dual-Agent session initiation failed. Verify /multi-agent endpoints.');
            }}
        }}

        // Init
        checkHealth();
        loadCurriculum();
        setInterval(loadCurriculum, 15000);
    </script>
</body>
</html>"""
    return html


@app.get("/health")
def health():
    """
    Health check endpoint.

    Returns a simple status object confirming the server is running.

    Returns:
        {"status": "ok", "env": "devops-incident-response", "version": "2.0.0"}
    """
    return {"status": "ok", "env": "devops-incident-response", "version": "2.0.0"}


@app.get("/about")
def about():
    """
    Full environment metadata for LLM judges and researchers.

    Returns a comprehensive description of the ARIA environment including
    task count, action types, feature flags, training metadata, reward
    design philosophy, and links to the live space, trained model, and docs.

    Returns:
        JSON object with name, version, description, themes, task/action counts,
        feature descriptions, training info, reward design, and links.
    """
    return {
        "name": "ARIA — DevOps Incident Response",
        "version": "2.0.0",
        "description": (
            "OpenEnv-compliant RL environment for production incident response. "
            "AI agents diagnose and remediate software incidents across 7 task types "
            "using 14 actions with dense reward shaping."
        ),
        "themes": [
            "World Modeling: Professional Tasks",
            "Self-Improvement",
            "Multi-Agent Interactions",
        ],
        "tasks": 8,
        "action_types": 14,
        "features": {
            "curriculum_engine": "Adaptive difficulty based on agent performance",
            "incident_generator": "Procedural incidents from seeds (0-99999)",
            "dual_agent_mode": "Split observability — Observer + Responder",
        },
        "training": {
            "model": "Llama-3.2-3B-Instruct",
            "algorithm": "GRPO",
            "framework": "HuggingFace TRL + Unsloth",
            "episodes": 140,
            "adapter_url": "https://huggingface.co/Arijit-07/aria-devops-llama3b",
        },
        "reward_design": {
            "type": "dense",
            "range": [0.001, 0.999],
            "anti_gaming": [
                "collateral_damage_penalty",
                "blind_remediation_penalty",
                "semantic_diagnosis_matching",
            ],
            "efficiency_bonus": True,
        },
        "links": {
            "space": "https://arijit-07-devops-incident-response.hf.space",
            "model": "https://huggingface.co/Arijit-07/aria-devops-llama3b",
            "github": "https://github.com/Twilight-13/devops-incident-response",
            "docs": "https://arijit-07-devops-incident-response.hf.space/docs",
        },
    }


@app.get("/generate/preview")
def preview_incident(seed: int = 42):
    """
    Preview a procedurally generated incident without starting an episode.

    Uses ARIA's IncidentFactory to generate a deterministic incident description
    from the given integer seed. Same seed always produces the same incident.

    Args:
        seed: Integer seed in range 0–99999 (default: 42)

    Returns:
        Incident object with: failure_mode, severity, affected_service,
        description, noise_alerts, difficulty_score
    """
    return _factory.generate(seed)


@app.post("/reset", response_model=Observation)
async def reset(req: Optional[ResetRequest] = None):
    """
    Start a new episode.

    Initializes the environment for the specified task and seed.
    Same seed always produces the same episode (deterministic).

    Args:
        task_id: One of easy/medium/hard/bonus/security/database/failover/generated
        seed: Integer seed for reproducibility (optional, random if not provided)

    Returns:
        Observation with: services, active_alerts, recent_logs,
        service_dependencies, evidence_log, sla_status, available_runbooks
    """
    if req is None:
        req = ResetRequest()
    if req.task_id not in VALID_TASKS and req.task_id != "generated":
        raise HTTPException(
            status_code=400,
            detail=f"task_id must be one of {VALID_TASKS} or 'generated'. Got: {req.task_id}",
        )
    return await _env.reset(seed=req.seed, task_id=req.task_id)


@app.post("/step", response_model=StepResult)
async def step(action: Action):
    """
    Take one action in the current episode.

    Must call /reset first. Accepts any of the 14 action types with their
    corresponding parameters. Returns the new observation, reward signal,
    and done flag.

    Args:
        action_type: One of diagnose/read_logs/read_metrics/read_runbook/
                     search_logs/restart_service/rollback/scale_up/
                     alert_oncall/acknowledge/noop/block_ip_range/
                     create_index/failover
        service: Target service name (required for most actions)
        root_cause: Diagnosis string (required for diagnose action)
        runbook: Runbook filename (required for read_runbook)
        version: Target version (required for rollback)
        reason: Reason string (required for alert_oncall)
        ip_range: CIDR range (required for block_ip_range)
        table: Table name (required for create_index)
        column: Column name (required for create_index)
        target_region: Target region (required for failover)

    Returns:
        StepResult with: observation (new state), reward (float), done (bool), info (dict)

    Side effects:
        On done=True, records the episode in the leaderboard and metrics history.
    """
    if _env._logic is None:
        raise HTTPException(status_code=400, detail="Call /reset before /step")
    res = await _env.step(action)
    if res.done:
        track_episode(_env.state)
    return res


@app.get("/state", response_model=State)
def state():
    """
    Return the full current environment state including ground truth.

    Unlike /step which returns partial observations, /state reveals the
    ground truth root cause, fix, and full action history. Useful for
    evaluation and debugging.

    Returns:
        State with: all Observation fields plus ground_truth_root_cause,
        ground_truth_fix, incident_resolved, total_reward, action_history,
        episode_id, task_id, step count
    """
    if _env._logic is None:
        raise HTTPException(status_code=400, detail="Call /reset before /state")
    return _env.state


@app.get("/tasks")
def list_tasks():
    """
    List all 8 tasks with metadata.

    Returns all available task IDs with their name, difficulty, max_steps,
    and description. Use the task_id values in POST /reset to start an episode.

    Returns:
        {"tasks": [...]} — list of 8 task objects (7 curated + 1 procedural)
    """
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
            {
                "id": "failover",
                "name": "Multi-Region Failover",
                "difficulty": "hard",
                "max_steps": 25,
                "description": (
                    "A primary datacenter region (us-east-1) is degraded due to a network partition. "
                    "The agent must correctly identify which services support automatic multi-region failover "
                    "and which do not. Failing over the wrong services causes severe data inconsistency penalties."
                ),
            },
            {
                "id": "generated",
                "name": "Procedural Incident",
                "difficulty": "variable",
                "max_steps": 20,
                "description": "A seed-based procedural incident generated by ARIA. Deterministic and reproducible.",
            },
        ]
    }


@app.get("/validate")
def validate():
    """
    Self-validation endpoint — runs all 7 curated tasks and returns per-task scores.

    Instantiates each task environment with seed=42 and runs a random agent
    for up to 30 steps. Verifies that: the environment runs without errors,
    scores stay within [0.0, 1.0], and grading completes successfully.

    This endpoint is safe to call at any time — it does not affect the current
    episode state (the active _env._logic is restored after validation).

    Returns:
        {
          "validation": "passed" | "failed",
          "summary": "X/Y tasks passed validation",
          "total_tasks": N,
          "passed": N,
          "tasks": [
            {
              "task_id": "easy",
              "score": 0.12,
              "in_range": true,
              "resolved": false,
              "steps": 15,
              "status": "ok"
            }, ...
          ]
        }
    """
    import random
    from graders.grader import grade_episode
    results = []
    old_logic = _env._logic
    for task_id in VALID_TASKS:
        try:
            import asyncio
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
                "score": round(float(score), 4),
                "in_range": 0.0 <= score <= 1.0,
                "resolved": s.incident_resolved,
                "steps": steps,
                "status": "ok",
            })
        except Exception as e:
            results.append({"task_id": task_id, "status": "error", "error": str(e)})

    _env._logic = old_logic
    passed_count = sum(1 for r in results if r.get("status") == "ok" and r.get("in_range"))
    total_count = len(results)
    all_ok = passed_count == total_count
    return {
        "validation": "passed" if all_ok else "failed",
        "summary": f"{passed_count}/{total_count} tasks passed validation",
        "total_tasks": total_count,
        "passed": passed_count,
        "tasks": results,
    }


@app.get("/metrics")
def get_metrics():
    """
    Aggregate episode statistics across all completed episodes.

    Statistics are computed in-memory and reset when the server restarts.

    Returns:
        {
          "total_episodes": N,
          "overall_avg_score": 0.XX,
          "by_task": {
            "easy": {"count", "avg_score", "max_score", "min_score",
                     "resolution_rate", "avg_steps_to_diagnosis",
                     "avg_info_gathering_ratio"},
            ...
          },
          "last_updated": "ISO timestamp"
        }
    """
    total_episodes = len(episode_history)
    by_task = {}
    total_score = 0.0
    
    if total_episodes == 0:
        return {
            "total_episodes": 0,
            "by_task": {},
            "overall_avg_score": 0.0,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
    for rec in episode_history:
        tid = rec["task_id"]
        if tid not in by_task:
            by_task[tid] = {"scores": [], "resolved": 0, "steps_to_diag": [], "info_ratios": []}
            
        by_task[tid]["scores"].append(rec["final_score"])
        if rec["incident_resolved"]:
            by_task[tid]["resolved"] += 1
        if rec["steps_to_diagnosis"] is not None:
            by_task[tid]["steps_to_diag"].append(rec["steps_to_diagnosis"])
        by_task[tid]["info_ratios"].append(rec["info_gathering_ratio"])
        total_score += rec["final_score"]
        
    out_by_task = {}
    for tid, agg in by_task.items():
        cnt = len(agg["scores"])
        out_by_task[tid] = {
            "count": cnt,
            "avg_score": round(sum(agg["scores"]) / cnt, 3),
            "max_score": round(max(agg["scores"]), 3),
            "min_score": round(min(agg["scores"]), 3),
            "resolution_rate": round(agg["resolved"] / cnt, 3),
            "avg_steps_to_diagnosis": round(sum(agg["steps_to_diag"]) / len(agg["steps_to_diag"]), 1) if agg["steps_to_diag"] else None,
            "avg_info_gathering_ratio": round(sum(agg["info_ratios"]) / len(agg["info_ratios"]), 2) if agg["info_ratios"] else 0.0
        }
        
    return {
        "total_episodes": total_episodes,
        "by_task": out_by_task,
        "overall_avg_score": round(total_score / total_episodes, 3),
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/leaderboard")
def get_leaderboard():
    """
    Top-10 episodes ranked by score (ties broken by fewer steps).

    Returns:
        {"leaderboard": [{"rank", "task_id", "score", "steps", "timestamp"}, ...]}
    """
    sorted_eps = sorted(episode_history, key=lambda x: (x["final_score"], -x["steps_taken"]), reverse=True)
    top_10 = []
    for i, rec in enumerate(sorted_eps[:10]):
        top_10.append({
            "rank": i + 1,
            "task_id": rec["task_id"],
            "score": rec["final_score"],
            "steps": rec["steps_taken"],
            "timestamp": rec["timestamp"]
        })
    return {"leaderboard": top_10}


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
                    if step_result.done:
                        track_episode(ws_env.state)
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


# ─── Multi-Agent Routes ────────────────────────────────────────────────────────

@app.post("/multi-agent/reset")
def multi_agent_reset(body: MultiAgentResetRequest):
    """
    Start a new dual-agent session with split observability.

    Creates two views of the same incident:
    - Agent A (Observer): sees logs and active alerts only
    - Agent B (Responder): sees metrics and service dependencies only

    Args:
        task_id: Task to run (same valid values as POST /reset)
        seed: Deterministic seed (default: 42)

    Returns:
        session_id, agent roles, step instructions, and initial observations
        for both agents.
    """
    session = DualAgentSession(task_id=body.task_id, seed=body.seed)
    multi_agent_sessions[session.session_id] = session
    return {
        "session_id": session.session_id,
        "task_id": body.task_id,
        "seed": body.seed,
        "agent_a_role": "observer — sees logs and alerts only",
        "agent_b_role": "responder — sees metrics and dependencies only",
        "instructions": {
            "agent_a": "POST /multi-agent/step/a/{session_id} body: {\"finding\": \"your observation\"}",
            "agent_b": "POST /multi-agent/step/b/{session_id} body: Action JSON (same schema as POST /step)",
        },
        "observation_a": session.get_observation_a(),
        "observation_b": session.get_observation_b(),
    }


@app.post("/multi-agent/step/a/{session_id}")
def multi_agent_step_a(session_id: str, body: AgentAStepRequest):
    """
    Agent A (Observer) shares a finding with Agent B.

    Agent A sees logs and alerts only. Findings are appended to the shared
    findings log that Agent B can see when deciding its next action.

    Args:
        session_id: Session ID from POST /multi-agent/reset
        finding: Text description of what Agent A observed

    Returns:
        Updated findings log and current Observer-view observation.
    """
    session = multi_agent_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.step_a(body.finding)


@app.post("/multi-agent/step/b/{session_id}")
def multi_agent_step_b(session_id: str, body: Action):
    """
    Agent B (Responder) takes an action in the environment.

    Agent B sees metrics and service dependencies. It receives all findings
    shared by Agent A, then executes an action. Action schema is identical
    to POST /step.

    Args:
        session_id: Session ID from POST /multi-agent/reset
        body: Action object (same schema as POST /step)

    Returns:
        StepResult with reward, done flag, and updated Responder-view observation.
    """
    session = multi_agent_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.step_b(body)


@app.get("/multi-agent/state/{session_id}")
def multi_agent_state(session_id: str):
    """
    Full state for a dual-agent session including both agent perspectives.

    Returns:
        Session state with findings_log, step count, done flag,
        and both Observer and Responder observations.
    """
    session = multi_agent_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get_state()


@app.get("/multi-agent/sessions")
def list_multi_agent_sessions():
    """
    List all active dual-agent sessions.

    Returns:
        List of active sessions with session_id, task_id, current step,
        done flag, and number of findings shared by Agent A.
    """
    return [
        {
            "session_id": s.session_id,
            "task_id": s.task_id,
            "step": s.step_count,
            "done": s.done,
            "findings_count": len(s.findings_log),
        }
        for s in multi_agent_sessions.values()
    ]


# ─── Curriculum Routes ─────────────────────────────────────────────────────────

@app.get("/curriculum/status")
def get_curriculum_status():
    """
    Agent mastery levels across all tasks.

    Returns the curriculum engine's current view of agent performance:
    rolling average score, mastery level (0–3), whether scaffolding is
    needed, and a diagnostic hint per task.

    Returns:
        {"tasks": {"easy": {"rolling_avg", "mastery_level", "scaffold_needed", "hint"}, ...},
         "recommended_task": "easy"}
    """
    return curriculum_engine.get_status()


@app.get("/curriculum/next")
def get_next_curriculum_task():
    """
    Recommended next task for adaptive training.

    Returns the task with the lowest rolling average score among non-mastered
    tasks. Training loops should call this between episodes to implement
    curriculum learning automatically.

    Returns:
        {"recommended_task": "medium", "reasoning": "..."}
    """
    return {
        "recommended_task": curriculum_engine.get_next_curriculum_task(),
        "reasoning": "Lowest rolling average among non-mastered tasks.",
    }


@app.post("/curriculum/record")
def record_curriculum_episode(req: CurriculumRecordRequest):
    """
    Record an episode result to update the curriculum engine.

    Training loops should call this after each episode to keep the
    curriculum engine's rolling averages and mastery levels current.

    Args:
        task_id: Task that was just run
        score: Episode score (float, typically 0.0–1.0)

    Returns:
        {"recorded": true, "new_status": {...}} — updated task status
    """
    try:
        curriculum_engine.record_episode(req.task_id, req.score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "recorded": True,
        "new_status": curriculum_engine.get_status()["tasks"][req.task_id],
    }


@app.get("/curriculum/hint/{task_id}")
def get_curriculum_hint(task_id: str):
    """
    Get a diagnostic hint and scaffold flag for a specific task.

    If an agent is repeatedly failing a task, this returns a structured hint
    explaining what the agent should try (e.g., "read logs before acting").

    Args:
        task_id: One of easy/medium/hard/bonus/security/database/failover

    Returns:
        {"task_id", "hint", "scaffold_needed": bool, "mastery_level": 0–3}
    """
    try:
        return {
            "task_id": task_id,
            "hint": curriculum_engine.get_hint(task_id),
            "scaffold_needed": curriculum_engine.should_scaffold(task_id),
            "mastery_level": curriculum_engine.get_mastery(task_id),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

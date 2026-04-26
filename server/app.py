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

replay_store: dict = {}
replay_counter: int = 0
current_episode_steps: list = []

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


@app.get("/about")
async def about():
    return {
        "name": "ARIA — DevOps Incident Response",
        "version": "2.0.0",
        "description": (
            "OpenEnv-compliant RL environment for production incident "
            "response. AI agents diagnose and remediate software incidents "
            "across 7 task types using 14 actions with dense reward shaping."
        ),
        "tasks": 8,
        "action_types": 14,
        "themes": [
            "World Modeling: Professional Tasks",
            "Self-Improvement: Curriculum Engine",
            "Multi-Agent Interactions: Dual-Agent Mode"
        ],
        "features": {
            "curriculum_engine": "Adaptive difficulty based on agent performance. Promotes when avg > 0.75, scaffolds when avg < 0.30.",
            "incident_generator": "Procedural incidents from seeds 0-99999. 6 failure modes x 8 services x 3 severities.",
            "dual_agent_mode": "Split observability — Observer sees logs/alerts, Responder sees metrics/deps.",
            "reward_shaping": "Dense rewards with collateral damage penalties (-0.15), blind remediation penalties (-0.10), semantic diagnosis matching."
        },
        "training": {
            "model": "Llama-3.1-8B-Instruct",
            "algorithm": "GRPO (Group Relative Policy Optimization)",
            "framework": "HuggingFace TRL + Unsloth",
            "lora_rank": 32,
            "episodes": 160,
            "adapter_3b": "https://huggingface.co/Arijit-07/aria-devops-llama3b",
            "adapter_8b": "https://huggingface.co/Arijit-07/aria-devops-llama8b"
        },
        "reward_design": {
            "type": "dense",
            "range": [0.001, 0.999],
            "gates": {
                "read_logs_correct": 0.15,
                "read_metrics": 0.10,
                "diagnose_full": 0.35,
                "correct_fix": 0.45,
                "alert_oncall": 0.15
            },
            "penalties": {
                "collateral_damage": -0.15,
                "blind_remediation": -0.10,
                "wrong_failover": -0.25,
                "excessive_noop": -0.04
            }
        },
        "links": {
            "space": "https://arijit-07-devops-incident-response.hf.space",
            "docs": "https://arijit-07-devops-incident-response.hf.space/docs",
            "validate": "https://arijit-07-devops-incident-response.hf.space/validate",
            "github": "https://github.com/Twilight-13/devops-incident-response",
            "model_3b": "https://huggingface.co/Arijit-07/aria-devops-llama3b",
            "model_8b": "https://huggingface.co/Arijit-07/aria-devops-llama8b",
            "blog": "https://huggingface.co/blog/Arijit-07/aria-devops-incident-response"
        }
    }



@app.get("/live", response_class=HTMLResponse)
async def live_dashboard():
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ARIA NOC LIVE</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root {{
    --void: #000000;
    --bg: #060914;
    --surface: #0a0f1e;
    --surface2: #0d1628;
    --border: #1a2744;
    --border-bright: #2a4080;
    --blue: #4d9fff;
    --blue-dim: #1a3a6e;
    --cyan: #00d4ff;
    --green: #00ff88;
    --green-dim: #003a1e;
    --yellow: #ffaa00;
    --yellow-dim: #3a2800;
    --red: #ff3355;
    --red-dim: #3a0011;
    --purple: #9d4edd;
    --text: #c8d8f0;
    --text-dim: #4a6080;
    --text-mono: #8ab4d4;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background-color: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    overflow: hidden;
    height: 100vh;
    display: grid;
    grid-template-rows: 48px 1fr 56px;
    grid-template-columns: 28% 44% 28%;
    grid-template-areas: 
      "top top top"
      "left center right"
      "bottom bottom bottom";
  }}

  .scanlines {{
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    pointer-events: none;
    z-index: 9999;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,0,0,0.03) 2px,
      rgba(0,0,0,0.03) 4px
    );
  }}

  .mono {{ font-family: 'Share Tech Mono', monospace; }}
  .uppercase {{ text-transform: uppercase; }}

  #top-bar {{
    grid-area: top;
    background: var(--void);
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 16px;
  }}

  .top-left, .top-center, .top-right {{ display: flex; align-items: center; gap: 12px; }}
  
  .logo {{ font-size: 18px; color: var(--blue); font-weight: bold; }}
  .logo-sub {{ font-size: 10px; color: var(--text-dim); }}
  .separator {{ width: 1px; height: 24px; background: var(--border); }}
  
  .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  .dot-green {{ background: var(--red); animation: livePulse 1.5s infinite; }} 
  .dot-grey {{ background: var(--text-dim); }}
  
  @keyframes livePulse {{
    0% {{ opacity: 0; }}
    50% {{ opacity: 1; }}
    100% {{ opacity: 0; }}
  }}

  .control-label {{ font-size: 9px; color: var(--text-dim); }}
  .terminal-input {{
    background: var(--surface);
    border: 1px solid var(--border-bright);
    color: var(--blue);
    font-family: 'Share Tech Mono', monospace;
    padding: 4px 8px;
    outline: none;
  }}
  .btn-deploy {{
    background: var(--blue-dim);
    border: 1px solid var(--blue);
    color: var(--blue);
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    padding: 6px 16px;
    cursor: pointer;
    transition: 0.2s;
  }}
  .btn-deploy:hover {{ background: var(--blue); color: var(--void); }}

  .step-counter {{ font-size: 16px; color: var(--cyan); }}
  .score-display-small {{ font-size: 20px; font-weight: bold; }}
  .clock {{ font-size: 11px; color: var(--text-dim); }}

  .panel {{
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow: hidden;
  }}
  #left-panel {{ grid-area: left; border-right: 1px solid var(--border); }}
  #center-panel {{ grid-area: center; border-right: 1px solid var(--border); }}
  #right-panel {{ grid-area: right; border-color: var(--purple); }}

  .panel-header {{
    display: flex; align-items: center; gap: 8px; font-size: 9px; color: var(--text-dim); margin-bottom: 8px;
  }}
  .pill {{ background: var(--surface2); padding: 2px 6px; border-radius: 10px; color: var(--text); }}

  #service-list {{ display: flex; flex-direction: column; gap: 8px; overflow-y: auto; flex: 1; }}
  .service-item {{
    height: 52px; padding: 0 12px; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; transition: border-color 0.3s, background 0.3s;
  }}
  .svc-name {{ font-size: 12px; color: var(--text); }}
  .svc-status {{ font-size: 9px; margin-top: 4px; }}
  
  .svc-stats {{ text-align: right; }}
  .svc-stat-line {{ font-size: 11px; }}

  @keyframes statusFlash {{
    0% {{ border-color: var(--text); }}
    100% {{ border-color: inherit; }}
  }}
  @keyframes criticalFlash {{
    0%, 50%, 100% {{ border-color: var(--border); }}
    25%, 75% {{ border-color: var(--red); }}
  }}
  .flash-critical {{ animation: criticalFlash 0.5s ease-in-out; border-color: var(--red) !important; }}
  
  @keyframes resolveFlash {{
    0%, 50%, 100% {{ border-color: var(--border); }}
    25%, 75% {{ border-color: var(--green); }}
  }}
  .flash-resolve {{ animation: resolveFlash 2s ease-in-out; border-color: var(--green) !important; }}

  @keyframes pulseScore {{
    0% {{ transform: scale(1); }}
    50% {{ transform: scale(1.1); }}
    100% {{ transform: scale(1); }}
  }}
  .pulse-score {{ animation: pulseScore 2s ease-in-out; }}

  @keyframes slideInRight {{
    from {{ transform: translateX(20px); opacity: 0; }}
    to {{ transform: translateX(0); opacity: 1; }}
  }}
  @keyframes fadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
  }}

  .center-top {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
  .center-bottom {{ height: 200px; display: flex; flex-direction: column; justify-content: flex-end; }}
  
  #alerts-list {{ display: flex; flex-direction: column; gap: 8px; flex: 1; }}
  .alert-strip {{
    height: 36px; display: flex; align-items: center; gap: 8px; padding-right: 12px; animation: slideInRight 0.3s ease-out;
  }}
  .alert-badge {{
    height: 100%; padding: 0 8px; display: flex; align-items: center; font-size: 9px; font-weight: bold; color: #000;
  }}
  .alert-text {{ font-size: 11px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .no-alerts {{ text-align: center; color: var(--text-dim); margin-top: 40px; animation: livePulse 3s infinite; }}

  .giant-score {{ font-size: 48px; font-weight: bold; text-align: center; margin-bottom: 12px; text-shadow: 0 0 20px currentColor; }}
  .progress-container {{ width: 100%; height: 8px; background: var(--surface); margin-bottom: 8px; }}
  .progress-fill {{ height: 100%; background: linear-gradient(90deg, var(--blue), var(--green)); transition: width 0.5s ease; width: 0%; }}
  .score-stats {{ display: flex; justify-content: space-between; font-size: 10px; color: var(--text-dim); margin-bottom: 16px; }}
  
  .sparkline {{ display: flex; align-items: flex-end; gap: 4px; height: 40px; margin-top: auto; }}
  .spark-bar {{ width: 16px; background: var(--green); animation: slideInRight 0.2s ease-out; position: relative; }}
  .spark-label {{ position: absolute; bottom: -14px; left: 50%; transform: translateX(-50%); font-size: 8px; color: var(--text-dim); }}

  #agent-log {{
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;
  }}
  .log-entry {{ animation: fadeIn 0.2s ease-out; font-size: 11px; line-height: 1.4; }}
  .log-time {{ color: var(--text-dim); margin-right: 8px; }}
  .log-action {{ color: var(--purple); }}
  .log-reward {{ padding-left: 48px; }}
  .log-evidence {{ color: var(--text-dim); font-style: italic; padding-left: 48px; }}
  .log-diagnose {{ color: var(--yellow); }}
  .log-fix {{ color: var(--cyan); }}
  .log-episode-start {{ color: var(--cyan); text-align: center; margin: 8px 0; }}
  .log-episode-end-ok {{ color: var(--green); text-align: center; margin: 8px 0; }}
  .log-episode-end-fail {{ color: var(--red); text-align: center; margin: 8px 0; }}

  #bottom-bar {{
    grid-area: bottom; background: var(--void); border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; padding: 0 16px;
  }}
  .ws-status {{ display: flex; align-items: center; gap: 8px; font-size: 11px; }}
  .tip-text {{ font-size: 11px; color: var(--text-dim); font-style: italic; transition: opacity 0.5s; }}
  .footer-right {{ font-size: 10px; color: var(--text-dim); }}
  
  ::-webkit-scrollbar {{ width: 4px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--border-bright); }}
</style>
</head>
<body>
<div class="scanlines"></div>

<div id="top-bar">
  <div class="top-left">
    <div class="logo mono">▣ ARIA</div>
    <div class="logo-sub uppercase">Incident Response System</div>
    <div class="separator"></div>
    <div class="status-dot dot-grey" id="live-dot"></div>
    <div class="logo-sub mono" id="live-text" style="color: var(--text)">OFFLINE</div>
  </div>
  
  <div class="top-center">
    <div class="control-label uppercase">Active Scenario</div>
    <select class="terminal-input" id="task-select">
      <option value="easy">EASY</option>
      <option value="medium">MEDIUM</option>
      <option value="hard">HARD</option>
      <option value="bonus">BONUS</option>
      <option value="security">SECURITY</option>
      <option value="database">DATABASE</option>
      <option value="failover">FAILOVER</option>
      <option value="generated">GENERATED</option>
    </select>
    <div class="control-label uppercase">Seed:</div>
    <input type="number" class="terminal-input" id="seed-input" value="42" style="width: 70px;">
    <button class="btn-deploy" onclick="deployIncident()">▶ DEPLOY INCIDENT</button>
  </div>
  
  <div class="top-right">
    <div class="step-counter mono" id="top-step">00 / 15</div>
    <div class="separator"></div>
    <div class="score-display-small mono" id="top-score">0.000</div>
    <div class="separator"></div>
    <div class="clock mono" id="clock">00:00:00</div>
  </div>
</div>

<div id="left-panel" class="panel">
  <div class="panel-header uppercase">
    ◈ Infrastructure Status <span class="pill mono" id="svc-count">0</span>
  </div>
  <div id="service-list"></div>
</div>

<div id="center-panel" class="panel">
  <div class="center-top">
    <div class="panel-header uppercase">
      ◈ Active Alerts <span class="pill mono" id="alert-count" style="background:var(--surface2)">0</span>
    </div>
    <div id="alerts-list">
      <div class="no-alerts mono">◎ ALL SYSTEMS NOMINAL</div>
    </div>
  </div>
  
  <div class="center-bottom">
    <div class="panel-header uppercase">◈ Episode Metrics</div>
    <div class="giant-score mono" id="giant-score" style="color: var(--text-dim)">0.000</div>
    <div class="progress-container"><div class="progress-fill" id="score-bar"></div></div>
    <div class="score-stats mono uppercase">
      <span id="stat-step">STEP 0/15</span>
      <span id="stat-task">TASK: --</span>
      <span id="stat-seed">SEED: --</span>
    </div>
    <div class="sparkline" id="sparkline"></div>
  </div>
</div>

<div id="right-panel" class="panel">
  <div class="panel-header uppercase" style="color: var(--purple)">◈ Agent Reasoning</div>
  <div id="agent-log" class="mono"></div>
</div>

<div id="bottom-bar">
  <div class="ws-status mono">
    <div class="status-dot dot-grey" id="btm-dot"></div>
    <span id="btm-text" style="color: var(--text-dim)">○ WS DISCONNECTED</span>
  </div>
  <div class="tip-text" id="tip-text">ⓘ Agents must read_logs before acting — blind remediation triggers -0.10 penalty</div>
  <div class="footer-right mono">ARIA v2.0 · OpenEnv Compliant &nbsp;&nbsp; 🤗 Arijit-07</div>
</div>

<script>
  const TIPS = [
    "ⓘ Agents must read_logs before acting — blind remediation triggers -0.10 penalty",
    "ⓘ Collateral damage: restarting healthy services costs -0.15",
    "ⓘ 7 tasks · 14 actions · Dense reward shaping · Semantic diagnosis matching",
    "ⓘ Curriculum Engine adapts difficulty to agent performance",
    "ⓘ Dual-Agent Mode: Observer sees logs, Responder sees metrics",
    "ⓘ Grader clamped to (0.001, 0.999) for GRPO advantage stability",
    "ⓘ Hard task: all services green — signal buried in business metrics"
  ];
  let tipIdx = 0;
  setInterval(() => {{
    const el = document.getElementById('tip-text');
    el.style.opacity = 0;
    setTimeout(() => {{
      tipIdx = (tipIdx + 1) % TIPS.length;
      el.textContent = TIPS[tipIdx];
      el.style.opacity = 1;
    }}, 500);
  }}, 15000);

  setInterval(() => {{
    const now = new Date();
    document.getElementById('clock').textContent = now.toTimeString().split(' ')[0];
  }}, 1000);

  let currentEpisodeId = null;
  let lastStep = -1;
  let rewardHistory = [];
  let totalScore = 0;

  function getScoreColor(sc) {{
    if(sc < 0.3) return 'var(--red)';
    if(sc < 0.6) return 'var(--yellow)';
    return 'var(--green)';
  }}

  function updateScoreDisplay() {{
    const sc = Math.max(0, totalScore);
    const col = getScoreColor(sc);
    
    const ts = document.getElementById('top-score');
    ts.textContent = sc.toFixed(3);
    ts.style.color = col;
    
    const gs = document.getElementById('giant-score');
    gs.textContent = sc.toFixed(3);
    gs.style.color = col;
    
    document.getElementById('score-bar').style.width = Math.min(100, sc * 100) + '%';
  }}

  function addLog(type, arg1, arg2) {{
    const logEl = document.getElementById('agent-log');
    const div = document.createElement('div');
    div.className = 'log-entry';
    
    const timeStr = new Date().toTimeString().split(' ')[0];
    const timeSpan = `<span class="log-time">[${{timeStr}}]</span>`;
    
    if (type === 'SYSTEM') {{
      div.innerHTML = `${{timeSpan}} <span style="color:var(--text-dim)">${{arg1}}</span>`;
    }} else if (type === 'EPISODE_START') {{
      div.innerHTML = `<div class="log-episode-start">━━━ NEW INCIDENT DEPLOYED ━━━<br>Task: ${{arg1.toUpperCase()}} | Seed: ${{arg2}}</div>`;
    }} else if (type === 'ACTION') {{
      div.innerHTML = `${{timeSpan}} <span class="log-action">→ ${{arg1.action_type}} ${{arg1.service || ''}}</span>`;
    }} else if (type === 'REWARD') {{
      let col = arg1 > 0 ? 'var(--green)' : (arg1 === 0 ? 'var(--red)' : 'var(--text-dim)');
      div.innerHTML = `<div class="log-reward" style="color:${{col}}">✦ ${{arg1 > 0 ? '+' : ''}}${{arg1.toFixed(3)}} reward</div>`;
    }} else if (type === 'EVIDENCE') {{
      let txt = (arg1 || '').substring(0, 60);
      if(arg1 && arg1.length > 60) txt += '...';
      div.innerHTML = `<div class="log-evidence">↳ ${{txt}}</div>`;
    }} else if (type === 'DIAGNOSE') {{
      div.innerHTML = `${{timeSpan}} <span class="log-diagnose">⊕ DIAGNOSIS: ${{arg1}}</span>`;
    }} else if (type === 'FIX') {{
      div.innerHTML = `${{timeSpan}} <span class="log-fix">⚡ FIX APPLIED: ${{arg1}} → ${{arg2}}</span>`;
    }} else if (type === 'EPISODE_END') {{
      if (arg1 >= 0.7) {{
        div.innerHTML = `<div class="log-episode-end-ok">━━━ ✓ INCIDENT RESOLVED ━━━<br>Score: ${{arg1.toFixed(3)}} | Steps: ${{arg2}}/15<br>━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>`;
        document.getElementById('center-panel').classList.add('flash-resolve');
        document.getElementById('giant-score').classList.add('pulse-score');
        setTimeout(()=>{{
          document.getElementById('center-panel').classList.remove('flash-resolve');
          document.getElementById('giant-score').classList.remove('pulse-score');
        }}, 2000);
      }} else {{
        div.innerHTML = `<div class="log-episode-end-fail">━━━ ✗ INCIDENT ESCALATED ━━━<br>Score: ${{arg1.toFixed(3)}} | Steps: ${{arg2}}/15<br>━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>`;
      }}
    }}
    
    logEl.appendChild(div);
    if(logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
    logEl.scrollTop = logEl.scrollHeight;
  }}

  function updateSparkline() {{
    const sp = document.getElementById('sparkline');
    sp.innerHTML = '';
    const start = Math.max(0, rewardHistory.length - 12);
    const recent = rewardHistory.slice(start);
    
    recent.forEach((r, i) => {{
      const h = Math.max(2, Math.min(40, (r / 0.5) * 40));
      const col = r > 0 ? 'var(--green)' : 'var(--red)';
      sp.innerHTML += `<div class="spark-bar" style="height:${{h}}px; background:${{col}}"><div class="spark-label">${{start + i + 1}}</div></div>`;
    }});
  }}

  async function pollState() {{
    try {{
      const res = await fetch('/state');
      if (!res.ok) throw new Error('Not OK');
      const data = await res.json();
      
      document.getElementById('live-dot').className = 'status-dot dot-green';
      document.getElementById('live-text').textContent = 'LIVE';
      document.getElementById('live-text').style.color = 'var(--red)';
      document.getElementById('btm-dot').className = 'status-dot dot-green';
      document.getElementById('btm-text').textContent = '◉ API SYNC';
      document.getElementById('btm-text').style.color = 'var(--green)';

      handleState(data);
    }} catch(e) {{
      document.getElementById('live-dot').className = 'status-dot dot-grey';
      document.getElementById('live-text').textContent = 'OFFLINE';
      document.getElementById('live-text').style.color = 'var(--text)';
      document.getElementById('btm-dot').className = 'status-dot dot-grey';
      document.getElementById('btm-text').textContent = '○ API DISCONNECTED';
      document.getElementById('btm-text').style.color = 'var(--text-dim)';
    }}
  }}

  function handleState(state) {{
    if (!state.episode_id) return;
    
    if (state.episode_id !== currentEpisodeId) {{
      currentEpisodeId = state.episode_id;
      lastStep = -1;
      rewardHistory = [];
      totalScore = 0;
      document.getElementById('agent-log').innerHTML = '';
      addLog('EPISODE_START', state.task_id, state.info?.seed || '--');
      document.getElementById('stat-task').textContent = `TASK: ${{state.task_id.toUpperCase()}}`;
      document.getElementById('stat-seed').textContent = `SEED: ${{state.info?.seed || '--'}}`;
    }}

    if (state.step > lastStep) {{
      for (let i = Math.max(0, lastStep); i < state.action_history.length; i++) {{
        const hist = state.action_history[i];
        const act = hist.action;
        
        if(act.action_type === 'diagnose') addLog('DIAGNOSE', act.root_cause);
        else if(act.action_type === 'restart_service' || act.action_type === 'rollback_service' || act.action_type === 'block_ip') 
          addLog('FIX', act.action_type, act.service || act.ip);
        else addLog('ACTION', act);
        
        if(hist.reward !== undefined) {{
          rewardHistory.push(hist.reward);
          addLog('REWARD', hist.reward);
        }}
      }}
      
      lastStep = state.step;
      totalScore = state.total_reward;
      
      document.getElementById('top-step').textContent = `${{state.step.toString().padStart(2,'0')}} / 15`;
      document.getElementById('stat-step').textContent = `STEP ${{state.step}}/15`;
      updateScoreDisplay();
      updateSparkline();
      
      if (state.done || state.incident_resolved) {{
        addLog('EPISODE_END', state.total_reward, state.step);
        // Ensure we don't duplicate end logs
        lastStep = 99999;
      }}
    }}

    if (state.observation) {{
      const obs = state.observation;
      if (obs.services) {{
        const svcs = Object.entries(obs.services).map(([name, s]) => ({{name, ...s}}));
        svcs.sort((a, b) => {{
          const val = (st) => st === 'down' ? 0 : (st === 'degraded' ? 1 : 2);
          return val(a.status) - val(b.status);
        }});
        
        const list = document.getElementById('service-list');
        list.innerHTML = '';
        document.getElementById('svc-count').textContent = svcs.length;
        
        svcs.forEach(s => {{
          let bcol = 'var(--border)', bgcol = 'var(--surface)', tcol = 'var(--text-dim)', stxt = '○ UNKNOWN';
          if(s.status === 'down') {{ bcol = 'var(--red)'; bgcol = 'var(--red-dim)'; tcol = 'var(--red)'; stxt = '● DOWN'; }}
          else if(s.status === 'degraded') {{ bcol = 'var(--yellow)'; bgcol = 'var(--yellow-dim)'; tcol = 'var(--yellow)'; stxt = '◐ DEGRADED'; }}
          else if(s.status === 'healthy') {{ bcol = 'var(--green)'; bgcol = 'var(--green-dim)'; tcol = 'var(--green)'; stxt = '○ HEALTHY'; }}
          
          let errRate = (s.error_rate * 100).toFixed(1);
          let memUtil = (s.memory_utilization * 100).toFixed(1);
          let errCol = s.error_rate > 0.3 ? 'var(--red)' : (s.error_rate > 0.1 ? 'var(--yellow)' : 'var(--green)');
          let memCol = s.memory_utilization > 0.9 ? 'var(--red)' : (s.memory_utilization > 0.7 ? 'var(--yellow)' : 'var(--green)');
          
          list.innerHTML += `
            <div class="service-item mono" style="border-left: 3px solid ${{bcol}}; background: ${{bgcol}}">
              <div>
                <div class="svc-name">${{s.name}}</div>
                <div class="svc-status" style="color:${{tcol}}">${{stxt}}</div>
              </div>
              <div class="svc-stats">
                <div class="svc-stat-line" style="color:${{errCol}}">ERR ${{errRate}}%</div>
                <div class="svc-stat-line" style="color:${{memCol}}">MEM ${{memUtil}}%</div>
              </div>
            </div>
          `;
        }});
      }}
      
      if (obs.active_alerts) {{
        const alist = document.getElementById('alerts-list');
        alist.innerHTML = '';
        document.getElementById('alert-count').textContent = obs.active_alerts.length;
        document.getElementById('alert-count').style.background = obs.active_alerts.length > 0 ? 'var(--red)' : 'var(--surface2)';
        
        if(obs.active_alerts.length === 0) {{
          alist.innerHTML = '<div class="no-alerts mono">◎ ALL SYSTEMS NOMINAL</div>';
        }} else {{
          let critFound = false;
          obs.active_alerts.slice(0, 5).forEach(a => {{
            let bg = 'var(--surface)', border = 'var(--border)', txtCol = '#000';
            if(a.severity === 'CRITICAL') {{ border = 'var(--red)'; bg = 'var(--red)'; critFound = true; }}
            else if(a.severity === 'HIGH') {{ border = '#ff6600'; bg = '#ff6600'; }}
            else if(a.severity === 'WARNING') {{ border = 'var(--yellow)'; bg = 'var(--yellow)'; }}
            else {{ border = 'var(--blue)'; bg = 'var(--blue)'; }}
            
            alist.innerHTML += `
              <div class="alert-strip mono" style="border-left: 3px solid ${{border}}; background: ${{bg}}20">
                <div class="alert-badge" style="background:${{bg}}; color:${{txtCol}}">${{a.severity}}</div>
                <div class="alert-text">[${{a.service}}] ${{a.message}}</div>
              </div>
            `;
          }});
          if(obs.active_alerts.length > 5) {{
            alist.innerHTML += `<div class="mono" style="font-size:9px; color:var(--text-dim); text-align:center">+${{obs.active_alerts.length - 5}} more</div>`;
          }}
          if(critFound) {{
            const lp = document.getElementById('left-panel');
            lp.classList.remove('flash-critical');
            void lp.offsetWidth;
            lp.classList.add('flash-critical');
          }}
        }}
      }}
    }}
  }}

  async function deployIncident() {{
    const task = document.getElementById('task-select').value;
    const seed = parseInt(document.getElementById('seed-input').value) || 42;
    
    // Call REST API
    try {{
      await fetch('/reset', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{task_id: task, seed: seed}})
      }});
      // The poller will pick up the state change
    }} catch (e) {{
      console.error(e);
    }}
  }}

  setInterval(pollState, 1000);
  pollState();
</script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARIA - DevOps Incident Response</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #060914;
            --bg-card: #111827;
            --border: #1f2937;
            --blue: #3b82f6;
            --cyan: #06b6d4;
            --green: #10b981;
            --red: #ef4444;
            --yellow: #f59e0b;
            --purple: #8b5cf6;
            --text: #f9fafb;
            --muted: #9ca3af;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
        }}
        html {{ scroll-behavior: smooth; }}
        a {{ text-decoration: none; color: inherit; }}
        
        /* Animation */
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .fade-in {{
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.6s ease-out, transform 0.6s ease-out;
        }}
        .fade-in.visible {{ opacity: 1; transform: translateY(0); }}

        /* Canvas Background */
        #bg-canvas {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 0;
            pointer-events: none;
        }}

        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
            position: relative;
            z-index: 1;
        }}
        section {{ padding: 80px 0; }}

        /* Navbar */
        nav {{
            position: fixed;
            top: 0;
            width: 100%;
            height: 64px;
            background: rgba(6, 9, 20, 0.8);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border);
            z-index: 100;
            display: flex;
            align-items: center;
        }}
        .nav-inner {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
        }}
        .nav-left {{ display: flex; align-items: center; gap: 8px; }}
        .nav-logo {{ font-size: 20px; font-weight: 700; color: var(--blue); }}
        .nav-desc {{ font-size: 13px; color: var(--muted); display: none; }}
        @media (min-width: 768px) {{ .nav-desc {{ display: block; }} }}
        
        .nav-center {{ display: flex; justify-content: center; flex: 1; }}
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid var(--green);
            color: var(--green);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }}
        .status-dot {{
            width: 6px;
            height: 6px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{ 0% {{ transform: scale(1); opacity: 1; }} 50% {{ transform: scale(1.5); opacity: 0.5; }} 100% {{ transform: scale(1); opacity: 1; }} }}
        
        .nav-right {{ display: flex; gap: 24px; }}
        .nav-link {{ font-size: 13px; color: var(--muted); transition: color 0.2s; }}
        .nav-link:hover {{ color: var(--text); }}

        /* Hero */
        .hero {{ padding: 120px 0 80px; text-align: center; }}
        .hero-badge {{
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 999px;
            padding: 6px 16px;
            font-size: 12px;
            color: var(--blue);
            display: inline-block;
            margin-bottom: 24px;
        }}
        .hero-title {{
            font-size: clamp(72px, 12vw, 140px);
            font-weight: 700;
            background: linear-gradient(135deg, var(--blue) 0%, var(--cyan) 50%, var(--purple) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1;
            letter-spacing: -4px;
        }}
        .hero-subtitle {{ font-size: 20px; color: var(--muted); margin-top: 16px; font-weight: 400; }}
        .hero-desc {{ font-size: 15px; color: #4b5563; margin-top: 12px; line-height: 1.6; max-width: 600px; margin-inline: auto; }}
        
        .hero-buttons {{ margin-top: 40px; display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; }}
        .btn-primary, .btn-secondary {{
            padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; transition: all 0.2s; cursor: pointer; display: inline-block;
        }}
        .btn-primary {{ background: var(--blue); color: white; border: none; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
        .btn-secondary {{ background: transparent; border: 1px solid var(--border); color: var(--muted); }}
        .btn-secondary:hover {{ border-color: var(--blue); color: white; transform: translateY(-2px); }}

        .hero-stats {{ margin-top: 64px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
        .stat-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px 32px; text-align: center; }}
        .stat-val {{ font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; color: var(--blue); }}
        .stat-label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}

        .section-title {{ font-size: 24px; font-weight: 600; margin-bottom: 8px; }}
        .section-subtitle {{ font-size: 15px; color: var(--muted); margin-bottom: 32px; }}

        /* Tasks Grid */
        .task-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
        @media (max-width: 1024px) {{ .task-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
        @media (max-width: 640px) {{ .task-grid {{ grid-template-columns: 1fr; }} }}
        
        .task-card {{
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 24px;
            transition: all 0.3s; cursor: pointer; position: relative; overflow: hidden; display: flex; flex-direction: column;
        }}
        .task-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: transparent; transition: all 0.3s; }}
        .task-card:hover {{ transform: translateY(-4px); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }}
        .task-card:hover::before {{ background: var(--card-color, var(--border)); }}
        
        .task-header {{ display: flex; justify-content: space-between; align-items: flex-start; }}
        .task-icon {{ font-size: 32px; }}
        .task-badge {{ font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; background: var(--card-bg); color: var(--card-color); letter-spacing: 0.5px; }}
        .task-name {{ font-size: 16px; font-weight: 600; margin-top: 16px; }}
        .task-desc {{ font-size: 13px; color: var(--muted); margin-top: 8px; line-height: 1.5; flex-grow: 1; }}
        .task-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }}
        .task-steps {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #4b5563; }}
        .task-status {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--card-color); font-weight: 500; }}
        .task-status::before {{ content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--card-color); }}

        /* Features */
        .features-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }}
        @media (max-width: 900px) {{ .features-grid {{ grid-template-columns: 1fr; }} }}
        .feature-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }}
        .feature-icon {{ font-size: 48px; margin-bottom: 24px; }}
        .feature-title {{ font-size: 20px; font-weight: 600; margin-bottom: 12px; color: var(--text); }}
        .feature-desc {{ font-size: 14px; color: var(--muted); line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }}
        
        .c-bar-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: 12px; font-family: 'JetBrains Mono', monospace; }}
        .c-bar-name {{ color: var(--muted); width: 80px; overflow: hidden; text-overflow: ellipsis; }}
        .c-bar-track {{ flex-grow: 1; margin: 0 12px; letter-spacing: -2px; color: #4b5563; }}
        .c-bar-score {{ width: 30px; text-align: right; }}
        
        .generator-input {{ display: flex; gap: 8px; margin-bottom: 16px; }}
        .gen-seed {{ background: #0d1117; border: 1px solid var(--border); color: white; padding: 8px 12px; border-radius: 6px; width: 80px; font-family: 'JetBrains Mono', monospace; }}
        .btn-gen {{ background: var(--purple); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        .gen-result {{ background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: none; }}
        .gen-badges {{ display: flex; gap: 8px; margin-bottom: 12px; }}
        .gen-badge {{ font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }}
        .gen-diff-bar {{ height: 4px; background: var(--border); border-radius: 2px; margin: 12px 0; overflow: hidden; }}
        
        .dual-diagram {{ background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-bottom: 24px; color: var(--muted); display: flex; justify-content: space-between; align-items: center; }}
        .agent-box {{ border: 1px solid var(--border); padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.2); width: 42%; }}
        .agent-arrow {{ flex-grow: 1; text-align: center; color: var(--green); position: relative; }}
        .agent-arrow::after {{ content: '→'; position: absolute; top: -10px; left: 50%; transform: translateX(-50%); animation: flowRight 1.5s infinite linear; }}
        @keyframes flowRight {{ 0% {{ left: 20%; opacity: 0; }} 50% {{ opacity: 1; }} 100% {{ left: 80%; opacity: 0; }} }}
        .btn-green {{ background: var(--green); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        
        .feature-link {{ color: var(--blue); font-size: 14px; font-weight: 500; margin-top: 16px; display: inline-block; }}
        
        /* Live Metrics */
        .metrics-bar {{ background: #0d1117; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 24px 0; }}
        .metrics-grid {{ display: flex; justify-content: space-between; }}
        .metric-item {{ text-align: center; flex: 1; border-right: 1px solid var(--border); }}
        .metric-item:last-child {{ border-right: none; }}
        .metric-val {{ font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; color: var(--blue); }}
        .metric-label {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
        @media (max-width: 640px) {{ .metrics-grid {{ flex-wrap: wrap; gap: 24px; }} .metric-item {{ min-width: 40%; border: none; }} }}

        /* Leaderboard */
        .leaderboard-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: rgba(255,255,255,0.03); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #4b5563; padding: 12px 24px; border-bottom: 1px solid var(--border); }}
        td {{ padding: 16px 24px; border-bottom: 1px solid var(--border); font-size: 14px; }}
        tr:last-child td {{ border-bottom: none; }}
        .lb-score {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; }}

        /* Quick Start */
        .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
        .tab {{ background: transparent; border: none; color: var(--muted); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;}}
        .tab.active {{ background: var(--blue); color: white; }}
        .code-block {{ background: #020408; border: 1px solid var(--border); border-radius: 12px; padding: 24px; position: relative; display: none; overflow-x: auto; }}
        .code-block.active {{ display: block; }}
        .code-text {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.8; color: var(--text); white-space: pre; }}
        .btn-copy {{ position: absolute; top: 12px; right: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border); color: var(--muted); padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }}
        
        .c-com {{ color: #4b5563; }} .c-str {{ color: var(--green); }} .c-cmd {{ color: var(--blue); }} .c-url {{ color: var(--cyan); }} .c-key {{ color: var(--yellow); }}

        /* Training Evidence */
        .training-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        @media (max-width: 900px) {{ .training-grid {{ grid-template-columns: 1fr; }} }}
        .train-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }}
        .train-title {{ font-size: 18px; font-weight: 600; margin-bottom: 24px; }}
        .train-row {{ margin-bottom: 24px; }}
        .train-label {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }}
        .train-badge {{ padding: 4px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 600; }}
        .train-desc {{ font-size: 14px; color: var(--muted); line-height: 1.5; margin-left: 28px; }}
        .train-vis {{ float: left; font-size: 18px; margin-top: 2px; }}
        .tt-row {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border); }}
        .tt-row:last-child {{ border-bottom: none; }}
        .tt-key {{ font-size: 13px; color: var(--muted); }}
        .tt-val {{ font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text); }}
        
        /* Footer */
        footer {{ background: #0d1117; border-top: 1px solid var(--border); padding: 48px 0 32px; margin-top: 80px; }}
        .footer-grid {{ display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 32px; }}
        @media (max-width: 768px) {{ .footer-grid {{ grid-template-columns: 1fr; }} }}
        .f-title {{ font-size: 14px; font-weight: 600; margin-bottom: 16px; }}
        .f-text {{ font-size: 13px; color: #4b5563; line-height: 1.6; }}
        .f-links {{ display: flex; flex-direction: column; gap: 12px; }}
        .f-link {{ font-size: 13px; color: var(--muted); transition: color 0.2s; }}
        .f-link:hover {{ color: var(--text); }}
        .f-bottom {{ border-top: 1px solid var(--border); margin-top: 32px; padding-top: 24px; display: flex; justify-content: space-between; font-size: 12px; color: #4b5563; }}
    </style>
</head>
<body>
    <canvas id="bg-canvas"></canvas>

    <nav>
        <div class="nav-inner">
            <div class="nav-left">
                <div class="nav-logo">🚨 ARIA</div>
                <div class="nav-desc">DevOps Incident Response</div>
            </div>
            <div class="nav-center">
                <div class="status-pill">
                    <div class="status-dot"></div>
                    <span id="nav-status-text">CONNECTING</span>
                </div>
            </div>
            <div class="nav-right">
                <a href="/docs" class="nav-link">API Docs</a>
                <a href="/validate" class="nav-link">Validate</a>
                <a href="/metrics" class="nav-link">Metrics</a>
                <a href="/leaderboard" class="nav-link">Leaderboard</a>
            </div>
        </div>
    </nav>

    <main class="container">
        <section class="hero fade-in">
            <div class="hero-badge">⚡ OpenEnv Compliant · Meta × PyTorch × HuggingFace</div>
            <h1 class="hero-title">ARIA</h1>
            <div class="hero-subtitle">Adaptive Reward & Incident Architecture</div>
            <p class="hero-desc">The first OpenEnv RL environment for production incident response.<br>7 tasks · 14 actions · Curriculum · Dual-agent · Trained Llama-3.1-8B</p>
            
            <div class="hero-buttons">
                <a href="/docs" class="btn-primary">Try Live API &rarr;</a>
                <a href="https://github.com/Twilight-13/devops-incident-response" target="_blank" class="btn-secondary">View GitHub &rarr;</a>
            </div>
            
            <div class="hero-stats">
                <div class="stat-card"><div class="stat-val">7</div><div class="stat-label">Tasks</div></div>
                <div class="stat-card"><div class="stat-val">14</div><div class="stat-label">Actions</div></div>
                <div class="stat-card"><div class="stat-val">&infin;</div><div class="stat-label">Scenarios</div></div>
                <div class="stat-card"><div class="stat-val">0.99</div><div class="stat-label">Max Score</div></div>
            </div>
        </section>
        
        <section class="fade-in">
            <h2 class="section-title">Environment Tasks</h2>
            <p class="section-subtitle">Eight scenarios of escalating operational complexity</p>
            <div class="task-grid" id="task-grid"><div style="grid-column: 1/-1; text-align: center; color: var(--muted);">Loading tasks...</div></div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">ARIA Features</h2>
            <p class="section-subtitle">What makes this environment unique</p>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-icon">🎓</div>
                    <h3 class="feature-title">Curriculum Engine</h3>
                    <p class="feature-desc">Tracks agent performance per task with rolling averages. Promotes when mastered (avg > 0.75). Scaffolds with hints when struggling (avg < 0.30). Agents always train at the edge of their capability.</p>
                    <div id="curriculum-container" style="margin-bottom: 24px;"></div>
                    <a href="/curriculum/status" class="feature-link" style="color: var(--blue);">View Status &rarr;</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3 class="feature-title">Incident Generator</h3>
                    <p class="feature-desc">Procedural incidents from seeds 0–99,999. Six failure modes × eight services × variable noise = infinite unique training scenarios. Same seed always produces the same incident.</p>
                    <div class="generator-input">
                        <input type="number" id="gen-seed" class="gen-seed" value="42" min="0" max="99999">
                        <button class="btn-gen" onclick="generateIncident()">Generate</button>
                    </div>
                    <div class="gen-result" id="gen-result">
                        <div class="gen-badges" id="gen-badges"></div>
                        <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px;" id="gen-affected"></div>
                        <div style="font-size: 12px; color: var(--muted); line-height: 1.5;" id="gen-desc"></div>
                        <div class="gen-diff-bar"><div id="gen-diff-fill" style="height: 100%; transition: width 0.3s;"></div></div>
                    </div>
                    <a href="/generate/preview?seed=42" class="feature-link" style="color: var(--purple);">Try Generator &rarr;</a>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">🤝</div>
                    <h3 class="feature-title">Dual-Agent Mode</h3>
                    <p class="feature-desc">Split observability between two agents. Observer sees logs and alerts. Responder sees metrics and dependencies. Neither can solve the incident alone — they must coordinate via share_finding.</p>
                    <div class="dual-diagram">
                        <div class="agent-box"><div style="font-weight:700; margin-bottom:4px;">AGENT A: Observer</div><div>• alerts, logs</div></div>
                        <div class="agent-arrow">share_finding</div>
                        <div class="agent-box"><div style="font-weight:700; margin-bottom:4px;">AGENT B: Responder</div><div>• metrics, deps</div></div>
                    </div>
                    <button class="btn-green" onclick="startDualSession()">Start Session</button>
                    <div id="dual-session-info" style="margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--green); display: none; word-break: break-all;"></div>
                    <a href="/multi-agent/sessions" class="feature-link" style="color: var(--green); margin-top: auto;">View Sessions &rarr;</a>
                </div>
            </div>
        </section>
    </main>

    <div class="metrics-bar fade-in">
        <div class="container metrics-grid">
            <div class="metric-item"><div class="metric-val" id="m-episodes">--</div><div class="metric-label">Total Episodes</div></div>
            <div class="metric-item"><div class="metric-val" id="m-avg">--</div><div class="metric-label">Avg Score</div></div>
            <div class="metric-item"><div class="metric-val" id="m-res">--</div><div class="metric-label">Resolution Rate</div></div>
            <div class="metric-item"><div class="metric-val" id="m-best">--</div><div class="metric-label">Best Score</div></div>
        </div>
    </div>

    <main class="container">
        <section class="fade-in">
            <h2 class="section-title">🏆 Leaderboard</h2>
            <div class="leaderboard-card">
                <table>
                    <thead><tr><th>Rank</th><th>Task</th><th>Score</th><th>Steps</th><th>Status</th></tr></thead>
                    <tbody id="lb-body"><tr><td colspan="5" style="text-align: center; color: var(--muted);">Loading leaderboard...</td></tr></tbody>
                </table>
            </div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">Quick Start</h2>
            <div class="tabs">
                <button class="tab active" onclick="switchTab('curl')">curl</button>
                <button class="tab" onclick="switchTab('python')">Python</button>
            </div>
            
            <div id="code-curl" class="code-block active">
                <button class="btn-copy" onclick="copyCode('code-curl-text', this)">Copy</button>
                <div class="code-text" id="code-curl-text"><span class="c-com"># 1. Start an incident</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/reset \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{{<span class="c-key">"task_id"</span>: <span class="c-str">"easy"</span>, <span class="c-key">"seed"</span>: 42}}'</span>

<span class="c-com"># 2. Read logs (reward: +0.15)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{{<span class="c-key">"action_type"</span>: <span class="c-str">"read_logs"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}}'</span>

<span class="c-com"># 3. Diagnose (reward: +0.30)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{{<span class="c-key">"action_type"</span>: <span class="c-str">"diagnose"</span>, <span class="c-key">"root_cause"</span>: <span class="c-str">"memory leak in payment-service"</span>}}'</span>

<span class="c-com"># 4. Fix it (reward: +0.40)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{{<span class="c-key">"action_type"</span>: <span class="c-str">"restart_service"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}}'</span>

<span class="c-com"># Score: ~0.94 ✅</span></div>
            </div>
            
            <div id="code-python" class="code-block">
                <button class="btn-copy" onclick="copyCode('code-py-text', this)">Copy</button>
                <div class="code-text" id="code-py-text"><span class="c-cmd">import</span> requests
BASE = <span class="c-str">"https://arijit-07-devops-incident-response.hf.space"</span>

<span class="c-com"># Start episode</span>
obs = requests.post(<span class="c-url">f"{{BASE}}/reset"</span>, json={{<span class="c-key">"task_id"</span>: <span class="c-str">"easy"</span>, <span class="c-key">"seed"</span>: 42}}).json()

<span class="c-com"># Take action</span>
result = requests.post(<span class="c-url">f"{{BASE}}/step"</span>,
    json={{<span class="c-key">"action_type"</span>: <span class="c-str">"read_logs"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}}).json()

print(<span class="c-url">f"Reward: {{result['reward']}}"</span>)  <span class="c-com"># 0.15</span></div>
            </div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">🧠 Training Evidence</h2>
            <div class="training-grid">
                <div class="train-card">
                    <h3 class="train-title">Before vs After</h3>
                    <div class="train-row">
                        <div class="train-label"><span>Base Llama-3.1-8B</span><span class="train-badge" style="background: rgba(239, 68, 68, 0.2); color: var(--red);">0.000</span></div>
                        <div class="train-vis" style="color: var(--red);">❌</div>
                        <div class="train-desc">jumps to diagnose, gets penalized</div>
                    </div>
                    <div class="train-row">
                        <div class="train-label"><span>ARIA Fine-tuned</span><span class="train-badge" style="background: rgba(16, 185, 129, 0.2); color: var(--green);">0.150</span></div>
                        <div class="train-vis" style="color: var(--green);">✅</div>
                        <div class="train-desc">reads logs first, every time</div>
                    </div>
                    <a href="https://huggingface.co/Arijit-07/aria-devops-llama8b" target="_blank" class="feature-link">Model weights &rarr;</a>
                </div>
                <div class="train-card">
                    <h3 class="train-title">Training Details</h3>
                    <div class="tt-row"><div class="tt-key">Algorithm</div><div class="tt-val">GRPO</div></div>
                    <div class="tt-row"><div class="tt-key">Base Model</div><div class="tt-val">Llama-3.1-8B-Instruct</div></div>
                    <div class="tt-row"><div class="tt-key">Framework</div><div class="tt-val">Unsloth + HuggingFace TRL</div></div>
                    <div class="tt-row"><div class="tt-key">LoRA Rank</div><div class="tt-val">32 (alpha 64)</div></div>
                    <div class="tt-row"><div class="tt-key">Episodes</div><div class="tt-val">160</div></div>
                    <div class="tt-row"><div class="tt-key">GPU</div><div class="tt-val">NVIDIA L4</div></div>
                </div>
            </div>
        </section>
    </main>

    <footer>
        <div class="container">
            <div class="footer-grid">
                <div>
                    <div style="font-size: 20px; font-weight: 700; color: var(--blue); margin-bottom: 8px;">🚨 ARIA</div>
                    <div class="f-text">DevOps Incident Response<br>OpenEnv-compliant RL environment</div>
                    <div style="display: flex; gap: 16px; margin-top: 16px;">
                        <a href="https://github.com/Twilight-13/devops-incident-response" target="_blank" class="f-link">GitHub</a>
                        <a href="https://huggingface.co/Arijit-07/aria-devops-llama8b" target="_blank" class="f-link">Model</a>
                    </div>
                </div>
                <div>
                    <div class="f-title">Resources</div>
                    <div class="f-links">
                        <a href="/docs" class="f-link">Live API Docs</a>
                        <a href="/validate" class="f-link">Validate</a>
                        <a href="/metrics" class="f-link">Metrics</a>
                        <a href="/leaderboard" class="f-link">Leaderboard</a>
                    </div>
                </div>
                <div>
                    <div class="f-title">Built for</div>
                    <div class="f-text">Meta × PyTorch × HuggingFace<br>OpenEnv Hackathon Finals<br>Bangalore, April 2026</div>
                </div>
            </div>
            <div class="f-bottom">
                <div>&copy; 2026 ARIA — Apache 2.0 License</div>
                <div>Can your agent handle a SEV-1 at 3am?</div>
            </div>
        </div>
    </footer>

    <script>
        const canvas = document.getElementById('bg-canvas');
        const ctx = canvas.getContext('2d');
        let width, height, particles = [];

        function resize() {{ width = canvas.width = window.innerWidth; height = canvas.height = window.innerHeight; }}
        window.addEventListener('resize', resize); resize();

        for(let i=0; i<50; i++) {{
            particles.push({{ x: Math.random() * width, y: Math.random() * height, vx: (Math.random()-0.5)*0.5, vy: (Math.random()-0.5)*0.5 }});
        }}

        function draw() {{
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.1)';
            for(let i=0; i<particles.length; i++) {{
                let p = particles[i];
                p.x += p.vx; p.y += p.vy;
                if(p.x < 0 || p.x > width) p.vx *= -1;
                if(p.y < 0 || p.y > height) p.vy *= -1;
                ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI*2); ctx.fill();
                for(let j=i+1; j<particles.length; j++) {{
                    let p2 = particles[j], dist = Math.hypot(p.x-p2.x, p.y-p2.y);
                    if(dist < 150) {{ ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p2.x, p2.y); ctx.stroke(); }}
                }}
            }}
            requestAnimationFrame(draw);
        }}
        draw();

        const observer = new IntersectionObserver(e => e.forEach(en => {{ if(en.isIntersecting) en.target.classList.add('visible'); }}), {{threshold: 0.1}});
        document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

        fetch('/health').then(r => r.json()).then(d => {{
            if(d.status === 'ok') document.getElementById('nav-status-text').innerText = 'LIVE';
        }}).catch(e => console.error(e));

        const tMap = {{
            'easy': {{icon: '💻', color: '#10b981', badge: 'EASY'}}, 'medium': {{icon: '⚡', color: '#f59e0b', badge: 'MEDIUM'}},
            'hard': {{icon: '🔥', color: '#ef4444', badge: 'HARD'}}, 'bonus': {{icon: '💥', color: '#8b5cf6', badge: 'EXPERT'}},
            'security': {{icon: '🛡️', color: '#06b6d4', badge: 'SECURITY'}}, 'database': {{icon: '🗄️', color: '#f97316', badge: 'DATABASE'}},
            'failover': {{icon: '🌐', color: '#6366f1', badge: 'FAILOVER'}}, 'generated': {{icon: '✨', color: '#ec4899', badge: 'DYNAMIC'}}
        }};
        fetch('/tasks').then(r => r.json()).then(d => {{
            document.getElementById('task-grid').innerHTML = d.tasks.map(t => {{
                let c = tMap[t.id] || tMap['easy'];
                return `<div class="task-card" style="--card-color:${{c.color}};--card-bg:${{c.color}}20;">
                    <div class="task-header"><div class="task-icon">${{c.icon}}</div><div class="task-badge">${{c.badge}}</div></div>
                    <div class="task-name">${{t.name}}</div><div class="task-desc">${{t.description}}</div>
                    <div class="task-footer"><div class="task-steps">Max steps: ${{t.max_steps}}</div><div class="task-status">Ready</div></div>
                </div>`;
            }}).join('');
        }}).catch(e => console.error(e));

        fetch('/curriculum/status').then(r => r.json()).then(d => {{
            const el = document.getElementById('curriculum-container');
            if(!d.total_episodes_recorded) el.innerHTML = '<div style="color:var(--muted); font-size:13px; text-align:center;">No episodes yet — run POST /reset to begin</div>';
            else {{
                el.innerHTML = Object.keys(d.tasks).slice(0, 4).map(k => {{
                    let avg = d.tasks[k].rolling_avg, col = avg < 0.3 ? 'var(--red)' : (avg < 0.6 ? 'var(--yellow)' : 'var(--green)');
                    let bl = Math.round(avg * 10);
                    return `<div class="c-bar-row"><div class="c-bar-name">${{k}}</div>
                    <div class="c-bar-track" style="color:${{col}}"><span>${{'█'.repeat(bl)}}</span><span style="opacity:0.3">${{'░'.repeat(10-bl)}}</span></div>
                    <div class="c-bar-score">${{avg.toFixed(2)}}</div></div>`;
                }}).join('');
            }}
        }}).catch(e => console.error(e));

        window.generateIncident = () => {{
            const seed = document.getElementById('gen-seed').value || 42;
            fetch(`/generate/preview?seed=${{seed}}`).then(r => r.json()).then(d => {{
                const colors = {{oom: '#ef4444', cascade: '#f59e0b', corruption: '#8b5cf6', security: '#06b6d4', database: '#f97316', network_partition: '#6366f1'}};
                const sc = {{sev1: '#ef4444', sev2: '#f59e0b', sev3: '#10b981'}};
                let fcol = colors[d.failure_mode] || 'var(--blue)';
                document.getElementById('gen-badges').innerHTML = `<span class="gen-badge" style="background:${{fcol}}20;color:${{fcol}}">${{d.failure_mode}}</span><span class="gen-badge" style="background:${{sc[d.severity]||fcol}}20;color:${{sc[d.severity]||fcol}}">${{d.severity}}</span><span class="gen-badge" style="background:rgba(255,255,255,0.1);color:var(--muted)">${{d.incident_id}}</span>`;
                document.getElementById('gen-affected').innerText = `Affected: ${{d.affected_service}}`;
                document.getElementById('gen-desc').innerText = d.description;
                let dc = d.difficulty_score < 0.4 ? 'var(--green)' : (d.difficulty_score < 0.7 ? 'var(--yellow)' : 'var(--red)');
                let fill = document.getElementById('gen-diff-fill');
                fill.style.width = `${{d.difficulty_score*100}}%`; fill.style.background = dc;
                document.getElementById('gen-result').style.display = 'block';
            }}).catch(e => console.error(e));
        }};

        window.startDualSession = () => {{
            fetch('/multi-agent/reset', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{task_id: "easy", seed: 42}}) }})
            .then(r => r.json()).then(d => {{
                let info = document.getElementById('dual-session-info');
                info.innerHTML = `Session: ${{d.session_id}}<br><br>Agent A (POST): /multi-agent/step/a/${{d.session_id}}<br>Agent B (POST): /multi-agent/step/b/${{d.session_id}}`;
                info.style.display = 'block';
            }}).catch(e => console.error(e));
        }};

        const loadMetrics = () => {{
            fetch('/metrics').then(r => r.json()).then(d => {{
                document.getElementById('m-episodes').innerText = d.total_episodes || 0;
                document.getElementById('m-avg').innerText = (d.overall_avg_score || 0).toFixed(3);
                if(d.by_task) {{
                    let tRes = 0, tCnt = 0, best = 0;
                    Object.values(d.by_task).forEach(t => {{ tRes += t.resolution_rate*t.count; tCnt += t.count; if(t.max_score > best) best = t.max_score; }});
                    document.getElementById('m-res').innerText = (tCnt ? (tRes/tCnt)*100 : 0).toFixed(1) + '%';
                    document.getElementById('m-best').innerText = best.toFixed(3);
                }}
            }}).catch(e => console.error(e));
        }};
        loadMetrics(); setInterval(loadMetrics, 30000);

        fetch('/leaderboard').then(r => r.json()).then(d => {{
            const body = document.getElementById('lb-body');
            if(!d.leaderboard || !d.leaderboard.length) {{ body.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--muted);">No episodes yet. Try POST /reset to start.</td></tr>'; return; }}
            body.innerHTML = d.leaderboard.map(r => {{
                let rank = r.rank === 1 ? 'color:#fbbf24;font-weight:bold' : (r.rank === 2 ? 'color:#9ca3af;font-weight:bold' : (r.rank === 3 ? 'color:#cd7f32;font-weight:bold' : ''));
                let sCol = r.score >= 0.8 ? 'var(--green)' : (r.score >= 0.5 ? 'var(--yellow)' : 'var(--red)');
                let status = r.score > 0.5 ? '<span style="color:var(--green)">✅ Resolved</span>' : '<span style="color:var(--red)">❌ Failed</span>';
                return `<tr><td style="${{rank}}">#${{r.rank}}</td><td>${{r.task_id}}</td><td class="lb-score" style="color:${{sCol}}">${{r.score.toFixed(4)}}</td><td>${{r.steps}}</td><td>${{status}}</td></tr>`;
            }}).join('');
        }}).catch(e => console.error(e));

        window.switchTab = t => {{
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.code-block').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab')[t === 'curl' ? 0 : 1].classList.add('active');
            document.getElementById('code-'+t).classList.add('active');
        }};

        window.copyCode = (id, btn) => {{
            navigator.clipboard.writeText(document.getElementById(id).innerText).then(() => {{
                let old = btn.innerText; btn.innerText = 'Copied ✓'; setTimeout(() => btn.innerText = old, 2000);
            }});
        }};
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
    current_episode_steps.clear()
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
    global replay_counter
    if _env._logic is None:
        raise HTTPException(status_code=400, detail="Call /reset before /step")
    res = await _env.step(action)

    step_data = {
        "step": len(current_episode_steps),
        "action": action.dict(),
        "reward": res.reward,
        "observation_summary": {
            "failing_services": [s.name for s in res.observation.services if s.status in ("down", "degraded")],
            "alert_count": len(res.observation.active_alerts),
            "evidence_count": len(res.observation.evidence_log),
        },
    }
    current_episode_steps.append(step_data)

    if res.done:
        track_episode(_env.state)
        state = _env.state
        replay_store[str(replay_counter)] = {
            "episode_id": str(replay_counter),
            "task_id": state.task_id,
            "seed": state.info.get("seed", 0),
            "final_score": round(state.total_reward, 3),
            "resolved": state.incident_resolved,
            "total_steps": state.step,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": list(current_episode_steps),
        }
        replay_counter += 1
        if len(replay_store) > 20:
            oldest = min(replay_store.keys(), key=int)
            del replay_store[oldest]

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
    
    details = {}
    for r in results:
        details[r["task_id"]] = {
            "status": "passed" if r.get("status") == "ok" and r.get("in_range") else r.get("status", "failed"),
            "score": r.get("score"),
            "resolved": r.get("resolved")
        }

    return {
        "validation": "passed" if all_ok else "failed",
        "summary": f"{passed_count}/{total_count} tasks passed validation",
        "tasks_checked": total_count,
        "tasks_passed": passed_count,
        "details": details,
        "environment": "devops-incident-response",
        "version": "2.0.0",
        "note": "Generated task excluded — procedural tasks require fixed parameters"
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


# ─── Feature 1: Episode Replay System ────────────────────────────────────────

@app.get("/replays")
def list_replays():
    """List available episode replays, newest first."""
    items = []
    for ep_id, r in replay_store.items():
        items.append({
            "episode_id": r["episode_id"],
            "task_id": r["task_id"],
            "score": r["final_score"],
            "resolved": r["resolved"],
            "total_steps": r["total_steps"],
            "timestamp": r["timestamp"],
        })
    items.sort(key=lambda x: int(x["episode_id"]), reverse=True)
    return items


@app.get("/replay/{episode_id}")
def get_replay(episode_id: str):
    """Return full replay data for an episode."""
    if episode_id not in replay_store:
        raise HTTPException(status_code=404, detail="Episode not found")
    return replay_store[episode_id]


@app.get("/replay/{episode_id}/html", response_class=HTMLResponse)
def get_replay_html(episode_id: str):
    """Return an HTML timeline visualization of an episode replay."""
    if episode_id not in replay_store:
        raise HTTPException(status_code=404, detail="Episode not found")
    r = replay_store[episode_id]

    def reward_color(reward: float) -> str:
        if reward > 0.2:
            return "#00ff88"
        if reward > 0:
            return "#ffaa00"
        if reward == 0:
            return "#ff3355"
        return "#ff3355"

    def reward_bg(reward: float) -> str:
        if reward > 0.2:
            return "rgba(0,255,136,0.08)"
        if reward > 0:
            return "rgba(255,170,0,0.08)"
        return "rgba(255,51,85,0.08)"

    steps_html = ""
    running_score = 0.0
    for s in r["steps"]:
        running_score += s["reward"]
        act = s["action"]
        act_type = act.get("action_type", "unknown")
        service = act.get("service") or ""
        rc = act.get("root_cause") or ""
        obs = s["observation_summary"]
        col = reward_color(s["reward"])
        bg = reward_bg(s["reward"])
        reward_sign = "+" if s["reward"] > 0 else ""
        failing = ", ".join(obs["failing_services"]) if obs["failing_services"] else "none"
        steps_html += f"""
        <div class="step-card" style="border-left-color:{col}; background:{bg}">
          <div class="step-header">
            <span class="step-num mono">STEP {s['step'] + 1}</span>
            <span class="step-action mono">{act_type} {service}</span>
            <span class="step-reward mono" style="color:{col}">{reward_sign}{s['reward']:.3f}</span>
            <span class="step-running mono" style="color:#4d9fff">&sum; {running_score:.3f}</span>
          </div>
          {"<div class='step-rc'>&rarr; " + rc + "</div>" if rc and act_type == "diagnose" else ""}
          <div class="step-obs mono">
            failing: {failing} &nbsp;|&nbsp;
            alerts: {obs['alert_count']} &nbsp;|&nbsp;
            evidence: {obs['evidence_count']}
          </div>
        </div>"""

    resolved_color = "#00ff88" if r["resolved"] else "#ff3355"
    resolved_text = "INCIDENT RESOLVED" if r["resolved"] else "INCIDENT ESCALATED"
    resolved_icon = "&#10003;" if r["resolved"] else "&#10007;"
    score_col = "#00ff88" if r["final_score"] >= 0.7 else "#ffaa00" if r["final_score"] >= 0.4 else "#ff3355"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ARIA Replay #{episode_id}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root {{--bg:#060914;--surface:#0a0f1e;--surface2:#0d1628;--border:#1a2744;--blue:#4d9fff;--cyan:#00d4ff;--green:#00ff88;--yellow:#ffaa00;--red:#ff3355;--text:#c8d8f0;--text-dim:#4a6080;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;padding:24px;max-width:900px;margin:0 auto;}}
  .mono{{font-family:'Share Tech Mono',monospace;}}
  .header{{background:var(--surface);border:1px solid var(--border);padding:24px;margin-bottom:24px;}}
  .header-title{{font-size:22px;color:var(--blue);font-weight:700;margin-bottom:8px;}}
  .header-meta{{display:flex;gap:24px;flex-wrap:wrap;}}
  .meta-item{{font-size:13px;color:var(--text-dim);}}
  .meta-value{{color:var(--text);font-weight:600;}}
  .step-card{{border-left:3px solid;padding:12px 16px;margin-bottom:8px;border-radius:0 4px 4px 0;}}
  .step-header{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:4px;}}
  .step-num{{font-size:11px;color:var(--text-dim);min-width:60px;}}
  .step-action{{font-size:13px;color:var(--cyan);flex:1;}}
  .step-reward{{font-size:14px;font-weight:700;}}
  .step-running{{font-size:11px;}}
  .step-rc{{font-size:12px;color:var(--yellow);padding:4px 0;}}
  .step-obs{{font-size:11px;color:var(--text-dim);margin-top:4px;}}
  .resolution-banner{{text-align:center;padding:32px;margin-top:24px;border:2px solid;font-size:24px;font-weight:700;}}
  .nav-links{{display:flex;gap:16px;margin-bottom:24px;font-size:13px;}}
  .nav-links a{{color:var(--blue);text-decoration:none;}}
  .nav-links a:hover{{color:var(--cyan);}}
  h2{{font-size:14px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:16px;}}
</style>
</head>
<body>
<div class="nav-links">
  <a href="/replays/html">&larr; All Replays</a>
  <a href="/live">Live NOC</a>
  <a href="/progress">Progress</a>
  <a href="/docs">API Docs</a>
</div>
<div class="header">
  <div class="header-title">&#9635; Episode Replay #{episode_id}</div>
  <div class="header-meta">
    <div class="meta-item">TASK <span class="meta-value mono">{r['task_id'].upper()}</span></div>
    <div class="meta-item">SEED <span class="meta-value mono">{r['seed']}</span></div>
    <div class="meta-item">SCORE <span class="meta-value mono" style="color:{score_col}">{r['final_score']:.3f}</span></div>
    <div class="meta-item">STEPS <span class="meta-value mono">{r['total_steps']}</span></div>
    <div class="meta-item">TIME <span class="meta-value mono">{r['timestamp'][:19]}</span></div>
  </div>
</div>
<h2>Step Timeline</h2>
{steps_html if steps_html else '<div style="color:var(--text-dim);padding:24px">No steps recorded.</div>'}
<div class="resolution-banner mono" style="color:{resolved_color};border-color:{resolved_color};background:{'rgba(0,255,136,0.05)' if r['resolved'] else 'rgba(255,51,85,0.05)'}">
  {resolved_icon} {resolved_text} &nbsp;|&nbsp; Final Score: {r['final_score']:.3f}
</div>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/replays/html", response_class=HTMLResponse)
def list_replays_html():
    """HTML index of all replays."""
    items = sorted(replay_store.values(), key=lambda x: int(x["episode_id"]), reverse=True)
    rows = ""
    for r in items:
        score_col = "#00ff88" if r["final_score"] >= 0.7 else "#ffaa00" if r["final_score"] >= 0.4 else "#ff3355"
        resolved_icon = "&#10003;" if r["resolved"] else "&#10007;"
        rows += f"""<tr>
          <td class="mono"><a href="/replay/{r['episode_id']}/html" style="color:#4d9fff">#{r['episode_id']}</a></td>
          <td class="mono">{r['task_id'].upper()}</td>
          <td class="mono" style="color:{score_col}">{r['final_score']:.3f}</td>
          <td class="mono" style="color:{'#00ff88' if r['resolved'] else '#ff3355'}">{resolved_icon}</td>
          <td class="mono">{r['total_steps']}</td>
          <td class="mono" style="color:#4a6080">{r['timestamp'][:19]}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#4a6080;padding:32px">No replays yet. Complete an episode to generate one.</td></tr>'
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ARIA Episode Replays</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#060914;--surface:#0a0f1e;--border:#1a2744;--blue:#4d9fff;--text:#c8d8f0;--text-dim:#4a6080;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;padding:32px;max-width:900px;margin:0 auto;}}
  .mono{{font-family:'Share Tech Mono',monospace;}}
  h1{{font-size:22px;color:var(--blue);margin-bottom:24px;}}
  table{{width:100%;border-collapse:collapse;}}
  th{{text-align:left;font-size:11px;color:var(--text-dim);text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--border);}}
  td{{padding:10px 12px;border-bottom:1px solid rgba(26,39,68,0.5);font-size:13px;}}
  tr:hover td{{background:rgba(77,159,255,0.04);}}
  .nav-links{{display:flex;gap:16px;margin-bottom:24px;font-size:13px;}}
  .nav-links a{{color:var(--blue);text-decoration:none;}}
</style>
</head>
<body>
<div class="nav-links"><a href="/live">Live NOC</a><a href="/progress">Progress</a><a href="/challenge">Challenge</a></div>
<h1>&#9635; Episode Replays</h1>
<table>
  <thead><tr><th>ID</th><th>Task</th><th>Score</th><th>Resolved</th><th>Steps</th><th>Time</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
</body>
</html>"""
    return HTMLResponse(html)


# ─── Feature 2: Human vs Agent Challenge ─────────────────────────────────────

@app.get("/challenge", response_class=HTMLResponse)
async def challenge_page():
    """Human-playable incident response challenge."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ARIA Human Challenge</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#060914;--surface:#0a0f1e;--surface2:#0d1628;--border:#1a2744;
    --border-bright:#2a4080;--blue:#4d9fff;--cyan:#00d4ff;--green:#00ff88;
    --yellow:#ffaa00;--red:#ff3355;--purple:#9d4edd;--text:#c8d8f0;--text-dim:#4a6080;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh;}
  .mono{font-family:'Share Tech Mono',monospace;}
  .nav{background:#000;border-bottom:1px solid var(--border);padding:0 24px;height:48px;display:flex;align-items:center;justify-content:space-between;}
  .nav-logo{font-size:16px;color:var(--blue);font-weight:700;}
  .nav-links{display:flex;gap:16px;font-size:12px;}
  .nav-links a{color:var(--text-dim);text-decoration:none;}
  .nav-links a:hover{color:var(--blue);}
  .warning{background:rgba(255,170,0,0.1);border-bottom:1px solid var(--yellow);padding:8px 24px;font-size:12px;color:var(--yellow);text-align:center;}
  .main{display:grid;grid-template-columns:1fr 380px;height:calc(100vh - 80px);}
  .left{padding:20px;overflow-y:auto;border-right:1px solid var(--border);}
  .right{padding:20px;overflow-y:auto;background:var(--surface);}
  .panel{background:var(--surface2);border:1px solid var(--border);padding:16px;margin-bottom:16px;}
  .panel-title{font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px;}
  table{width:100%;border-collapse:collapse;font-size:12px;}
  th{text-align:left;color:var(--text-dim);font-size:10px;text-transform:uppercase;padding:4px 8px;border-bottom:1px solid var(--border);}
  td{padding:6px 8px;font-family:'Share Tech Mono',monospace;font-size:12px;border-bottom:1px solid rgba(26,39,68,0.5);}
  .status-down{color:var(--red);}
  .status-degraded{color:var(--yellow);}
  .status-healthy{color:var(--green);}
  .alert-item{padding:6px 10px;border-left:3px solid;margin-bottom:6px;font-size:12px;}
  .sev-critical{border-color:var(--red);background:rgba(255,51,85,0.08);}
  .sev-high{border-color:#ff6600;background:rgba(255,102,0,0.08);}
  .sev-warning{border-color:var(--yellow);background:rgba(255,170,0,0.08);}
  .sev-info{border-color:var(--blue);background:rgba(77,159,255,0.08);}
  .evidence-item{font-size:11px;color:var(--text-dim);padding:4px 0;border-bottom:1px solid rgba(26,39,68,0.3);}
  .form-row{margin-bottom:12px;}
  label{display:block;font-size:11px;color:var(--text-dim);text-transform:uppercase;margin-bottom:4px;}
  select,input[type=text]{width:100%;background:var(--surface);border:1px solid var(--border-bright);color:var(--text);font-family:'Share Tech Mono',monospace;font-size:13px;padding:8px 10px;outline:none;}
  select:focus,input[type=text]:focus{border-color:var(--blue);}
  .btn-action{width:100%;background:rgba(77,159,255,0.15);border:1px solid var(--blue);color:var(--blue);font-family:'Share Tech Mono',monospace;font-size:14px;padding:12px;cursor:pointer;transition:0.2s;margin-top:8px;text-transform:uppercase;letter-spacing:0.1em;}
  .btn-action:hover{background:var(--blue);color:#000;}
  .btn-action:disabled{opacity:0.4;cursor:not-allowed;}
  .btn-reset{background:rgba(255,51,85,0.1);border:1px solid var(--red);color:var(--red);}
  .btn-reset:hover{background:var(--red);color:#000;}
  .score-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;}
  .big-score{font-size:36px;font-weight:700;font-family:'Share Tech Mono',monospace;}
  .step-info{font-size:12px;color:var(--text-dim);}
  .reward-flash{padding:8px 12px;margin-bottom:8px;font-size:14px;font-family:'Share Tech Mono',monospace;border-left:3px solid;}
  .result-log{max-height:150px;overflow-y:auto;font-size:11px;color:var(--text-dim);font-family:'Share Tech Mono',monospace;background:var(--surface);padding:8px;margin-top:8px;white-space:pre-wrap;}
  .comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;}
  .cmp-card{background:var(--surface2);border:1px solid var(--border);padding:20px;text-align:center;}
  .cmp-label{font-size:11px;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;}
  .cmp-score{font-size:32px;font-weight:700;font-family:'Share Tech Mono',monospace;}
  .cmp-steps{font-size:12px;color:var(--text-dim);margin-top:4px;}
  .done-banner{text-align:center;padding:24px;border:2px solid;font-size:20px;font-weight:700;margin-bottom:16px;}
  ::-webkit-scrollbar{width:4px;}::-webkit-scrollbar-thumb{background:var(--border-bright);}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-logo mono">&#9635; ARIA HUMAN CHALLENGE</div>
  <div class="nav-links">
    <a href="/live">Live NOC</a>
    <a href="/progress">Progress</a>
    <a href="/replays/html">Replays</a>
    <a href="/docs">API</a>
  </div>
</div>
<div class="warning">&#9888; Note: This resets the shared environment &mdash; agent runs will be interrupted while you play</div>
<div class="main">
  <div class="left">
    <div class="panel" id="task-desc-panel" style="display:none">
      <div class="panel-title">&#9658; Task Description</div>
      <div id="task-desc" style="font-size:13px;color:#8ab4d4"></div>
    </div>
    <div class="panel">
      <div class="panel-title">&#9658; Infrastructure Status</div>
      <table>
        <thead><tr><th>Service</th><th>Status</th><th>CPU%</th><th>Mem%</th><th>Err/s</th><th>P99ms</th></tr></thead>
        <tbody id="svc-tbody"><tr><td colspan="6" style="color:var(--text-dim);padding:16px">Loading...</td></tr></tbody>
      </table>
    </div>
    <div class="panel">
      <div class="panel-title">&#9658; Active Alerts <span id="alert-count" style="color:var(--red)"></span></div>
      <div id="alerts-container"><div style="color:var(--text-dim);font-size:12px">No alerts</div></div>
    </div>
    <div class="panel">
      <div class="panel-title">&#9658; Evidence Gathered <span id="evidence-count" style="color:var(--blue)"></span></div>
      <div id="evidence-container"><div style="color:var(--text-dim);font-size:12px">No evidence yet</div></div>
    </div>
    <div id="done-panel" style="display:none">
      <div class="done-banner mono" id="done-banner"></div>
      <div class="comparison">
        <div class="cmp-card">
          <div class="cmp-label">Your Score</div>
          <div class="cmp-score" id="human-score">&mdash;</div>
          <div class="cmp-steps" id="human-steps"></div>
        </div>
        <div class="cmp-card">
          <div class="cmp-label">Trained Agent (Llama-3.1-8B)</div>
          <div class="cmp-score" id="agent-score">&mdash;</div>
          <div class="cmp-steps">from /metrics avg</div>
        </div>
      </div>
      <button class="btn-action" onclick="startGame(true)" style="margin-top:16px;width:100%">&#9654; Play Again (Random Seed)</button>
    </div>
  </div>
  <div class="right">
    <div class="score-header">
      <div>
        <div class="panel-title">Episode Progress</div>
        <div class="big-score mono" id="score-display" style="color:var(--text-dim)">0.000</div>
      </div>
      <div style="text-align:right">
        <div class="step-info mono" id="step-display">Step 0 / 15</div>
        <div class="step-info mono" id="task-display" style="color:var(--blue)">EASY</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">&#9658; Take Action</div>
      <div class="form-row">
        <label>Action Type</label>
        <select id="action-type" onchange="onActionTypeChange()">
          <option value="read_logs">read_logs &mdash; Read full log output</option>
          <option value="search_logs">search_logs &mdash; Search logs for keyword</option>
          <option value="read_metrics">read_metrics &mdash; Read CPU/mem/latency</option>
          <option value="read_runbook">read_runbook &mdash; Open a runbook</option>
          <option value="diagnose">diagnose &mdash; Submit root cause diagnosis</option>
          <option value="restart_service">restart_service &mdash; Restart a crashed service</option>
          <option value="rollback">rollback &mdash; Roll back a deployment</option>
          <option value="scale_up">scale_up &mdash; Scale up replicas</option>
          <option value="alert_oncall">alert_oncall &mdash; Page on-call engineer</option>
          <option value="acknowledge">acknowledge &mdash; Acknowledge an alert</option>
          <option value="block_ip_range">block_ip_range &mdash; Block a CIDR range</option>
          <option value="create_index">create_index &mdash; Create a DB index</option>
          <option value="failover">failover &mdash; Regional failover</option>
          <option value="noop">noop &mdash; No action</option>
        </select>
      </div>
      <div class="form-row" id="svc-row">
        <label>Service Name</label>
        <input type="text" id="service-input" placeholder="e.g. payment-service">
      </div>
      <div class="form-row" id="rc-row" style="display:none">
        <label>Root Cause (for diagnose)</label>
        <input type="text" id="rc-input" placeholder="e.g. Memory leak in payment-service causing OOM">
      </div>
      <div class="form-row" id="query-row" style="display:none">
        <label>Search Query</label>
        <input type="text" id="query-input" placeholder="e.g. OOM">
      </div>
      <div class="form-row" id="rb-row" style="display:none">
        <label>Runbook File</label>
        <input type="text" id="rb-input" placeholder="e.g. memory_leak.md">
      </div>
      <div class="form-row" id="ip-row" style="display:none">
        <label>IP Range</label>
        <input type="text" id="ip-input" placeholder="e.g. 185.220.0.0/16">
      </div>
      <div class="form-row" id="reason-row" style="display:none">
        <label>Reason (for alert_oncall)</label>
        <input type="text" id="reason-input" placeholder="e.g. Data corruption detected">
      </div>
      <button class="btn-action" id="action-btn" onclick="takeAction()">&#9654; TAKE ACTION</button>
      <div id="reward-flash" style="display:none" class="reward-flash"></div>
      <div id="result-log" class="result-log" style="display:none"></div>
    </div>
    <div class="panel">
      <div class="panel-title">&#9658; Reward History</div>
      <div id="reward-history" class="mono" style="font-size:11px;max-height:120px;overflow-y:auto"></div>
    </div>
    <button class="btn-action btn-reset" onclick="startGame(true)" style="margin-top:8px">&#8635; New Incident (Random Seed)</button>
  </div>
</div>
<script>
  let isDone = false;
  let currentSeed = 1234;
  let stepCount = 0;
  let totalScore = 0;
  let maxSteps = 15;

  async function startGame(randomSeed) {
    currentSeed = randomSeed ? Math.floor(Math.random() * 99999) : 1234;
    stepCount = 0; totalScore = 0; isDone = false;
    document.getElementById('done-panel').style.display = 'none';
    document.getElementById('reward-history').innerHTML = '';
    document.getElementById('result-log').style.display = 'none';
    document.getElementById('reward-flash').style.display = 'none';
    document.getElementById('action-btn').disabled = false;
    const res = await fetch('/reset', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id: 'easy', seed: currentSeed})
    });
    const obs = await res.json();
    maxSteps = obs.max_steps || 15;
    renderObs(obs);
    document.getElementById('step-display').textContent = 'Step 0 / ' + maxSteps;
    document.getElementById('task-display').textContent = (obs.task_id || 'easy').toUpperCase() + ' \\u00b7 SEED ' + currentSeed;
    if (obs.task_description) {
      document.getElementById('task-desc').textContent = obs.task_description;
      document.getElementById('task-desc-panel').style.display = 'block';
    }
    updateScoreDisplay(0);
  }

  function onActionTypeChange() {
    const at = document.getElementById('action-type').value;
    document.getElementById('rc-row').style.display = at === 'diagnose' ? 'block' : 'none';
    document.getElementById('query-row').style.display = at === 'search_logs' ? 'block' : 'none';
    document.getElementById('rb-row').style.display = at === 'read_runbook' ? 'block' : 'none';
    document.getElementById('ip-row').style.display = at === 'block_ip_range' ? 'block' : 'none';
    document.getElementById('reason-row').style.display = at === 'alert_oncall' ? 'block' : 'none';
    document.getElementById('svc-row').style.display = ['read_runbook','block_ip_range','noop'].includes(at) ? 'none' : 'block';
  }

  async function takeAction() {
    if (isDone) return;
    const at = document.getElementById('action-type').value;
    const svc = document.getElementById('service-input').value.trim() || null;
    const body = {action_type: at};
    if (svc) body.service = svc;
    if (at === 'diagnose') body.root_cause = document.getElementById('rc-input').value.trim();
    if (at === 'search_logs') body.query = document.getElementById('query-input').value.trim();
    if (at === 'read_runbook') body.runbook = document.getElementById('rb-input').value.trim();
    if (at === 'block_ip_range') body.ip_range = document.getElementById('ip-input').value.trim();
    if (at === 'alert_oncall') body.reason = document.getElementById('reason-input').value.trim();
    document.getElementById('action-btn').disabled = true;
    const res = await fetch('/step', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    document.getElementById('action-btn').disabled = isDone ? true : false;
    const reward = data.reward || 0;
    totalScore += reward; stepCount += 1;
    renderObs(data.observation);
    updateScoreDisplay(totalScore);
    document.getElementById('step-display').textContent = 'Step ' + stepCount + ' / ' + maxSteps;
    showReward(reward, data.observation && data.observation.last_action_result);
    appendRewardHistory(stepCount, at, reward);
    if (data.done) { isDone = true; document.getElementById('action-btn').disabled = true; showDonePanel(totalScore, stepCount, data.observation && data.observation.incident_resolved); }
  }

  function renderObs(obs) {
    if (!obs) return;
    if (obs.services) {
      document.getElementById('svc-tbody').innerHTML = obs.services.map(s => {
        const sc = s.status === 'down' ? 'status-down' : s.status === 'degraded' ? 'status-degraded' : 'status-healthy';
        return '<tr><td>' + s.name + '</td><td class="' + sc + '">' + s.status.toUpperCase() + '</td><td>' + (s.cpu_percent||0).toFixed(1) + '</td><td>' + (s.memory_percent||0).toFixed(1) + '</td><td>' + (s.error_rate||0).toFixed(3) + '</td><td>' + (s.latency_p99_ms||0).toFixed(0) + '</td></tr>';
      }).join('');
    }
    const ac = document.getElementById('alerts-container');
    if (obs.active_alerts && obs.active_alerts.length > 0) {
      document.getElementById('alert-count').textContent = '(' + obs.active_alerts.length + ')';
      ac.innerHTML = obs.active_alerts.map(a => {
        const sev = (a.severity||'INFO').toLowerCase();
        const cls = sev === 'critical' ? 'sev-critical' : sev === 'high' ? 'sev-high' : sev === 'warning' ? 'sev-warning' : 'sev-info';
        return '<div class="alert-item ' + cls + ' mono"><strong>' + a.severity + '</strong> [' + a.service + '] ' + a.message + '</div>';
      }).join('');
    } else { document.getElementById('alert-count').textContent = ''; ac.innerHTML = '<div style="color:var(--text-dim);font-size:12px">No active alerts</div>'; }
    const ec = document.getElementById('evidence-container');
    if (obs.evidence_log && obs.evidence_log.length > 0) {
      document.getElementById('evidence-count').textContent = '(' + obs.evidence_log.length + ')';
      ec.innerHTML = obs.evidence_log.slice(-5).map(e => '<div class="evidence-item">&#9658; [step ' + e.step + '] ' + e.source + ': ' + e.summary + '</div>').join('');
    } else { document.getElementById('evidence-count').textContent = ''; ec.innerHTML = '<div style="color:var(--text-dim);font-size:12px">No evidence yet &mdash; use read_logs, read_metrics, or search_logs</div>'; }
  }

  function updateScoreDisplay(score) {
    const el = document.getElementById('score-display');
    el.textContent = score.toFixed(3);
    el.style.color = score >= 0.7 ? 'var(--green)' : score >= 0.4 ? 'var(--yellow)' : score > 0 ? 'var(--red)' : 'var(--text-dim)';
  }

  function showReward(reward, resultText) {
    const el = document.getElementById('reward-flash');
    const sign = reward > 0 ? '+' : '';
    el.style.display = 'block'; el.style.borderColor = reward > 0 ? 'var(--green)' : 'var(--red)';
    el.style.color = reward > 0 ? 'var(--green)' : 'var(--red)';
    el.style.background = reward > 0 ? 'rgba(0,255,136,0.08)' : 'rgba(255,51,85,0.08)';
    el.textContent = 'Reward: ' + sign + reward.toFixed(3);
    if (resultText) { const rl = document.getElementById('result-log'); rl.style.display = 'block'; rl.textContent = resultText.substring(0, 500); }
  }

  function appendRewardHistory(step, action, reward) {
    const el = document.getElementById('reward-history');
    const sign = reward > 0 ? '+' : '';
    const col = reward > 0 ? 'var(--green)' : 'var(--red)';
    el.innerHTML += '<div style="color:' + col + '">S' + step + ' ' + action + ' &rarr; ' + sign + reward.toFixed(3) + '</div>';
    el.scrollTop = el.scrollHeight;
  }

  async function showDonePanel(score, steps, resolved) {
    const banner = document.getElementById('done-banner');
    banner.style.color = resolved ? 'var(--green)' : 'var(--red)';
    banner.style.borderColor = resolved ? 'var(--green)' : 'var(--red)';
    banner.style.background = resolved ? 'rgba(0,255,136,0.05)' : 'rgba(255,51,85,0.05)';
    banner.textContent = (resolved ? '\\u2713 INCIDENT RESOLVED' : '\\u2717 INCIDENT ESCALATED') + ' \\u2014 Score: ' + score.toFixed(3);
    document.getElementById('human-score').textContent = score.toFixed(3);
    document.getElementById('human-score').style.color = score >= 0.7 ? 'var(--green)' : score >= 0.4 ? 'var(--yellow)' : 'var(--red)';
    document.getElementById('human-steps').textContent = steps + ' steps taken';
    try {
      const m = await fetch('/metrics'); const mdata = await m.json();
      const easyData = mdata.by_task && mdata.by_task['easy'];
      if (easyData) { document.getElementById('agent-score').textContent = easyData.avg_score.toFixed(3); document.getElementById('agent-score').style.color = easyData.avg_score >= 0.7 ? 'var(--green)' : easyData.avg_score >= 0.4 ? 'var(--yellow)' : 'var(--red)'; }
      else { document.getElementById('agent-score').textContent = 'N/A'; }
    } catch(e) { document.getElementById('agent-score').textContent = 'N/A'; }
    document.getElementById('done-panel').style.display = 'block';
  }

  startGame(false);
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ─── Feature 3: Progress Visualization ───────────────────────────────────────

@app.get("/progress", response_class=HTMLResponse)
def progress_page():
    """Training progress and live performance visualization."""
    metrics = get_metrics()
    by_task = metrics.get("by_task", {})

    BASELINES = {
        "easy": 0.05, "medium": 0.03, "hard": 0.01,
        "bonus": 0.01, "security": 0.01, "database": 0.01, "failover": 0.01,
    }
    TRAINING_RESULTS = [
        ("easy",   0.320, 0.685),
        ("medium", 0.050, 0.378),
        ("hard",   0.190, 0.869),
        ("bonus",  0.152, 0.682),
    ]
    ALL_TASKS = ["easy", "medium", "hard", "bonus", "security", "database", "failover"]

    def bar_row(task: str, score: float, baseline: float) -> str:
        pct = round(score * 100, 1)
        bpct = round(baseline * 100, 1)
        col = "#00ff88" if score >= 0.7 else "#ffaa00" if score >= 0.4 else "#ff3355"
        return f"""
        <div class="bar-group">
          <div class="bar-label mono">{task.upper()}</div>
          <div class="bar-tracks">
            <div class="bar-track">
              <span class="bar-tag">RANDOM</span>
              <div class="bar-bg"><div class="bar-fill" style="width:{bpct}%;background:#4a6080"></div></div>
              <span class="bar-val mono" style="color:#4a6080">{baseline:.3f}</span>
            </div>
            <div class="bar-track">
              <span class="bar-tag">ARIA</span>
              <div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{col}"></div></div>
              <span class="bar-val mono" style="color:{col}">{score:.3f}</span>
            </div>
          </div>
        </div>"""

    bars = "".join(
        bar_row(task, by_task.get(task, {}).get("avg_score", 0.0), BASELINES.get(task, 0.01))
        for task in ALL_TASKS
    )

    training_rows = "".join(
        f"""<tr>
          <td class="mono">{task.upper()}</td>
          <td class="mono" style="color:#4a6080">{base:.3f}</td>
          <td class="mono" style="color:#4d9fff">{finetuned:.3f}</td>
          <td class="mono" style="color:#00ff88">+{finetuned - base:.3f} &#10003;</td>
        </tr>"""
        for task, base, finetuned in TRAINING_RESULTS
    )

    recent = list(episode_history)[-20:] if episode_history else []
    recent_scores_js = str([round(r["final_score"], 3) for r in recent])
    total_eps = metrics.get("total_episodes", 0)
    overall = metrics.get("overall_avg_score", 0.0)
    overall_col = "#00ff88" if overall >= 0.7 else "#ffaa00" if overall >= 0.4 else "#4d9fff"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ARIA Progress</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#060914;--surface:#0a0f1e;--surface2:#0d1628;--border:#1a2744;--blue:#4d9fff;--cyan:#00d4ff;--green:#00ff88;--yellow:#ffaa00;--red:#ff3355;--text:#c8d8f0;--text-dim:#4a6080;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;}}
  .mono{{font-family:'Share Tech Mono',monospace;}}
  .nav{{background:#000;border-bottom:1px solid var(--border);padding:0 32px;height:48px;display:flex;align-items:center;justify-content:space-between;}}
  .nav-logo{{font-size:16px;color:var(--blue);font-weight:700;}}
  .nav-links{{display:flex;gap:16px;font-size:12px;}}
  .nav-links a{{color:var(--text-dim);text-decoration:none;}}
  .nav-links a:hover{{color:var(--blue);}}
  .page{{max-width:960px;margin:0 auto;padding:32px;}}
  h1{{font-size:22px;color:var(--blue);margin-bottom:8px;}}
  .subtitle{{font-size:13px;color:var(--text-dim);margin-bottom:40px;}}
  h2{{font-size:13px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:20px;padding-bottom:8px;border-bottom:1px solid var(--border);}}
  section{{margin-bottom:48px;}}
  .stats-row{{display:flex;gap:24px;margin-bottom:32px;flex-wrap:wrap;}}
  .stat-card{{background:var(--surface);border:1px solid var(--border);padding:20px 24px;flex:1;min-width:140px;}}
  .stat-label{{font-size:10px;color:var(--text-dim);text-transform:uppercase;margin-bottom:6px;}}
  .stat-value{{font-size:28px;font-weight:700;font-family:'Share Tech Mono',monospace;}}
  .bar-group{{margin-bottom:20px;}}
  .bar-label{{font-size:11px;color:var(--text-dim);text-transform:uppercase;margin-bottom:8px;letter-spacing:0.08em;}}
  .bar-tracks{{display:flex;flex-direction:column;gap:6px;}}
  .bar-track{{display:flex;align-items:center;gap:10px;}}
  .bar-tag{{font-size:9px;color:var(--text-dim);width:50px;text-align:right;font-family:'Share Tech Mono',monospace;}}
  .bar-bg{{flex:1;height:12px;background:var(--surface);border:1px solid var(--border);overflow:hidden;}}
  .bar-fill{{height:100%;transition:width 0.6s ease;}}
  .bar-val{{font-size:12px;width:50px;text-align:right;}}
  table{{width:100%;border-collapse:collapse;}}
  th{{text-align:left;font-size:11px;color:var(--text-dim);text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--border);}}
  td{{padding:10px 12px;border-bottom:1px solid rgba(26,39,68,0.5);}}
  .canvas-wrap{{background:var(--surface);border:1px solid var(--border);padding:16px;}}
  canvas{{display:block;width:100%;max-width:880px;}}
  .canvas-label{{font-size:11px;color:var(--text-dim);margin-top:8px;text-align:center;font-family:'Share Tech Mono',monospace;}}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-logo mono">&#9635; ARIA PROGRESS</div>
  <div class="nav-links">
    <a href="/live">Live NOC</a>
    <a href="/challenge">Challenge</a>
    <a href="/replays/html">Replays</a>
    <a href="/docs">API Docs</a>
  </div>
</div>
<div class="page">
  <h1>Training Progress &amp; Live Performance</h1>
  <div class="subtitle">Llama-3.1-8B fine-tuned with GRPO on 7 task types &middot; 14 actions &middot; Dense reward shaping</div>
  <div class="stats-row">
    <div class="stat-card"><div class="stat-label">Live Episodes</div><div class="stat-value" id="live-eps" style="color:var(--blue)">{total_eps}</div></div>
    <div class="stat-card"><div class="stat-label">Avg Live Score</div><div class="stat-value" id="live-avg" style="color:{overall_col}">{overall:.3f}</div></div>
    <div class="stat-card"><div class="stat-label">Training Episodes</div><div class="stat-value" style="color:var(--blue)">160</div></div>
    <div class="stat-card"><div class="stat-label">Model</div><div class="stat-value" style="font-size:14px;color:var(--cyan)">8B GRPO</div></div>
  </div>
  <section>
    <h2>Section 1 &mdash; Live Task Performance vs Random Baseline</h2>
    {bars}
  </section>
  <section>
    <h2>Section 2 &mdash; Training Improvement (Llama-3.1-8B, GRPO)</h2>
    <table>
      <thead><tr><th>Task</th><th>Baseline</th><th>Fine-tuned</th><th>Improvement</th></tr></thead>
      <tbody>{training_rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Section 3 &mdash; Live Episode Score Timeline</h2>
    <div class="canvas-wrap">
      <canvas id="timeline-canvas" width="880" height="120"></canvas>
      <div class="canvas-label mono" id="canvas-label">Last 20 episodes &middot; updates every 30s</div>
    </div>
  </section>
</div>
<script>
  const SCORES = {recent_scores_js};
  function drawTimeline(scores) {{
    const canvas = document.getElementById('timeline-canvas');
    canvas.width = canvas.parentElement.clientWidth - 32;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = 120;
    ctx.clearRect(0, 0, W, H);
    if (scores.length === 0) {{
      ctx.fillStyle = '#4a6080'; ctx.font = '13px Share Tech Mono, monospace';
      ctx.textAlign = 'center'; ctx.fillText('No episodes yet', W/2, H/2); return;
    }}
    const pad = 30, plotW = W - pad * 2, plotH = H - pad * 2;
    ctx.strokeStyle = '#1a2744'; ctx.lineWidth = 1;
    [0, 0.25, 0.5, 0.75, 1.0].forEach(v => {{
      const y = pad + plotH - v * plotH;
      ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke();
      ctx.fillStyle = '#4a6080'; ctx.font = '10px Share Tech Mono, monospace';
      ctx.textAlign = 'right'; ctx.fillText(v.toFixed(2), pad - 4, y + 3);
    }});
    const n = scores.length;
    const pts = scores.map((s, i) => [pad + (i / Math.max(n-1, 1)) * plotW, pad + plotH - s * plotH]);
    ctx.strokeStyle = '#4d9fff'; ctx.lineWidth = 2; ctx.lineJoin = 'round';
    ctx.beginPath(); pts.forEach(([x,y], i) => i === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y)); ctx.stroke();
    pts.forEach(([x,y], i) => {{
      const s = scores[i];
      ctx.fillStyle = s >= 0.7 ? '#00ff88' : s >= 0.4 ? '#ffaa00' : '#ff3355';
      ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI*2); ctx.fill();
    }});
  }}
  drawTimeline(SCORES);
  async function refresh() {{
    try {{
      const res = await fetch('/metrics'); const data = await res.json();
      document.getElementById('live-eps').textContent = data.total_episodes || 0;
      const avg = data.overall_avg_score || 0;
      document.getElementById('live-avg').textContent = avg.toFixed(3);
    }} catch(e) {{}}
  }}
  setInterval(refresh, 30000);
</script>
</body>
</html>"""
    return HTMLResponse(html)

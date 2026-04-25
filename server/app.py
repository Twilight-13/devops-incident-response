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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARIA - DevOps Incident Response</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #060914;
            --bg-secondary: #0d1117;
            --bg-card: #111827;
            --bg-card-hover: #1a2234;
            --border: #1f2937;
            --border-glow: #3b82f6;
            --accent-blue: #3b82f6;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-purple: #8b5cf6;
            --accent-orange: #f97316;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
            --text-dim: #4b5563;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
        }}
        
        a {{ text-decoration: none; color: inherit; }}

        /* Animation */
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

        /* Container */
        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
            position: relative;
            z-index: 1;
        }}
        
        /* Section Spacing */
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
        .nav-logo {{ font-size: 20px; font-weight: 700; color: var(--accent-blue); display: flex; align-items: center; gap: 6px; }}
        .nav-desc {{ font-size: 13px; color: var(--text-secondary); margin-left: 8px; display: none; }}
        @media (min-width: 768px) {{ .nav-desc {{ display: block; }} }}
        
        .nav-center {{ display: flex; justify-content: center; flex: 1; }}
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }}
        .status-dot {{
            width: 6px;
            height: 6px;
            background: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{ 0% {{ transform: scale(1); opacity: 1; }} 50% {{ transform: scale(1.5); opacity: 0.5; }} 100% {{ transform: scale(1); opacity: 1; }} }}
        
        .nav-right {{ display: flex; gap: 24px; }}
        .nav-link {{ font-size: 13px; color: var(--text-secondary); transition: color 0.2s; }}
        .nav-link:hover {{ color: var(--text-primary); }}

        /* Hero Section */
        .hero {{ padding: 120px 0 80px; text-align: center; }}
        .hero-badge {{
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 999px;
            padding: 6px 16px;
            font-size: 12px;
            color: var(--accent-blue);
            display: inline-block;
            margin-bottom: 24px;
        }}
        .hero-title {{
            font-size: clamp(72px, 12vw, 140px);
            font-weight: 700;
            background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 50%, #8b5cf6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1;
            letter-spacing: -4px;
        }}
        .hero-subtitle {{ font-size: 20px; color: var(--text-secondary); margin-top: 16px; font-weight: 400; }}
        .hero-desc {{ font-size: 15px; color: var(--text-dim); margin-top: 12px; line-height: 1.6; max-width: 600px; margin-inline: auto; }}
        
        .hero-buttons {{ margin-top: 40px; display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; }}
        .btn-primary, .btn-secondary {{
            padding: 14px 28px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 15px;
            transition: all 0.2s;
            cursor: pointer;
            display: inline-block;
        }}
        .btn-primary {{ background: var(--accent-blue); color: white; border: none; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
        .btn-secondary {{ background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }}
        .btn-secondary:hover {{ border-color: var(--accent-blue); color: white; transform: translateY(-2px); }}

        .hero-stats {{
            margin-top: 64px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 32px;
            text-align: center;
        }}
        .stat-val {{ font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; color: var(--accent-blue); }}
        .stat-label {{ font-size: 13px; color: var(--text-secondary); margin-top: 4px; }}

        /* General Sections */
        .section-title {{ font-size: 24px; font-weight: 600; margin-bottom: 8px; }}
        .section-subtitle {{ font-size: 15px; color: var(--text-secondary); margin-bottom: 32px; }}

        /* Task Cards */
        .task-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
        @media (max-width: 1024px) {{ .task-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
        @media (max-width: 640px) {{ .task-grid {{ grid-template-columns: 1fr; }} }}

        .task-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            transition: all 0.3s;
            cursor: pointer;
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .task-card::before {{
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
            background: transparent; transition: all 0.3s;
        }}
        .task-card:hover {{
            background: var(--bg-card-hover);
            transform: translateY(-4px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }}
        .task-card:hover::before {{ background: var(--card-color, var(--border)); }}
        
        .task-header {{ display: flex; justify-content: space-between; align-items: flex-start; }}
        .task-icon {{ font-size: 32px; }}
        .task-badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            background: var(--card-bg);
            color: var(--card-color);
            letter-spacing: 0.5px;
        }}
        .task-name {{ font-size: 16px; font-weight: 600; margin-top: 16px; }}
        .task-desc {{ font-size: 13px; color: var(--text-secondary); margin-top: 8px; line-height: 1.5; flex-grow: 1; }}
        .task-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }}
        .task-steps {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-dim); }}
        .task-status {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--card-color); font-weight: 500; }}
        .task-status::before {{ content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--card-color); }}

        /* Features */
        .features-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }}
        @media (max-width: 900px) {{ .features-grid {{ grid-template-columns: 1fr; }} }}
        
        .feature-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            display: flex;
            flex-direction: column;
        }}
        .feature-icon {{ font-size: 48px; margin-bottom: 24px; }}
        .feature-title {{ font-size: 20px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }}
        .feature-desc {{ font-size: 14px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }}
        
        .curriculum-bars {{ margin-bottom: 24px; }}
        .c-bar-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: 12px; font-family: 'JetBrains Mono', monospace; }}
        .c-bar-name {{ color: var(--text-secondary); width: 80px; overflow: hidden; text-overflow: ellipsis; }}
        .c-bar-track {{ flex-grow: 1; margin: 0 12px; letter-spacing: -2px; color: var(--text-dim); }}
        .c-bar-fill {{ letter-spacing: -2px; }}
        .c-bar-score {{ width: 30px; text-align: right; }}
        
        .generator-input {{
            display: flex; gap: 8px; margin-bottom: 16px;
        }}
        .gen-seed {{
            background: var(--bg-secondary); border: 1px solid var(--border); color: white;
            padding: 8px 12px; border-radius: 6px; width: 80px; font-family: 'JetBrains Mono', monospace;
        }}
        .btn-gen {{ background: var(--accent-purple); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        .btn-gen:hover {{ background: #7c3aed; }}
        .gen-result {{ background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: none; }}
        .gen-badges {{ display: flex; gap: 8px; margin-bottom: 12px; }}
        .gen-badge {{ font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }}
        .gen-diff-bar {{ height: 4px; background: var(--border); border-radius: 2px; margin: 12px 0; overflow: hidden; }}
        .gen-diff-fill {{ height: 100%; transition: width 0.3s; }}
        
        .dual-diagram {{
            background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px;
            padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-bottom: 24px;
            color: var(--text-secondary);
            display: flex; justify-content: space-between; align-items: center;
        }}
        .agent-box {{ border: 1px solid var(--border); padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.2); width: 42%; }}
        .agent-arrow {{ flex-grow: 1; text-align: center; color: var(--accent-green); position: relative; }}
        .agent-arrow::after {{
            content: '→'; position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
            animation: flowRight 1.5s infinite linear;
        }}
        @keyframes flowRight {{ 0% {{ left: 20%; opacity: 0; }} 50% {{ opacity: 1; }} 100% {{ left: 80%; opacity: 0; }} }}
        .btn-green {{ background: var(--accent-green); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        .btn-green:hover {{ background: #059669; }}
        .session-info {{ margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--accent-green); display: none; word-break: break-all; }}

        .feature-link {{ color: var(--accent-blue); font-size: 14px; font-weight: 500; text-decoration: none; margin-top: auto; display: inline-block; }}
        .feature-link:hover {{ text-decoration: underline; }}

        /* Live Metrics Bar */
        .metrics-bar-container {{ background: var(--bg-secondary); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 24px 0; }}
        .metrics-grid {{ display: flex; justify-content: space-between; }}
        .metric-item {{ text-align: center; flex: 1; border-right: 1px solid var(--border); }}
        .metric-item:last-child {{ border-right: none; }}
        .metric-val {{ font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; color: var(--accent-blue); }}
        .metric-label {{ font-size: 12px; color: var(--text-secondary); margin-top: 4px; }}
        @media (max-width: 640px) {{ .metrics-grid {{ flex-wrap: wrap; gap: 24px; }} .metric-item {{ min-width: 40%; border: none; }} }}

        /* Leaderboard */
        .leaderboard-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: rgba(255,255,255,0.03); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); padding: 12px 24px; border-bottom: 1px solid var(--border); }}
        td {{ padding: 16px 24px; border-bottom: 1px solid var(--border); font-size: 14px; color: var(--text-primary); }}
        tr:last-child td {{ border-bottom: none; }}
        .rank-1 {{ color: #fbbf24; font-weight: bold; }}
        .rank-2 {{ color: #9ca3af; font-weight: bold; }}
        .rank-3 {{ color: #cd7f32; font-weight: bold; }}
        .lb-score {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; }}
        .lb-status {{ font-size: 13px; }}

        /* Quick Start */
        .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
        .tab {{ background: transparent; border: none; color: var(--text-secondary); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;}}
        .tab.active {{ background: var(--accent-blue); color: white; }}
        .code-block {{ background: #020408; border: 1px solid var(--border); border-radius: 12px; padding: 24px; position: relative; display: none; overflow-x: auto; }}
        .code-block.active {{ display: block; }}
        .code-text {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.8; color: var(--text-primary); white-space: pre; }}
        .btn-copy {{ position: absolute; top: 12px; right: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border); color: var(--text-secondary); padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }}
        .btn-copy:hover {{ color: white; background: rgba(255,255,255,0.2); }}
        
        .code-comment {{ color: var(--text-dim); }}
        .code-str {{ color: var(--accent-green); }}
        .code-cmd {{ color: var(--accent-blue); }}
        .code-url {{ color: var(--accent-cyan); }}
        .code-key {{ color: var(--accent-yellow); }}

        /* Training Evidence */
        .training-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        @media (max-width: 900px) {{ .training-grid {{ grid-template-columns: 1fr; }} }}
        .train-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }}
        .train-title {{ font-size: 18px; font-weight: 600; margin-bottom: 24px; }}
        .train-row {{ margin-bottom: 24px; }}
        .train-label {{ font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }}
        .train-badge {{ padding: 4px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 12px; }}
        .train-desc {{ font-size: 14px; color: var(--text-secondary); line-height: 1.5; margin-left: 28px; }}
        .train-vis {{ float: left; font-size: 18px; margin-top: 2px; }}
        .train-table-row {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border); }}
        .train-table-row:last-child {{ border-bottom: none; }}
        .tt-key {{ font-size: 13px; color: var(--text-secondary); }}
        .tt-val {{ font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); }}
        
        /* Footer */
        footer {{ background: var(--bg-secondary); border-top: 1px solid var(--border); padding: 48px 0 32px; margin-top: 80px; }}
        .footer-grid {{ display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 32px; }}
        @media (max-width: 768px) {{ .footer-grid {{ grid-template-columns: 1fr; }} }}
        .f-title {{ font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }}
        .f-text {{ font-size: 13px; color: var(--text-dim); line-height: 1.6; }}
        .f-links {{ display: flex; flex-direction: column; gap: 12px; }}
        .f-link {{ font-size: 13px; color: var(--text-secondary); transition: color 0.2s; }}
        .f-link:hover {{ color: var(--text-primary); }}
        .f-social {{ display: flex; gap: 16px; margin-top: 16px; }}
        .f-bottom {{ border-top: 1px solid var(--border); margin-top: 32px; padding-top: 24px; display: flex; justify-content: space-between; font-size: 12px; color: var(--text-dim); }}
        @media (max-width: 640px) {{ .f-bottom {{ flex-direction: column; gap: 8px; text-align: center; }} }}
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
                <div class="status-pill" id="nav-status">
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
            <p class="hero-desc">The first OpenEnv RL environment for production incident response.<br>7 tasks · 14 actions · Curriculum learning · Dual-agent mode · Trained Llama-3B</p>
            
            <div class="hero-buttons">
                <a href="/docs" class="btn-primary">Try Live API &rarr;</a>
                <a href="https://github.com/Twilight-13/devops-incident-response" target="_blank" class="btn-secondary">View on GitHub &rarr;</a>
            </div>
            
            <div class="hero-stats">
                <div class="stat-card">
                    <div class="stat-val">7</div>
                    <div class="stat-label">Tasks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">14</div>
                    <div class="stat-label">Actions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">&infin;</div>
                    <div class="stat-label">Scenarios</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">0.99</div>
                    <div class="stat-label">Max Score</div>
                </div>
            </div>
        </section>
        
        <section class="fade-in">
            <h2 class="section-title">Environment Tasks</h2>
            <p class="section-subtitle">Eight scenarios of escalating operational complexity</p>
            
            <div class="task-grid" id="task-grid">
                <!-- Populated by JS -->
                <div style="grid-column: 1/-1; text-align: center; color: var(--text-dim);">Loading tasks...</div>
            </div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">ARIA Features</h2>
            <p class="section-subtitle">What makes this environment unique</p>
            
            <div class="features-grid">
                <!-- Curriculum -->
                <div class="feature-card">
                    <div class="feature-icon">🎓</div>
                    <h3 class="feature-title">Curriculum Engine</h3>
                    <p class="feature-desc">Tracks agent performance per task with rolling averages. Promotes when mastered (avg > 0.75). Scaffolds with hints when struggling (avg < 0.30). Agents always train at the edge of their capability.</p>
                    
                    <div class="curriculum-bars" id="curriculum-container">
                        <!-- Populated by JS -->
                        <div style="text-align: center; color: var(--text-dim); font-size: 13px;">Loading curriculum data...</div>
                    </div>
                    
                    <a href="/curriculum/status" class="feature-link" style="color: var(--accent-blue);">View Status &rarr;</a>
                </div>
                
                <!-- Generator -->
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
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;" id="gen-desc"></div>
                        <div class="gen-diff-bar"><div class="gen-diff-fill" id="gen-diff-fill"></div></div>
                    </div>
                    
                    <a href="/generate/preview?seed=42" class="feature-link" style="color: var(--accent-purple);">Try Generator &rarr;</a>
                </div>
                
                <!-- Dual Agent -->
                <div class="feature-card">
                    <div class="feature-icon">🤝</div>
                    <h3 class="feature-title">Dual-Agent Mode</h3>
                    <p class="feature-desc">Split observability between two agents. Observer sees logs and alerts. Responder sees metrics and dependencies. Neither can solve the incident alone — they must coordinate via share_finding.</p>
                    
                    <div class="dual-diagram">
                        <div class="agent-box">
                            <div style="font-weight:700; margin-bottom:4px;">AGENT A</div>
                            <div style="color:var(--text-dim); margin-bottom:4px;">Observer</div>
                            <div>• alerts<br>• logs</div>
                        </div>
                        <div class="agent-arrow">share<br>finding</div>
                        <div class="agent-box">
                            <div style="font-weight:700; margin-bottom:4px;">AGENT B</div>
                            <div style="color:var(--text-dim); margin-bottom:4px;">Responder</div>
                            <div>• metrics<br>• deps</div>
                        </div>
                    </div>
                    
                    <button class="btn-green" onclick="startDualSession()">Start Session</button>
                    <div class="session-info" id="dual-session-info"></div>
                    
                    <a href="/multi-agent/sessions" class="feature-link" style="color: var(--accent-green);">View Sessions &rarr;</a>
                </div>
            </div>
        </section>
        
    </main>

    <div class="metrics-bar-container fade-in">
        <div class="container metrics-grid" id="metrics-grid">
            <div class="metric-item">
                <div class="metric-val" id="m-episodes">--</div>
                <div class="metric-label">Total Episodes</div>
            </div>
            <div class="metric-item">
                <div class="metric-val" id="m-avg">--</div>
                <div class="metric-label">Avg Score</div>
            </div>
            <div class="metric-item">
                <div class="metric-val" id="m-res">--</div>
                <div class="metric-label">Resolution Rate</div>
            </div>
            <div class="metric-item">
                <div class="metric-val" id="m-best">--</div>
                <div class="metric-label">Best Score</div>
            </div>
        </div>
    </div>

    <main class="container">
        <section class="fade-in">
            <h2 class="section-title">🏆 Leaderboard</h2>
            <p class="section-subtitle">Top episodes by score</p>
            
            <div class="leaderboard-card">
                <table>
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Task</th>
                            <th>Score</th>
                            <th>Steps</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="lb-body">
                        <tr><td colspan="5" style="text-align: center; color: var(--text-dim);">Loading leaderboard...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">Quick Start</h2>
            <p class="section-subtitle">Run your first episode in seconds</p>
            
            <div class="tabs">
                <button class="tab active" onclick="switchTab('curl')">curl</button>
                <button class="tab" onclick="switchTab('python')">Python</button>
            </div>
            
            <div id="code-curl" class="code-block active">
                <button class="btn-copy" onclick="copyCode('code-curl-text', this)">Copy</button>
                <div class="code-text" id="code-curl-text"><span class="code-comment"># 1. Start an incident</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/reset \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{{<span class="code-key">"task_id"</span>: <span class="code-str">"easy"</span>, <span class="code-key">"seed"</span>: 42}}'</span>

<span class="code-comment"># 2. Read logs (reward: +0.15)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{{<span class="code-key">"action_type"</span>: <span class="code-str">"read_logs"</span>, <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}}'</span>

<span class="code-comment"># 3. Diagnose (reward: +0.30)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{{<span class="code-key">"action_type"</span>: <span class="code-str">"diagnose"</span>, <span class="code-key">"root_cause"</span>: <span class="code-str">"memory leak in payment-service"</span>}}'</span>

<span class="code-comment"># 4. Fix it (reward: +0.40)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{{<span class="code-key">"action_type"</span>: <span class="code-str">"restart_service"</span>, <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}}'</span>

<span class="code-comment"># Score: ~0.94 ✅</span></div>
            </div>
            
            <div id="code-python" class="code-block">
                <button class="btn-copy" onclick="copyCode('code-py-text', this)">Copy</button>
                <div class="code-text" id="code-py-text"><span class="code-cmd">import</span> requests

BASE = <span class="code-str">"https://arijit-07-devops-incident-response.hf.space"</span>

<span class="code-comment"># Start episode</span>
obs = requests.post(<span class="code-url">f"{{BASE}}/reset"</span>, 
    json={{<span class="code-key">"task_id"</span>: <span class="code-str">"easy"</span>, <span class="code-key">"seed"</span>: 42}}).json()

<span class="code-comment"># Take action</span>
result = requests.post(<span class="code-url">f"{{BASE}}/step"</span>,
    json={{<span class="code-key">"action_type"</span>: <span class="code-str">"read_logs"</span>,
          <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}}).json()

print(<span class="code-url">f"Reward: {{result['reward']}}"</span>)  <span class="code-comment"># 0.15</span></div>
            </div>
        </section>

        <section class="fade-in">
            <h2 class="section-title">🧠 Training Evidence</h2>
            <p class="section-subtitle">Llama-3.2-3B fine-tuned with GRPO on this environment</p>
            
            <div class="training-grid">
                <div class="train-card">
                    <h3 class="train-title">Behavioral Change</h3>
                    
                    <div class="train-row">
                        <div class="train-label">
                            <span>Base Llama-3B</span>
                            <span class="train-badge" style="background: rgba(239, 68, 68, 0.2); color: #ef4444;">0.000</span>
                        </div>
                        <div class="train-vis" style="color: #ef4444;">❌</div>
                        <div class="train-desc">Jumps straight to diagnose without reading logs → triggers blind remediation penalty (-0.10)</div>
                    </div>
                    
                    <div class="train-row">
                        <div class="train-label">
                            <span>ARIA Fine-tuned (140 episodes)</span>
                            <span class="train-badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981;">0.150</span>
                        </div>
                        <div class="train-vis" style="color: #10b981;">✅</div>
                        <div class="train-desc">Consistently reads logs on correct failing service first → information gathering before acting</div>
                    </div>
                    
                    <a href="https://huggingface.co/Arijit-07/aria-devops-llama3b" target="_blank" class="feature-link" style="color: var(--accent-blue);">Model weights &rarr;</a>
                </div>
                
                <div class="train-card">
                    <h3 class="train-title">Training Setup</h3>
                    
                    <div class="train-table-row">
                        <div class="tt-key">Algorithm</div><div class="tt-val">GRPO</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">Framework</div><div class="tt-val">Unsloth + HuggingFace TRL</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">Base Model</div><div class="tt-val">Llama-3.2-3B-Instruct</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">LoRA Rank</div><div class="tt-val">16 (alpha: 32)</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">Episodes</div><div class="tt-val">140 (easy + medium)</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">GPU</div><div class="tt-val">Kaggle T4 x2</div>
                    </div>
                    <div class="train-table-row">
                        <div class="tt-key">Group Size</div><div class="tt-val">6 completions/step</div>
                    </div>
                    <div class="train-table-row" style="border-bottom: none;">
                        <div class="tt-key">KL Penalty</div><div class="tt-val">0.05</div>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <footer>
        <div class="container">
            <div class="footer-grid">
                <div>
                    <div style="font-size: 20px; font-weight: 700; color: var(--accent-blue); margin-bottom: 8px;">🚨 ARIA</div>
                    <div class="f-text">DevOps Incident Response<br>OpenEnv-compliant RL environment</div>
                    <div class="f-social">
                        <a href="https://github.com/Twilight-13/devops-incident-response" target="_blank" class="f-link">GitHub</a>
                        <a href="https://huggingface.co/Arijit-07/aria-devops-llama3b" target="_blank" class="f-link">HuggingFace Model</a>
                    </div>
                </div>
                <div>
                    <div class="f-title">Resources</div>
                    <div class="f-links">
                        <a href="/docs" class="f-link">Live API Docs</a>
                        <a href="/validate" class="f-link">Validate</a>
                        <a href="/metrics" class="f-link">Metrics</a>
                        <a href="/leaderboard" class="f-link">Leaderboard</a>
                        <a href="/curriculum/status" class="f-link">Curriculum</a>
                        <a href="/about" class="f-link">About</a>
                    </div>
                </div>
                <div>
                    <div class="f-title">Built for</div>
                    <div class="f-text">Meta × PyTorch × HuggingFace<br>OpenEnv Hackathon Finals<br>Bangalore, April 2026</div>
                    <div class="f-text" style="font-size: 12px; margin-top: 16px;">Solo project by Arijit</div>
                </div>
            </div>
            <div class="f-bottom">
                <div>&copy; 2026 ARIA — Apache 2.0 License</div>
                <div>Can your agent handle a SEV-1 at 3am?</div>
            </div>
        </div>
    </footer>

    <script>
        // 1. Canvas Particles
        const canvas = document.getElementById('bg-canvas');
        const ctx = canvas.getContext('2d');
        let width, height;
        let particles = [];

        function resize() {{
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
        }}
        window.addEventListener('resize', resize);
        resize();

        for(let i=0; i<60; i++) {{
            particles.push({{
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5
            }});
        }}

        function drawParticles() {{
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.05)';
            
            for(let i=0; i<particles.length; i++) {{
                let p = particles[i];
                p.x += p.vx; p.y += p.vy;
                
                if(p.x < 0 || p.x > width) p.vx *= -1;
                if(p.y < 0 || p.y > height) p.vy *= -1;
                
                ctx.beginPath();
                ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
                ctx.fill();
                
                for(let j=i+1; j<particles.length; j++) {{
                    let p2 = particles[j];
                    let dx = p.x - p2.x, dy = p.y - p2.y;
                    let dist = Math.sqrt(dx*dx + dy*dy);
                    if(dist < 150) {{
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.stroke();
                    }}
                }}
            }}
            requestAnimationFrame(drawParticles);
        }}
        drawParticles();

        // 2. Intersection Observer for Fade-in
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if(entry.isIntersecting) {{
                    entry.target.classList.add('visible');
                }}
            }});
        }}, {{ threshold: 0.1 }});
        document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

        // 3. Status Check
        fetch('/health')
            .then(r => r.json())
            .then(data => {{
                if(data.status === 'ok') {{
                    document.getElementById('nav-status-text').innerText = 'LIVE';
                }}
            }}).catch(e => console.error(e));

        // 4. Load Tasks
        const taskConfig = {{
            'easy': {{icon: '💻', color: '#10b981', badge: 'EASY'}},
            'medium': {{icon: '⚡', color: '#f59e0b', badge: 'MEDIUM'}},
            'hard': {{icon: '🔥', color: '#ef4444', badge: 'HARD'}},
            'bonus': {{icon: '💥', color: '#8b5cf6', badge: 'EXPERT'}},
            'security': {{icon: '🛡️', color: '#06b6d4', badge: 'SECURITY'}},
            'database': {{icon: '🗄️', color: '#f97316', badge: 'DATABASE'}},
            'failover': {{icon: '🌐', color: '#6366f1', badge: 'FAILOVER'}},
            'generated': {{icon: '✨', color: '#ec4899', badge: 'DYNAMIC'}}
        }};
        
        fetch('/tasks')
            .then(r => r.json())
            .then(data => {{
                const grid = document.getElementById('task-grid');
                grid.innerHTML = '';
                data.tasks.forEach(t => {{
                    const cfg = taskConfig[t.id] || taskConfig['easy'];
                    grid.innerHTML += `
                        <div class="task-card" style="--card-color: ${{cfg.color}}; --card-bg: ${{cfg.color}}20;">
                            <div class="task-header">
                                <div class="task-icon">${{cfg.icon}}</div>
                                <div class="task-badge">${{cfg.badge}}</div>
                            </div>
                            <div class="task-name">${{t.name}}</div>
                            <div class="task-desc">${{t.description}}</div>
                            <div class="task-footer">
                                <div class="task-steps">Max steps: ${{t.max_steps}}</div>
                                <div class="task-status">Ready</div>
                            </div>
                        </div>
                    `;
                }});
            }}).catch(e => console.error(e));

        // 5. Curriculum
        fetch('/curriculum/status')
            .then(r => r.json())
            .then(data => {{
                const container = document.getElementById('curriculum-container');
                if(data.total_episodes_recorded === 0) {{
                    container.innerHTML = '<div style="text-align: center; color: var(--text-dim); font-size: 13px;">No episodes recorded yet</div>';
                    return;
                }}
                container.innerHTML = '';
                const tasks = data.tasks || {{}};
                Object.keys(tasks).slice(0, 4).forEach(k => {{
                    let avg = tasks[k].rolling_avg;
                    let w = Math.max(5, avg * 100);
                    let color = avg < 0.3 ? 'var(--accent-red)' : (avg < 0.6 ? 'var(--accent-yellow)' : 'var(--accent-green)');
                    let blocks = Math.round(w / 10);
                    let fillStr = '█'.repeat(blocks);
                    let trackStr = '░'.repeat(10 - blocks);
                    container.innerHTML += `
                        <div class="c-bar-row">
                            <div class="c-bar-name">${{k}}</div>
                            <div class="c-bar-track" style="color: ${{color}}"><span class="c-bar-fill">${{fillStr}}</span><span style="opacity:0.3">${{trackStr}}</span></div>
                            <div class="c-bar-score">${{avg.toFixed(2)}}</div>
                        </div>
                    `;
                }});
            }}).catch(e => {{
                document.getElementById('curriculum-container').innerHTML = '<div style="text-align: center; color: var(--text-dim); font-size: 13px;">--</div>';
                console.error(e);
            }});

        // 6. Generator
        window.generateIncident = function() {{
            const seed = document.getElementById('gen-seed').value || 42;
            fetch(`/generate/preview?seed=${{seed}}`)
                .then(r => r.json())
                .then(data => {{
                    const cMap = {{oom: '#ef4444', cascade: '#f59e0b', corruption: '#8b5cf6', security: '#06b6d4', database: '#f97316', network_partition: '#6366f1'}};
                    const sMap = {{sev1: '#ef4444', sev2: '#f59e0b', sev3: '#10b981'}};
                    const fColor = cMap[data.failure_mode] || '#3b82f6';
                    
                    document.getElementById('gen-badges').innerHTML = `
                        <span class="gen-badge" style="background:${{fColor}}20; color:${{fColor}}">${{data.failure_mode}}</span>
                        <span class="gen-badge" style="background:${{sMap[data.severity] || '#3b82f6'}}20; color:${{sMap[data.severity] || '#3b82f6'}}">${{data.severity}}</span>
                        <span class="gen-badge" style="background:rgba(255,255,255,0.1); color:var(--text-secondary)">${{data.incident_id}}</span>
                    `;
                    document.getElementById('gen-affected').innerText = `Affected: ${{data.affected_service}}`;
                    document.getElementById('gen-desc').innerText = data.description;
                    
                    let dColor = data.difficulty_score < 0.4 ? '#10b981' : (data.difficulty_score < 0.7 ? '#f59e0b' : '#ef4444');
                    document.getElementById('gen-diff-fill').style.width = `${{data.difficulty_score * 100}}%`;
                    document.getElementById('gen-diff-fill').style.background = dColor;
                    
                    document.getElementById('gen-result').style.display = 'block';
                }}).catch(e => console.error(e));
        }};

        // 7. Dual Agent
        window.startDualSession = function() {{
            fetch('/multi-agent/reset', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{task_id: "easy", seed: 42}})
            }}).then(r => r.json())
              .then(data => {{
                  const info = document.getElementById('dual-session-info');
                  info.innerHTML = `Session: ${{data.session_id}}<br><br>Agent A (POST): /multi-agent/step/a/${{data.session_id}}<br>Agent B (POST): /multi-agent/step/b/${{data.session_id}}`;
                  info.style.display = 'block';
              }}).catch(e => console.error(e));
        }};

        // 8. Live Metrics
        function loadMetrics() {{
            fetch('/metrics')
                .then(r => r.json())
                .then(data => {{
                    document.getElementById('m-episodes').innerText = data.total_episodes || 0;
                    document.getElementById('m-avg').innerText = (data.overall_avg_score || 0).toFixed(3);
                    
                    // calculate overall resolution rate
                    if (data.by_task) {{
                        let totalRes = 0, totalCount = 0;
                        let bestScore = 0;
                        Object.values(data.by_task).forEach(t => {{
                            totalRes += t.resolution_rate * t.count;
                            totalCount += t.count;
                            if (t.max_score > bestScore) bestScore = t.max_score;
                        }});
                        let resRate = totalCount > 0 ? (totalRes / totalCount) * 100 : 0;
                        document.getElementById('m-res').innerText = resRate.toFixed(1) + '%';
                        document.getElementById('m-best').innerText = bestScore.toFixed(3);
                    }}
                }}).catch(e => console.error(e));
        }}
        loadMetrics();
        setInterval(loadMetrics, 30000);

        // 9. Leaderboard
        fetch('/leaderboard')
            .then(r => r.json())
            .then(data => {{
                const tbody = document.getElementById('lb-body');
                if(!data.leaderboard || data.leaderboard.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No episodes yet. Try POST /reset to start your first episode.</td></tr>';
                    return;
                }}
                tbody.innerHTML = '';
                data.leaderboard.forEach(row => {{
                    let rClass = row.rank <= 3 ? `rank-${{row.rank}}` : '';
                    let sColor = row.score >= 0.8 ? '#10b981' : (row.score >= 0.5 ? '#f59e0b' : '#ef4444');
                    let statusHtml = row.score > 0.5 ? '<span style="color:#10b981">✅ Resolved</span>' : '<span style="color:#ef4444">❌ Failed</span>'; // Simple heuristic if resolution missing
                    
                    tbody.innerHTML += `
                        <tr>
                            <td class="${{rClass}}">#${{row.rank}}</td>
                            <td>${{row.task_id}}</td>
                            <td class="lb-score" style="color: ${{sColor}}">${{row.score.toFixed(4)}}</td>
                            <td>${{row.steps}}</td>
                            <td class="lb-status">${{statusHtml}}</td>
                        </tr>
                    `;
                }});
            }}).catch(e => console.error(e));

        // 10. Tabs
        window.switchTab = function(type) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.code-block').forEach(c => c.classList.remove('active'));
            if(type === 'curl') {{
                document.querySelectorAll('.tab')[0].classList.add('active');
                document.getElementById('code-curl').classList.add('active');
            }} else {{
                document.querySelectorAll('.tab')[1].classList.add('active');
                document.getElementById('code-python').classList.add('active');
            }}
        }};

        window.copyCode = function(id, btn) {{
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(() => {{
                let old = btn.innerText;
                btn.innerText = 'Copied ✓';
                setTimeout(() => btn.innerText = old, 2000);
            }});
        }};
    </script>
</body>
</html>
"""
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

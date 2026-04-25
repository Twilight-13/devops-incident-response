import re

html_content = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARIA - DevOps Incident Response</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
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
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
        }
        html { scroll-behavior: smooth; }
        a { text-decoration: none; color: inherit; }
        
        /* Animation */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in {
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.6s ease-out, transform 0.6s ease-out;
        }
        .fade-in.visible { opacity: 1; transform: translateY(0); }

        /* Canvas Background */
        #bg-canvas {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 0;
            pointer-events: none;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
            position: relative;
            z-index: 1;
        }
        section { padding: 80px 0; }

        /* Navbar */
        nav {
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
        }
        .nav-inner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
        }
        .nav-left { display: flex; align-items: center; gap: 8px; }
        .nav-logo { font-size: 20px; font-weight: 700; color: var(--blue); }
        .nav-desc { font-size: 13px; color: var(--muted); display: none; }
        @media (min-width: 768px) { .nav-desc { display: block; } }
        
        .nav-center { display: flex; justify-content: center; flex: 1; }
        .status-pill {
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
        }
        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
        
        .nav-right { display: flex; gap: 24px; }
        .nav-link { font-size: 13px; color: var(--muted); transition: color 0.2s; }
        .nav-link:hover { color: var(--text); }

        /* Hero */
        .hero { padding: 120px 0 80px; text-align: center; }
        .hero-badge {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 999px;
            padding: 6px 16px;
            font-size: 12px;
            color: var(--blue);
            display: inline-block;
            margin-bottom: 24px;
        }
        .hero-title {
            font-size: clamp(72px, 12vw, 140px);
            font-weight: 700;
            background: linear-gradient(135deg, var(--blue) 0%, var(--cyan) 50%, var(--purple) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1;
            letter-spacing: -4px;
        }
        .hero-subtitle { font-size: 20px; color: var(--muted); margin-top: 16px; font-weight: 400; }
        .hero-desc { font-size: 15px; color: #4b5563; margin-top: 12px; line-height: 1.6; max-width: 600px; margin-inline: auto; }
        
        .hero-buttons { margin-top: 40px; display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; }
        .btn-primary, .btn-secondary {
            padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; transition: all 0.2s; cursor: pointer; display: inline-block;
        }
        .btn-primary { background: var(--blue); color: white; border: none; }
        .btn-primary:hover { background: #2563eb; transform: translateY(-2px); }
        .btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--muted); }
        .btn-secondary:hover { border-color: var(--blue); color: white; transform: translateY(-2px); }

        .hero-stats { margin-top: 64px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px 32px; text-align: center; }
        .stat-val { font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; color: var(--blue); }
        .stat-label { font-size: 13px; color: var(--muted); margin-top: 4px; }

        .section-title { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
        .section-subtitle { font-size: 15px; color: var(--muted); margin-bottom: 32px; }

        /* Tasks Grid */
        .task-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
        @media (max-width: 1024px) { .task-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 640px) { .task-grid { grid-template-columns: 1fr; } }
        
        .task-card {
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 24px;
            transition: all 0.3s; cursor: pointer; position: relative; overflow: hidden; display: flex; flex-direction: column;
        }
        .task-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: transparent; transition: all 0.3s; }
        .task-card:hover { transform: translateY(-4px); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }
        .task-card:hover::before { background: var(--card-color, var(--border)); }
        
        .task-header { display: flex; justify-content: space-between; align-items: flex-start; }
        .task-icon { font-size: 32px; }
        .task-badge { font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; background: var(--card-bg); color: var(--card-color); letter-spacing: 0.5px; }
        .task-name { font-size: 16px; font-weight: 600; margin-top: 16px; }
        .task-desc { font-size: 13px; color: var(--muted); margin-top: 8px; line-height: 1.5; flex-grow: 1; }
        .task-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }
        .task-steps { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #4b5563; }
        .task-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--card-color); font-weight: 500; }
        .task-status::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--card-color); }

        /* Features */
        .features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
        @media (max-width: 900px) { .features-grid { grid-template-columns: 1fr; } }
        .feature-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }
        .feature-icon { font-size: 48px; margin-bottom: 24px; }
        .feature-title { font-size: 20px; font-weight: 600; margin-bottom: 12px; color: var(--text); }
        .feature-desc { font-size: 14px; color: var(--muted); line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }
        
        .c-bar-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: 12px; font-family: 'JetBrains Mono', monospace; }
        .c-bar-name { color: var(--muted); width: 80px; overflow: hidden; text-overflow: ellipsis; }
        .c-bar-track { flex-grow: 1; margin: 0 12px; letter-spacing: -2px; color: #4b5563; }
        .c-bar-score { width: 30px; text-align: right; }
        
        .generator-input { display: flex; gap: 8px; margin-bottom: 16px; }
        .gen-seed { background: #0d1117; border: 1px solid var(--border); color: white; padding: 8px 12px; border-radius: 6px; width: 80px; font-family: 'JetBrains Mono', monospace; }
        .btn-gen { background: var(--purple); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .gen-result { background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: none; }
        .gen-badges { display: flex; gap: 8px; margin-bottom: 12px; }
        .gen-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
        .gen-diff-bar { height: 4px; background: var(--border); border-radius: 2px; margin: 12px 0; overflow: hidden; }
        
        .dual-diagram { background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-bottom: 24px; color: var(--muted); display: flex; justify-content: space-between; align-items: center; }
        .agent-box { border: 1px solid var(--border); padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.2); width: 42%; }
        .agent-arrow { flex-grow: 1; text-align: center; color: var(--green); position: relative; }
        .agent-arrow::after { content: '→'; position: absolute; top: -10px; left: 50%; transform: translateX(-50%); animation: flowRight 1.5s infinite linear; }
        @keyframes flowRight { 0% { left: 20%; opacity: 0; } 50% { opacity: 1; } 100% { left: 80%; opacity: 0; } }
        .btn-green { background: var(--green); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
        
        .feature-link { color: var(--blue); font-size: 14px; font-weight: 500; margin-top: 16px; display: inline-block; }
        
        /* Live Metrics */
        .metrics-bar { background: #0d1117; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 24px 0; }
        .metrics-grid { display: flex; justify-content: space-between; }
        .metric-item { text-align: center; flex: 1; border-right: 1px solid var(--border); }
        .metric-item:last-child { border-right: none; }
        .metric-val { font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; color: var(--blue); }
        .metric-label { font-size: 12px; color: var(--muted); margin-top: 4px; }
        @media (max-width: 640px) { .metrics-grid { flex-wrap: wrap; gap: 24px; } .metric-item { min-width: 40%; border: none; } }

        /* Leaderboard */
        .leaderboard-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: rgba(255,255,255,0.03); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #4b5563; padding: 12px 24px; border-bottom: 1px solid var(--border); }
        td { padding: 16px 24px; border-bottom: 1px solid var(--border); font-size: 14px; }
        tr:last-child td { border-bottom: none; }
        .lb-score { font-family: 'JetBrains Mono', monospace; font-weight: 600; }

        /* Quick Start */
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; }
        .tab { background: transparent; border: none; color: var(--muted); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;}
        .tab.active { background: var(--blue); color: white; }
        .code-block { background: #020408; border: 1px solid var(--border); border-radius: 12px; padding: 24px; position: relative; display: none; overflow-x: auto; }
        .code-block.active { display: block; }
        .code-text { font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.8; color: var(--text); white-space: pre; }
        .btn-copy { position: absolute; top: 12px; right: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border); color: var(--muted); padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }
        
        .c-com { color: #4b5563; } .c-str { color: var(--green); } .c-cmd { color: var(--blue); } .c-url { color: var(--cyan); } .c-key { color: var(--yellow); }

        /* Training Evidence */
        .training-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        @media (max-width: 900px) { .training-grid { grid-template-columns: 1fr; } }
        .train-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }
        .train-title { font-size: 18px; font-weight: 600; margin-bottom: 24px; }
        .train-row { margin-bottom: 24px; }
        .train-label { font-size: 12px; color: var(--muted); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
        .train-badge { padding: 4px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 600; }
        .train-desc { font-size: 14px; color: var(--muted); line-height: 1.5; margin-left: 28px; }
        .train-vis { float: left; font-size: 18px; margin-top: 2px; }
        .tt-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border); }
        .tt-row:last-child { border-bottom: none; }
        .tt-key { font-size: 13px; color: var(--muted); }
        .tt-val { font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text); }
        
        /* Footer */
        footer { background: #0d1117; border-top: 1px solid var(--border); padding: 48px 0 32px; margin-top: 80px; }
        .footer-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 32px; }
        @media (max-width: 768px) { .footer-grid { grid-template-columns: 1fr; } }
        .f-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
        .f-text { font-size: 13px; color: #4b5563; line-height: 1.6; }
        .f-links { display: flex; flex-direction: column; gap: 12px; }
        .f-link { font-size: 13px; color: var(--muted); transition: color 0.2s; }
        .f-link:hover { color: var(--text); }
        .f-bottom { border-top: 1px solid var(--border); margin-top: 32px; padding-top: 24px; display: flex; justify-content: space-between; font-size: 12px; color: #4b5563; }
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
  -d <span class="c-str">'{<span class="c-key">"task_id"</span>: <span class="c-str">"easy"</span>, <span class="c-key">"seed"</span>: 42}'</span>

<span class="c-com"># 2. Read logs (reward: +0.15)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{<span class="c-key">"action_type"</span>: <span class="c-str">"read_logs"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}'</span>

<span class="c-com"># 3. Diagnose (reward: +0.30)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{<span class="c-key">"action_type"</span>: <span class="c-str">"diagnose"</span>, <span class="c-key">"root_cause"</span>: <span class="c-str">"memory leak in payment-service"</span>}'</span>

<span class="c-com"># 4. Fix it (reward: +0.40)</span>
<span class="c-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="c-str">"Content-Type: application/json"</span> \
  -d <span class="c-str">'{<span class="c-key">"action_type"</span>: <span class="c-str">"restart_service"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}'</span>

<span class="c-com"># Score: ~0.94 ✅</span></div>
            </div>
            
            <div id="code-python" class="code-block">
                <button class="btn-copy" onclick="copyCode('code-py-text', this)">Copy</button>
                <div class="code-text" id="code-py-text"><span class="c-cmd">import</span> requests
BASE = <span class="c-str">"https://arijit-07-devops-incident-response.hf.space"</span>

<span class="c-com"># Start episode</span>
obs = requests.post(<span class="c-url">f"{BASE}/reset"</span>, json={<span class="c-key">"task_id"</span>: <span class="c-str">"easy"</span>, <span class="c-key">"seed"</span>: 42}).json()

<span class="c-com"># Take action</span>
result = requests.post(<span class="c-url">f"{BASE}/step"</span>,
    json={<span class="c-key">"action_type"</span>: <span class="c-str">"read_logs"</span>, <span class="c-key">"service"</span>: <span class="c-str">"payment-service"</span>}).json()

print(<span class="c-url">f"Reward: {result['reward']}"</span>)  <span class="c-com"># 0.15</span></div>
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

        function resize() { width = canvas.width = window.innerWidth; height = canvas.height = window.innerHeight; }
        window.addEventListener('resize', resize); resize();

        for(let i=0; i<50; i++) {
            particles.push({ x: Math.random() * width, y: Math.random() * height, vx: (Math.random()-0.5)*0.5, vy: (Math.random()-0.5)*0.5 });
        }

        function draw() {
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.1)';
            for(let i=0; i<particles.length; i++) {
                let p = particles[i];
                p.x += p.vx; p.y += p.vy;
                if(p.x < 0 || p.x > width) p.vx *= -1;
                if(p.y < 0 || p.y > height) p.vy *= -1;
                ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI*2); ctx.fill();
                for(let j=i+1; j<particles.length; j++) {
                    let p2 = particles[j], dist = Math.hypot(p.x-p2.x, p.y-p2.y);
                    if(dist < 150) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p2.x, p2.y); ctx.stroke(); }
                }
            }
            requestAnimationFrame(draw);
        }
        draw();

        const observer = new IntersectionObserver(e => e.forEach(en => { if(en.isIntersecting) en.target.classList.add('visible'); }), {threshold: 0.1});
        document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

        fetch('/health').then(r => r.json()).then(d => {
            if(d.status === 'ok') document.getElementById('nav-status-text').innerText = 'LIVE';
        }).catch(e => console.error(e));

        const tMap = {
            'easy': {icon: '💻', color: '#10b981', badge: 'EASY'}, 'medium': {icon: '⚡', color: '#f59e0b', badge: 'MEDIUM'},
            'hard': {icon: '🔥', color: '#ef4444', badge: 'HARD'}, 'bonus': {icon: '💥', color: '#8b5cf6', badge: 'EXPERT'},
            'security': {icon: '🛡️', color: '#06b6d4', badge: 'SECURITY'}, 'database': {icon: '🗄️', color: '#f97316', badge: 'DATABASE'},
            'failover': {icon: '🌐', color: '#6366f1', badge: 'FAILOVER'}, 'generated': {icon: '✨', color: '#ec4899', badge: 'DYNAMIC'}
        };
        fetch('/tasks').then(r => r.json()).then(d => {
            document.getElementById('task-grid').innerHTML = d.tasks.map(t => {
                let c = tMap[t.id] || tMap['easy'];
                return `<div class="task-card" style="--card-color:${c.color};--card-bg:${c.color}20;">
                    <div class="task-header"><div class="task-icon">${c.icon}</div><div class="task-badge">${c.badge}</div></div>
                    <div class="task-name">${t.name}</div><div class="task-desc">${t.description}</div>
                    <div class="task-footer"><div class="task-steps">Max steps: ${t.max_steps}</div><div class="task-status">Ready</div></div>
                </div>`;
            }).join('');
        }).catch(e => console.error(e));

        fetch('/curriculum/status').then(r => r.json()).then(d => {
            const el = document.getElementById('curriculum-container');
            if(!d.total_episodes_recorded) el.innerHTML = '<div style="color:var(--muted); font-size:13px; text-align:center;">No episodes yet — run POST /reset to begin</div>';
            else {
                el.innerHTML = Object.keys(d.tasks).slice(0, 4).map(k => {
                    let avg = d.tasks[k].rolling_avg, col = avg < 0.3 ? 'var(--red)' : (avg < 0.6 ? 'var(--yellow)' : 'var(--green)');
                    let bl = Math.round(avg * 10);
                    return `<div class="c-bar-row"><div class="c-bar-name">${k}</div>
                    <div class="c-bar-track" style="color:${col}"><span>${'█'.repeat(bl)}</span><span style="opacity:0.3">${'░'.repeat(10-bl)}</span></div>
                    <div class="c-bar-score">${avg.toFixed(2)}</div></div>`;
                }).join('');
            }
        }).catch(e => console.error(e));

        window.generateIncident = () => {
            const seed = document.getElementById('gen-seed').value || 42;
            fetch(`/generate/preview?seed=${seed}`).then(r => r.json()).then(d => {
                const colors = {oom: '#ef4444', cascade: '#f59e0b', corruption: '#8b5cf6', security: '#06b6d4', database: '#f97316', network_partition: '#6366f1'};
                const sc = {sev1: '#ef4444', sev2: '#f59e0b', sev3: '#10b981'};
                let fcol = colors[d.failure_mode] || 'var(--blue)';
                document.getElementById('gen-badges').innerHTML = `<span class="gen-badge" style="background:${fcol}20;color:${fcol}">${d.failure_mode}</span><span class="gen-badge" style="background:${sc[d.severity]||fcol}20;color:${sc[d.severity]||fcol}">${d.severity}</span><span class="gen-badge" style="background:rgba(255,255,255,0.1);color:var(--muted)">${d.incident_id}</span>`;
                document.getElementById('gen-affected').innerText = `Affected: ${d.affected_service}`;
                document.getElementById('gen-desc').innerText = d.description;
                let dc = d.difficulty_score < 0.4 ? 'var(--green)' : (d.difficulty_score < 0.7 ? 'var(--yellow)' : 'var(--red)');
                let fill = document.getElementById('gen-diff-fill');
                fill.style.width = `${d.difficulty_score*100}%`; fill.style.background = dc;
                document.getElementById('gen-result').style.display = 'block';
            }).catch(e => console.error(e));
        };

        window.startDualSession = () => {
            fetch('/multi-agent/reset', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task_id: "easy", seed: 42}) })
            .then(r => r.json()).then(d => {
                let info = document.getElementById('dual-session-info');
                info.innerHTML = `Session: ${d.session_id}<br><br>Agent A (POST): /multi-agent/step/a/${d.session_id}<br>Agent B (POST): /multi-agent/step/b/${d.session_id}`;
                info.style.display = 'block';
            }).catch(e => console.error(e));
        };

        const loadMetrics = () => {
            fetch('/metrics').then(r => r.json()).then(d => {
                document.getElementById('m-episodes').innerText = d.total_episodes || 0;
                document.getElementById('m-avg').innerText = (d.overall_avg_score || 0).toFixed(3);
                if(d.by_task) {
                    let tRes = 0, tCnt = 0, best = 0;
                    Object.values(d.by_task).forEach(t => { tRes += t.resolution_rate*t.count; tCnt += t.count; if(t.max_score > best) best = t.max_score; });
                    document.getElementById('m-res').innerText = (tCnt ? (tRes/tCnt)*100 : 0).toFixed(1) + '%';
                    document.getElementById('m-best').innerText = best.toFixed(3);
                }
            }).catch(e => console.error(e));
        };
        loadMetrics(); setInterval(loadMetrics, 30000);

        fetch('/leaderboard').then(r => r.json()).then(d => {
            const body = document.getElementById('lb-body');
            if(!d.leaderboard || !d.leaderboard.length) { body.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--muted);">No episodes yet. Try POST /reset to start.</td></tr>'; return; }
            body.innerHTML = d.leaderboard.map(r => {
                let rank = r.rank === 1 ? 'color:#fbbf24;font-weight:bold' : (r.rank === 2 ? 'color:#9ca3af;font-weight:bold' : (r.rank === 3 ? 'color:#cd7f32;font-weight:bold' : ''));
                let sCol = r.score >= 0.8 ? 'var(--green)' : (r.score >= 0.5 ? 'var(--yellow)' : 'var(--red)');
                let status = r.score > 0.5 ? '<span style="color:var(--green)">✅ Resolved</span>' : '<span style="color:var(--red)">❌ Failed</span>';
                return `<tr><td style="${rank}">#${r.rank}</td><td>${r.task_id}</td><td class="lb-score" style="color:${sCol}">${r.score.toFixed(4)}</td><td>${r.steps}</td><td>${status}</td></tr>`;
            }).join('');
        }).catch(e => console.error(e));

        window.switchTab = t => {
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.code-block').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab')[t === 'curl' ? 0 : 1].classList.add('active');
            document.getElementById('code-'+t).classList.add('active');
        };

        window.copyCode = (id, btn) => {
            navigator.clipboard.writeText(document.getElementById(id).innerText).then(() => {
                let old = btn.innerText; btn.innerText = 'Copied ✓'; setTimeout(() => btn.innerText = old, 2000);
            });
        };
    </script>
</body>
</html>"""

import re
import sys

# Escape { and } properly to {{ and }}
# But since html_content is just a raw python string we actually just escape it.
html_escaped = html_content.replace("{", "{{").replace("}", "}}")

with open("server/app.py", "r", encoding="utf-8") as f:
    app_text = f.read()

# Replace the current dashboard endpoint
start_idx = app_text.find("def dashboard():")
end_idx = app_text.find('    return html', start_idx) + len('    return html')

if start_idx == -1 or end_idx == -1:
    print("Could not find dashboard.")
    sys.exit(1)

new_dashboard = f'''def dashboard():
    html = f"""{html_escaped}"""
    return html'''


new_text = app_text[:start_idx] + new_dashboard + app_text[end_idx:]

with open("server/app.py", "w", encoding="utf-8") as f:
    f.write(new_text)

print("Dashboard replaced successfully.")

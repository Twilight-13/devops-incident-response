html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARIA - DevOps Incident Response</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
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
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        a { text-decoration: none; color: inherit; }

        /* Animation */
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

        /* Container */
        .container {
            max-width: 1280px;
            margin: 0 auto;
            padding: 0 24px;
            position: relative;
            z-index: 1;
        }
        
        /* Section Spacing */
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
        .nav-logo { font-size: 20px; font-weight: 700; color: var(--accent-blue); display: flex; align-items: center; gap: 6px; }
        .nav-desc { font-size: 13px; color: var(--text-secondary); margin-left: 8px; display: none; }
        @media (min-width: 768px) { .nav-desc { display: block; } }
        
        .nav-center { display: flex; justify-content: center; flex: 1; }
        .status-pill {
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
        }
        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--accent-green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
        
        .nav-right { display: flex; gap: 24px; }
        .nav-link { font-size: 13px; color: var(--text-secondary); transition: color 0.2s; }
        .nav-link:hover { color: var(--text-primary); }

        /* Hero Section */
        .hero { padding: 120px 0 80px; text-align: center; }
        .hero-badge {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 999px;
            padding: 6px 16px;
            font-size: 12px;
            color: var(--accent-blue);
            display: inline-block;
            margin-bottom: 24px;
        }
        .hero-title {
            font-size: clamp(72px, 12vw, 140px);
            font-weight: 700;
            background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 50%, #8b5cf6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1;
            letter-spacing: -4px;
        }
        .hero-subtitle { font-size: 20px; color: var(--text-secondary); margin-top: 16px; font-weight: 400; }
        .hero-desc { font-size: 15px; color: var(--text-dim); margin-top: 12px; line-height: 1.6; max-width: 600px; margin-inline: auto; }
        
        .hero-buttons { margin-top: 40px; display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; }
        .btn-primary, .btn-secondary {
            padding: 14px 28px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 15px;
            transition: all 0.2s;
            cursor: pointer;
            display: inline-block;
        }
        .btn-primary { background: var(--accent-blue); color: white; border: none; }
        .btn-primary:hover { background: #2563eb; transform: translateY(-2px); }
        .btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }
        .btn-secondary:hover { border-color: var(--accent-blue); color: white; transform: translateY(-2px); }

        .hero-stats {
            margin-top: 64px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 32px;
            text-align: center;
        }
        .stat-val { font-family: 'JetBrains Mono', monospace; font-size: 32px; font-weight: 700; color: var(--accent-blue); }
        .stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

        /* General Sections */
        .section-title { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
        .section-subtitle { font-size: 15px; color: var(--text-secondary); margin-bottom: 32px; }

        /* Task Cards */
        .task-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
        @media (max-width: 1024px) { .task-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 640px) { .task-grid { grid-template-columns: 1fr; } }

        .task-card {
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
        }
        .task-card::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
            background: transparent; transition: all 0.3s;
        }
        .task-card:hover {
            background: var(--bg-card-hover);
            transform: translateY(-4px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .task-card:hover::before { background: var(--card-color, var(--border)); }
        
        .task-header { display: flex; justify-content: space-between; align-items: flex-start; }
        .task-icon { font-size: 32px; }
        .task-badge {
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            background: var(--card-bg);
            color: var(--card-color);
            letter-spacing: 0.5px;
        }
        .task-name { font-size: 16px; font-weight: 600; margin-top: 16px; }
        .task-desc { font-size: 13px; color: var(--text-secondary); margin-top: 8px; line-height: 1.5; flex-grow: 1; }
        .task-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }
        .task-steps { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-dim); }
        .task-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--card-color); font-weight: 500; }
        .task-status::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--card-color); }

        /* Features */
        .features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
        @media (max-width: 900px) { .features-grid { grid-template-columns: 1fr; } }
        
        .feature-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            display: flex;
            flex-direction: column;
        }
        .feature-icon { font-size: 48px; margin-bottom: 24px; }
        .feature-title { font-size: 20px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }
        .feature-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }
        
        .curriculum-bars { margin-bottom: 24px; }
        .c-bar-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: 12px; font-family: 'JetBrains Mono', monospace; }
        .c-bar-name { color: var(--text-secondary); width: 80px; overflow: hidden; text-overflow: ellipsis; }
        .c-bar-track { flex-grow: 1; margin: 0 12px; letter-spacing: -2px; color: var(--text-dim); }
        .c-bar-fill { letter-spacing: -2px; }
        .c-bar-score { width: 30px; text-align: right; }
        
        .generator-input {
            display: flex; gap: 8px; margin-bottom: 16px;
        }
        .gen-seed {
            background: var(--bg-secondary); border: 1px solid var(--border); color: white;
            padding: 8px 12px; border-radius: 6px; width: 80px; font-family: 'JetBrains Mono', monospace;
        }
        .btn-gen { background: var(--accent-purple); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .btn-gen:hover { background: #7c3aed; }
        .gen-result { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: none; }
        .gen-badges { display: flex; gap: 8px; margin-bottom: 12px; }
        .gen-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
        .gen-diff-bar { height: 4px; background: var(--border); border-radius: 2px; margin: 12px 0; overflow: hidden; }
        .gen-diff-fill { height: 100%; transition: width 0.3s; }
        
        .dual-diagram {
            background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px;
            padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-bottom: 24px;
            color: var(--text-secondary);
            display: flex; justify-content: space-between; align-items: center;
        }
        .agent-box { border: 1px solid var(--border); padding: 8px; border-radius: 4px; background: rgba(0,0,0,0.2); width: 42%; }
        .agent-arrow { flex-grow: 1; text-align: center; color: var(--accent-green); position: relative; }
        .agent-arrow::after {
            content: '→'; position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
            animation: flowRight 1.5s infinite linear;
        }
        @keyframes flowRight { 0% { left: 20%; opacity: 0; } 50% { opacity: 1; } 100% { left: 80%; opacity: 0; } }
        .btn-green { background: var(--accent-green); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .btn-green:hover { background: #059669; }
        .session-info { margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--accent-green); display: none; word-break: break-all; }

        .feature-link { color: var(--accent-blue); font-size: 14px; font-weight: 500; text-decoration: none; margin-top: auto; display: inline-block; }
        .feature-link:hover { text-decoration: underline; }

        /* Live Metrics Bar */
        .metrics-bar-container { background: var(--bg-secondary); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 24px 0; }
        .metrics-grid { display: flex; justify-content: space-between; }
        .metric-item { text-align: center; flex: 1; border-right: 1px solid var(--border); }
        .metric-item:last-child { border-right: none; }
        .metric-val { font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; color: var(--accent-blue); }
        .metric-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
        @media (max-width: 640px) { .metrics-grid { flex-wrap: wrap; gap: 24px; } .metric-item { min-width: 40%; border: none; } }

        /* Leaderboard */
        .leaderboard-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { background: rgba(255,255,255,0.03); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); padding: 12px 24px; border-bottom: 1px solid var(--border); }
        td { padding: 16px 24px; border-bottom: 1px solid var(--border); font-size: 14px; color: var(--text-primary); }
        tr:last-child td { border-bottom: none; }
        .rank-1 { color: #fbbf24; font-weight: bold; }
        .rank-2 { color: #9ca3af; font-weight: bold; }
        .rank-3 { color: #cd7f32; font-weight: bold; }
        .lb-score { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
        .lb-status { font-size: 13px; }

        /* Quick Start */
        .tabs { display: flex; gap: 8px; margin-bottom: 16px; }
        .tab { background: transparent; border: none; color: var(--text-secondary); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;}
        .tab.active { background: var(--accent-blue); color: white; }
        .code-block { background: #020408; border: 1px solid var(--border); border-radius: 12px; padding: 24px; position: relative; display: none; overflow-x: auto; }
        .code-block.active { display: block; }
        .code-text { font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.8; color: var(--text-primary); white-space: pre; }
        .btn-copy { position: absolute; top: 12px; right: 12px; background: rgba(255,255,255,0.1); border: 1px solid var(--border); color: var(--text-secondary); padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }
        .btn-copy:hover { color: white; background: rgba(255,255,255,0.2); }
        
        .code-comment { color: var(--text-dim); }
        .code-str { color: var(--accent-green); }
        .code-cmd { color: var(--accent-blue); }
        .code-url { color: var(--accent-cyan); }
        .code-key { color: var(--accent-yellow); }

        /* Training Evidence */
        .training-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        @media (max-width: 900px) { .training-grid { grid-template-columns: 1fr; } }
        .train-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; }
        .train-title { font-size: 18px; font-weight: 600; margin-bottom: 24px; }
        .train-row { margin-bottom: 24px; }
        .train-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
        .train-badge { padding: 4px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 12px; }
        .train-desc { font-size: 14px; color: var(--text-secondary); line-height: 1.5; margin-left: 28px; }
        .train-vis { float: left; font-size: 18px; margin-top: 2px; }
        .train-table-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border); }
        .train-table-row:last-child { border-bottom: none; }
        .tt-key { font-size: 13px; color: var(--text-secondary); }
        .tt-val { font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); }
        
        /* Footer */
        footer { background: var(--bg-secondary); border-top: 1px solid var(--border); padding: 48px 0 32px; margin-top: 80px; }
        .footer-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 32px; }
        @media (max-width: 768px) { .footer-grid { grid-template-columns: 1fr; } }
        .f-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }
        .f-text { font-size: 13px; color: var(--text-dim); line-height: 1.6; }
        .f-links { display: flex; flex-direction: column; gap: 12px; }
        .f-link { font-size: 13px; color: var(--text-secondary); transition: color 0.2s; }
        .f-link:hover { color: var(--text-primary); }
        .f-social { display: flex; gap: 16px; margin-top: 16px; }
        .f-bottom { border-top: 1px solid var(--border); margin-top: 32px; padding-top: 24px; display: flex; justify-content: space-between; font-size: 12px; color: var(--text-dim); }
        @media (max-width: 640px) { .f-bottom { flex-direction: column; gap: 8px; text-align: center; } }
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
  -d <span class="code-str">'{<span class="code-key">"task_id"</span>: <span class="code-str">"easy"</span>, <span class="code-key">"seed"</span>: 42}'</span>

<span class="code-comment"># 2. Read logs (reward: +0.15)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{<span class="code-key">"action_type"</span>: <span class="code-str">"read_logs"</span>, <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}'</span>

<span class="code-comment"># 3. Diagnose (reward: +0.30)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{<span class="code-key">"action_type"</span>: <span class="code-str">"diagnose"</span>, <span class="code-key">"root_cause"</span>: <span class="code-str">"memory leak in payment-service"</span>}'</span>

<span class="code-comment"># 4. Fix it (reward: +0.40)</span>
<span class="code-cmd">curl</span> -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H <span class="code-str">"Content-Type: application/json"</span> \
  -d <span class="code-str">'{<span class="code-key">"action_type"</span>: <span class="code-str">"restart_service"</span>, <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}'</span>

<span class="code-comment"># Score: ~0.94 ✅</span></div>
            </div>
            
            <div id="code-python" class="code-block">
                <button class="btn-copy" onclick="copyCode('code-py-text', this)">Copy</button>
                <div class="code-text" id="code-py-text"><span class="code-cmd">import</span> requests

BASE = <span class="code-str">"https://arijit-07-devops-incident-response.hf.space"</span>

<span class="code-comment"># Start episode</span>
obs = requests.post(<span class="code-url">f"{BASE}/reset"</span>, 
    json={<span class="code-key">"task_id"</span>: <span class="code-str">"easy"</span>, <span class="code-key">"seed"</span>: 42}).json()

<span class="code-comment"># Take action</span>
result = requests.post(<span class="code-url">f"{BASE}/step"</span>,
    json={<span class="code-key">"action_type"</span>: <span class="code-str">"read_logs"</span>,
          <span class="code-key">"service"</span>: <span class="code-str">"payment-service"</span>}).json()

print(<span class="code-url">f"Reward: {result['reward']}"</span>)  <span class="code-comment"># 0.15</span></div>
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

        function resize() {
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
        }
        window.addEventListener('resize', resize);
        resize();

        for(let i=0; i<60; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.5,
                vy: (Math.random() - 0.5) * 0.5
            });
        }

        function drawParticles() {
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.05)';
            
            for(let i=0; i<particles.length; i++) {
                let p = particles[i];
                p.x += p.vx; p.y += p.vy;
                
                if(p.x < 0 || p.x > width) p.vx *= -1;
                if(p.y < 0 || p.y > height) p.vy *= -1;
                
                ctx.beginPath();
                ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
                ctx.fill();
                
                for(let j=i+1; j<particles.length; j++) {
                    let p2 = particles[j];
                    let dx = p.x - p2.x, dy = p.y - p2.y;
                    let dist = Math.sqrt(dx*dx + dy*dy);
                    if(dist < 150) {
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.stroke();
                    }
                }
            }
            requestAnimationFrame(drawParticles);
        }
        drawParticles();

        // 2. Intersection Observer for Fade-in
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if(entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, { threshold: 0.1 });
        document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

        // 3. Status Check
        fetch('/health')
            .then(r => r.json())
            .then(data => {
                if(data.status === 'ok') {
                    document.getElementById('nav-status-text').innerText = 'LIVE';
                }
            }).catch(e => console.error(e));

        // 4. Load Tasks
        const taskConfig = {
            'easy': {icon: '💻', color: '#10b981', badge: 'EASY'},
            'medium': {icon: '⚡', color: '#f59e0b', badge: 'MEDIUM'},
            'hard': {icon: '🔥', color: '#ef4444', badge: 'HARD'},
            'bonus': {icon: '💥', color: '#8b5cf6', badge: 'EXPERT'},
            'security': {icon: '🛡️', color: '#06b6d4', badge: 'SECURITY'},
            'database': {icon: '🗄️', color: '#f97316', badge: 'DATABASE'},
            'failover': {icon: '🌐', color: '#6366f1', badge: 'FAILOVER'},
            'generated': {icon: '✨', color: '#ec4899', badge: 'DYNAMIC'}
        };
        
        fetch('/tasks')
            .then(r => r.json())
            .then(data => {
                const grid = document.getElementById('task-grid');
                grid.innerHTML = '';
                data.tasks.forEach(t => {
                    const cfg = taskConfig[t.id] || taskConfig['easy'];
                    grid.innerHTML += `
                        <div class="task-card" style="--card-color: ${cfg.color}; --card-bg: ${cfg.color}20;">
                            <div class="task-header">
                                <div class="task-icon">${cfg.icon}</div>
                                <div class="task-badge">${cfg.badge}</div>
                            </div>
                            <div class="task-name">${t.name}</div>
                            <div class="task-desc">${t.description}</div>
                            <div class="task-footer">
                                <div class="task-steps">Max steps: ${t.max_steps}</div>
                                <div class="task-status">Ready</div>
                            </div>
                        </div>
                    `;
                });
            }).catch(e => console.error(e));

        // 5. Curriculum
        fetch('/curriculum/status')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('curriculum-container');
                if(data.total_episodes_recorded === 0) {
                    container.innerHTML = '<div style="text-align: center; color: var(--text-dim); font-size: 13px;">No episodes recorded yet</div>';
                    return;
                }
                container.innerHTML = '';
                const tasks = data.tasks || {};
                Object.keys(tasks).slice(0, 4).forEach(k => {
                    let avg = tasks[k].rolling_avg;
                    let w = Math.max(5, avg * 100);
                    let color = avg < 0.3 ? 'var(--accent-red)' : (avg < 0.6 ? 'var(--accent-yellow)' : 'var(--accent-green)');
                    let blocks = Math.round(w / 10);
                    let fillStr = '█'.repeat(blocks);
                    let trackStr = '░'.repeat(10 - blocks);
                    container.innerHTML += `
                        <div class="c-bar-row">
                            <div class="c-bar-name">${k}</div>
                            <div class="c-bar-track" style="color: ${color}"><span class="c-bar-fill">${fillStr}</span><span style="opacity:0.3">${trackStr}</span></div>
                            <div class="c-bar-score">${avg.toFixed(2)}</div>
                        </div>
                    `;
                });
            }).catch(e => {
                document.getElementById('curriculum-container').innerHTML = '<div style="text-align: center; color: var(--text-dim); font-size: 13px;">--</div>';
                console.error(e);
            });

        // 6. Generator
        window.generateIncident = function() {
            const seed = document.getElementById('gen-seed').value || 42;
            fetch(`/generate/preview?seed=${seed}`)
                .then(r => r.json())
                .then(data => {
                    const cMap = {oom: '#ef4444', cascade: '#f59e0b', corruption: '#8b5cf6', security: '#06b6d4', database: '#f97316', network_partition: '#6366f1'};
                    const sMap = {sev1: '#ef4444', sev2: '#f59e0b', sev3: '#10b981'};
                    const fColor = cMap[data.failure_mode] || '#3b82f6';
                    
                    document.getElementById('gen-badges').innerHTML = `
                        <span class="gen-badge" style="background:${fColor}20; color:${fColor}">${data.failure_mode}</span>
                        <span class="gen-badge" style="background:${sMap[data.severity] || '#3b82f6'}20; color:${sMap[data.severity] || '#3b82f6'}">${data.severity}</span>
                        <span class="gen-badge" style="background:rgba(255,255,255,0.1); color:var(--text-secondary)">${data.incident_id}</span>
                    `;
                    document.getElementById('gen-affected').innerText = `Affected: ${data.affected_service}`;
                    document.getElementById('gen-desc').innerText = data.description;
                    
                    let dColor = data.difficulty_score < 0.4 ? '#10b981' : (data.difficulty_score < 0.7 ? '#f59e0b' : '#ef4444');
                    document.getElementById('gen-diff-fill').style.width = `${data.difficulty_score * 100}%`;
                    document.getElementById('gen-diff-fill').style.background = dColor;
                    
                    document.getElementById('gen-result').style.display = 'block';
                }).catch(e => console.error(e));
        };

        // 7. Dual Agent
        window.startDualSession = function() {
            fetch('/multi-agent/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: "easy", seed: 42})
            }).then(r => r.json())
              .then(data => {
                  const info = document.getElementById('dual-session-info');
                  info.innerHTML = `Session: ${data.session_id}<br><br>Agent A (POST): /multi-agent/step/a/${data.session_id}<br>Agent B (POST): /multi-agent/step/b/${data.session_id}`;
                  info.style.display = 'block';
              }).catch(e => console.error(e));
        };

        // 8. Live Metrics
        function loadMetrics() {
            fetch('/metrics')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('m-episodes').innerText = data.total_episodes || 0;
                    document.getElementById('m-avg').innerText = (data.overall_avg_score || 0).toFixed(3);
                    
                    // calculate overall resolution rate
                    if (data.by_task) {
                        let totalRes = 0, totalCount = 0;
                        let bestScore = 0;
                        Object.values(data.by_task).forEach(t => {
                            totalRes += t.resolution_rate * t.count;
                            totalCount += t.count;
                            if (t.max_score > bestScore) bestScore = t.max_score;
                        });
                        let resRate = totalCount > 0 ? (totalRes / totalCount) * 100 : 0;
                        document.getElementById('m-res').innerText = resRate.toFixed(1) + '%';
                        document.getElementById('m-best').innerText = bestScore.toFixed(3);
                    }
                }).catch(e => console.error(e));
        }
        loadMetrics();
        setInterval(loadMetrics, 30000);

        // 9. Leaderboard
        fetch('/leaderboard')
            .then(r => r.json())
            .then(data => {
                const tbody = document.getElementById('lb-body');
                if(!data.leaderboard || data.leaderboard.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No episodes yet. Try POST /reset to start your first episode.</td></tr>';
                    return;
                }
                tbody.innerHTML = '';
                data.leaderboard.forEach(row => {
                    let rClass = row.rank <= 3 ? `rank-${row.rank}` : '';
                    let sColor = row.score >= 0.8 ? '#10b981' : (row.score >= 0.5 ? '#f59e0b' : '#ef4444');
                    let statusHtml = row.score > 0.5 ? '<span style="color:#10b981">✅ Resolved</span>' : '<span style="color:#ef4444">❌ Failed</span>'; // Simple heuristic if resolution missing
                    
                    tbody.innerHTML += `
                        <tr>
                            <td class="${rClass}">#${row.rank}</td>
                            <td>${row.task_id}</td>
                            <td class="lb-score" style="color: ${sColor}">${row.score.toFixed(4)}</td>
                            <td>${row.steps}</td>
                            <td class="lb-status">${statusHtml}</td>
                        </tr>
                    `;
                });
            }).catch(e => console.error(e));

        // 10. Tabs
        window.switchTab = function(type) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.code-block').forEach(c => c.classList.remove('active'));
            if(type === 'curl') {
                document.querySelectorAll('.tab')[0].classList.add('active');
                document.getElementById('code-curl').classList.add('active');
            } else {
                document.querySelectorAll('.tab')[1].classList.add('active');
                document.getElementById('code-python').classList.add('active');
            }
        };

        window.copyCode = function(id, btn) {
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text).then(() => {
                let old = btn.innerText;
                btn.innerText = 'Copied ✓';
                setTimeout(() => btn.innerText = old, 2000);
            });
        };
    </script>
</body>
</html>
"""

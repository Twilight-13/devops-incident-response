import sys

html_content = r'''
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

  let ws = null;
  let currentTask = 'easy';
  let currentSeed = 42;
  let stepCount = 0;
  let totalScore = 0;
  let isRunning = false;
  let rewardHistory = [];
  
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

  function updateStepCounter() {{
    document.getElementById('top-step').textContent = `${{stepCount.toString().padStart(2,'0')}} / 15`;
    document.getElementById('stat-step').textContent = `STEP ${{stepCount}}/15`;
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

  function startEpisode(task, seed) {{
    stepCount = 0;
    totalScore = 0;
    rewardHistory = [];
    isRunning = true;
    currentTask = task;
    currentSeed = seed;
    
    document.getElementById('stat-task').textContent = `TASK: ${{task.toUpperCase()}}`;
    document.getElementById('stat-seed').textContent = `SEED: ${{seed}}`;
    updateStepCounter();
    updateScoreDisplay();
    updateSparkline();
    document.getElementById('alerts-list').innerHTML = '<div class="no-alerts mono">◎ ALL SYSTEMS NOMINAL</div>';
    document.getElementById('alert-count').textContent = '0';
    document.getElementById('alert-count').style.background = 'var(--surface2)';
    
    addLog('EPISODE_START', task, seed);
    if(ws && ws.readyState === WebSocket.OPEN) {{
      ws.send(JSON.stringify({{command: "reset", task_id: task, seed: seed}}));
    }}
  }}

  function deployIncident() {{
    const task = document.getElementById('task-select').value;
    const seed = parseInt(document.getElementById('seed-input').value) || 42;
    if(ws && ws.readyState === WebSocket.OPEN) {{
      startEpisode(task, seed);
    }} else {{
      connectWS();
    }}
  }}

  function connectWS() {{
    if(ws) ws.close();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${{protocol}}//${{window.location.host}}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {{
      document.getElementById('live-dot').className = 'status-dot dot-green';
      document.getElementById('live-text').textContent = 'LIVE';
      document.getElementById('live-text').style.color = 'var(--red)';
      document.getElementById('btm-dot').className = 'status-dot dot-green';
      document.getElementById('btm-text').textContent = '◉ WS CONNECTED';
      document.getElementById('btm-text').style.color = 'var(--green)';
      addLog('SYSTEM', 'WebSocket connected');
      startEpisode(currentTask, currentSeed);
    }};
    
    ws.onclose = () => {{
      document.getElementById('live-dot').className = 'status-dot dot-grey';
      document.getElementById('live-text').textContent = 'OFFLINE';
      document.getElementById('live-text').style.color = 'var(--text)';
      document.getElementById('btm-dot').className = 'status-dot dot-grey';
      document.getElementById('btm-text').textContent = '○ WS DISCONNECTED';
      document.getElementById('btm-text').style.color = 'var(--text-dim)';
      addLog('SYSTEM', 'Disconnected — reconnecting in 3s...');
      setTimeout(connectWS, 3000);
    }};
    
    ws.onmessage = (event) => {{
      let data;
      try {{ data = JSON.parse(event.data); }} catch(e) {{ return; }}
      
      if(data.services) {{
        const svcs = Object.entries(data.services).map(([name, s]) => ({{name, ...s}}));
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
      
      if(data.active_alerts) {{
        const alist = document.getElementById('alerts-list');
        alist.innerHTML = '';
        document.getElementById('alert-count').textContent = data.active_alerts.length;
        document.getElementById('alert-count').style.background = data.active_alerts.length > 0 ? 'var(--red)' : 'var(--surface2)';
        
        if(data.active_alerts.length === 0) {{
          alist.innerHTML = '<div class="no-alerts mono">◎ ALL SYSTEMS NOMINAL</div>';
        }} else {{
          let critFound = false;
          data.active_alerts.slice(0, 5).forEach(a => {{
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
          if(data.active_alerts.length > 5) {{
            alist.innerHTML += `<div class="mono" style="font-size:9px; color:var(--text-dim); text-align:center">+${{data.active_alerts.length - 5}} more</div>`;
          }}
          if(critFound) {{
            const lp = document.getElementById('left-panel');
            lp.classList.remove('flash-critical');
            void lp.offsetWidth;
            lp.classList.add('flash-critical');
          }}
        }}
      }}
      
      if(data.action !== undefined && isRunning) {{
        stepCount++;
        updateStepCounter();
        
        let act = data.action;
        if(typeof act === 'string') try{{ act = JSON.parse(act) }}catch(e){{}}
        
        if(act.action_type === 'diagnose') addLog('DIAGNOSE', act.root_cause);
        else if(act.action_type === 'restart_service' || act.action_type === 'rollback_service' || act.action_type === 'block_ip') 
          addLog('FIX', act.action_type, act.service || act.ip);
        else addLog('ACTION', act);
        
        if(data.evidence) addLog('EVIDENCE', data.evidence);
        if(data.reward !== undefined) {{
          totalScore += data.reward;
          rewardHistory.push(data.reward);
          addLog('REWARD', data.reward);
          updateScoreDisplay();
          updateSparkline();
        }}
        
        if(data.done) {{
          isRunning = false;
          addLog('EPISODE_END', totalScore, stepCount);
          updateScoreDisplay();
          setTimeout(() => {{
            currentSeed = Math.floor(Math.random() * 99999);
            document.getElementById('seed-input').value = currentSeed;
            startEpisode(currentTask, currentSeed);
          }}, 4000);
        }}
      }}
    }};
  }}

  window.onload = connectWS;
</script>
</body>
</html>
"""
    return HTMLResponse(html)
'''

with open("server/app.py", "r", encoding="utf-8") as f:
    content = f.read()

# find @app.get("/", response_class=HTMLResponse)
target = '@app.get("/", response_class=HTMLResponse)'
if target in content:
    new_content = content.replace(target, html_content + "\n\n" + target)
    with open("server/app.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("SUCCESS")
else:
    print("NOT FOUND")

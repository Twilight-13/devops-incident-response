#!/usr/bin/env python3
"""
demo_llm.py — ARIA DevOps Incident Response: live demo with LLM agent
======================================================================
Runs a full episode against the live HuggingFace Space using either
a heuristic agent (no GPU needed) or the real fine-tuned Llama model.

Usage:
    pip install rich requests
    python demo_llm.py                   # prompts for mode at startup
    HF_TOKEN=hf_... python demo_llm.py  # with model hub access
"""

import os
import sys
import json
import re
import time
import requests

# Load .env from project root before anything else reads os.environ
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

# Force UTF-8 on Windows (emoji in Rich panels would otherwise crash cp1252)
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.markup import escape
from rich import box

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL     = "https://arijit-07-devops-incident-response.hf.space"
DEFAULT_TASK = "easy"
DEFAULT_SEED = 42

MODEL_REPO = "Arijit-07/aria-devops-llama8b"

HF_TOKEN = os.environ.get('HF_TOKEN', '')

# force_terminal + force_interactive ensures Rich uses full ANSI rendering
# on Windows terminals that would otherwise fall back to legacy mode
console = Console(
    force_terminal=True,
    force_interactive=True,
    legacy_windows=False,
)

# ─── Model loading ────────────────────────────────────────────────────────────

def _get_model_device(model):
    try:
        return next(model.parameters()).device
    except Exception:
        import torch
        return torch.device("cpu")


def load_model():
    import torch
    if torch.cuda.is_available():
        console.print(f"[green]✓ CUDA available: {torch.cuda.get_device_name(0)}[/green]")
    else:
        console.print("[yellow]⚠ No CUDA GPU detected. LLM mode requires a GPU.[/yellow]")
        console.print("[yellow]  Running on CPU will be very slow (5-10 min per step).[/yellow]")
        console.print("[yellow]  Consider using heuristic mode (n) instead.[/yellow]")

    import os
    hf_token = os.environ.get('HF_TOKEN', None)
    if hf_token:
        from huggingface_hub import login
        login(token=hf_token, add_to_git_credential=False)
        console.print("[green]✓ HF authenticated[/green]")

    console.print("[cyan]Loading ARIA fine-tuned model...[/cyan]")

    try:
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_REPO,
            max_seq_length=2048,
            load_in_4bit=True,
            token=hf_token,
        )
        FastLanguageModel.for_inference(model)
        console.print(f"[green]✓ Model loaded via Unsloth: {MODEL_REPO}[/green]")
    except ModuleNotFoundError:
        console.print("[yellow]! Unsloth not found. Falling back to transformers + PEFT...[/yellow]")
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        BASE_MODEL = "unsloth/Meta-Llama-3.1-8B-Instruct"
        ADAPTER_REPO = "Arijit-07/aria-devops-llama8b"

        console.print("[cyan]Loading base model (4-bit)...[/cyan]")

        try:
            from transformers import BitsAndBytesConfig
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
            base = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )
            console.print("[green]✓ Loaded in 4-bit[/green]")
        except Exception:
            base = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            console.print("[yellow]✓ Loaded in float16[/yellow]")

        console.print("[cyan]Loading LoRA adapter...[/cyan]")
        model = PeftModel.from_pretrained(base, ADAPTER_REPO)
        model.eval()

        tokenizer = AutoTokenizer.from_pretrained(ADAPTER_REPO)
        console.print(f"[green]✓ Model ready: {ADAPTER_REPO}[/green]")

    device = _get_model_device(model)
    console.print(f"[green]✓ Model device: {device}[/green]")
    if str(device) == "cpu":
        console.print("[yellow]⚠ Model is on CPU. Install PyTorch with CUDA support for GPU inference:[/yellow]")
        console.print("[yellow]  pip install torch --index-url https://download.pytorch.org/whl/cu121[/yellow]")

    return model, tokenizer

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert DevOps engineer responding to a production incident.
Respond with ONLY a valid JSON action object. No explanation.

Available actions:
{"action_type": "read_logs", "service": "<name>"}
{"action_type": "read_metrics", "service": "<name>"}
{"action_type": "search_logs", "service": "<name>", "query": "<term>"}
{"action_type": "diagnose", "root_cause": "<diagnosis>"}
{"action_type": "restart_service", "service": "<name>"}
{"action_type": "rollback", "service": "<name>", "version": "previous"}
{"action_type": "alert_oncall", "reason": "<reason>"}
{"action_type": "block_ip_range", "ip_range": "<cidr>"}
{"action_type": "create_index", "table": "<t>", "column": "<c>"}
{"action_type": "failover", "service": "<name>", "target_region": "us-west-2"}
{"action_type": "noop"}

Rule: ALWAYS read_logs before diagnose or any fix action."""

# ─── Observation → LLM prompt ─────────────────────────────────────────────────

def obs_to_prompt(obs, task_id):
    lines = [
        f"INCIDENT | Task: {task_id.upper()} | "
        f"Step {obs.get('step',0)}/{obs.get('max_steps',15)}",
        ""
    ]
    for a in sorted(obs.get('active_alerts', []),
                    key=lambda x: x.get('severity',''), reverse=True):
        lines.append(
            f"ALERT [{a.get('severity','').upper()}] "
            f"{a.get('service','')}: {a.get('message','')}"
        )
    lines.append("")
    for s in sorted(obs.get('services', []),
                    key=lambda x: x.get('error_rate', 0), reverse=True):
        lines.append(
            f"SERVICE {s.get('name',''):25s} | "
            f"{s.get('status',''):10s} | "
            f"err={s.get('error_rate',0):.3f} | "
            f"mem={s.get('memory',0):.1f}%"
        )
    evidence = obs.get('evidence_log', [])
    if evidence:
        lines.append("\nEVIDENCE:")
        for e in evidence[-4:]:
            lines.append(
                f"  [{e.get('action_type','').upper()}] "
                f"{e.get('content','')[:120]}"
            )
    return "\n".join(lines)

# ─── Action parsing ───────────────────────────────────────────────────────────

def parse_action(text):
    text = text.strip()
    for pattern in [
        r'```json\s*({.*?})\s*```',
        r'```\s*({.*?})\s*```',
        r'({\s*"action_type"[^}]+})',
    ]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                continue
    try:
        return json.loads(text)
    except Exception:
        return {"action_type": "noop"}

# ─── Heuristic agent ──────────────────────────────────────────────────────────

def get_next_action(obs, step_history, task_id="easy"):
    """
    Rule-based heuristic — no GPU required.

    BUG-FIX: use step_history (local, authoritative) to track which action
    types have already been taken, instead of evidence_log source strings
    whose format is server-internal and does NOT include the word 'diagnose'.
    """
    alerts  = obs.get('active_alerts', [])

    # Track state from our own history — reliable regardless of server format
    action_types_taken = {a.get('action_type') for a in step_history}
    read_done  = {a.get('service') for a in step_history
                  if a.get('action_type') == 'read_logs'}
    diagnosed  = 'diagnose' in action_types_taken
    fixed      = bool(action_types_taken & {
        'restart_service', 'rollback', 'block_ip_range',
        'create_index', 'failover', 'alert_oncall',
    })

    # Find the root-cause service: prefer CRITICAL alert, fallback to max error_rate
    failing_service = next(
        (a.get('service') for a in obs.get('active_alerts', [])
         if a.get('severity') == 'critical'),
        max(
            obs.get('services', [{'name': 'payment-service', 'error_rate': 0}]),
            key=lambda x: x.get('error_rate', 0),
        ).get('name', 'payment-service')
    )

    # Step 1 — gather evidence
    if failing_service not in read_done:
        return {"action_type": "read_logs", "service": failing_service}

    # Step 2 — diagnose
    if not diagnosed:
        crit_msg = next(
            (a.get('message', 'unknown') for a in alerts
             if a.get('severity') == 'critical'),
            alerts[0].get('message', 'unknown') if alerts else 'unknown',
        )
        return {"action_type": "diagnose",
                "root_cause": f"{crit_msg} in {failing_service}"}

    # Step 3 — apply fix (task-specific)
    if not fixed:
        if task_id == "medium":
            return {"action_type": "rollback",
                    "service": "inventory-service", "version": "previous"}

        if task_id == "hard":
            return {"action_type": "rollback",
                    "service": "data-pipeline", "version": "previous"}

        if task_id == "bonus":
            ml_fixed = any(
                a.get('action_type') == 'restart_service' and
                a.get('service') == 'ml-inference-service'
                for a in step_history
            )
            if not ml_fixed:
                return {"action_type": "restart_service",
                        "service": "ml-inference-service"}
            return {"action_type": "alert_oncall",
                    "reason": "disk full on log-aggregator"}

        # security / generic alert checks
        for a in alerts:
            msg = a.get('message', '').lower()
            if any(kw in msg for kw in ('ddos', 'botnet', '185.220', 'ip range')):
                return {"action_type": "block_ip_range",
                        "ip_range": "185.220.0.0/16"}
            if any(kw in msg for kw in ('index', 'seq_scan', 'slow query', 'full table')):
                return {"action_type": "create_index",
                        "table": "orders", "column": "user_segment"}

        # default: restart the failing service (easy / failover fallback)
        return {"action_type": "restart_service", "service": failing_service}

    return {"action_type": "noop"}

# ─── LLM agent ────────────────────────────────────────────────────────────────

def get_next_action_llm(model, tokenizer, obs, task_id):
    import torch
    device = _get_model_device(model)
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": obs_to_prompt(obs, task_id)}
    ]
    ids = tokenizer.apply_chat_template(
        msgs, tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt"
    ).to(device)
    with torch.no_grad():
        out = model.generate(
            ids, max_new_tokens=80,
            temperature=0.7, do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True)
    return parse_action(text), text

# ─── REST API helpers ─────────────────────────────────────────────────────────

def api_reset(task_id, seed):
    r = requests.post(
        f"{BASE_URL}/reset",
        json={"task_id": task_id, "seed": seed},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

def api_step(action):
    r = requests.post(f"{BASE_URL}/step", json=action, timeout=15)
    r.raise_for_status()
    return r.json()

def api_leaderboard():
    try:
        r = requests.get(f"{BASE_URL}/leaderboard", timeout=5)
        if not r.ok:
            return []
        data = r.json()
        if isinstance(data, list):
            return data
        for key in ('leaderboard', 'entries', 'scores', 'data'):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    except Exception:
        return []

# ─── Rich UI helpers ──────────────────────────────────────────────────────────

STATUS_COLOR = {
    "healthy":  "green",
    "degraded": "yellow",
    "down":     "red bold",
    "unknown":  "dim",
}
SEVERITY_COLOR = {
    "critical": "red bold",
    "warning":  "yellow bold",
    "info":     "cyan",
}
ACTION_COLOR = {
    "restart_service": "bold red",
    "rollback":        "bold orange3",
    "diagnose":        "bold yellow",
    "read_logs":       "cyan",
    "read_metrics":    "cyan",
    "search_logs":     "cyan",
    "alert_oncall":    "magenta",
    "block_ip_range":  "bold red",
    "create_index":    "blue",
    "failover":        "bold red",
    "noop":            "dim",
}


def make_header(task_id, step, max_steps, score, use_llm):
    if use_llm:
        agent_label = Text("🧠 LLM: Llama-3.1-8B + LoRA adapter (97MB)", style="bold green")
    else:
        agent_label = Text("🔧 HEURISTIC AGENT", style="bold yellow")
    t = Text()
    t.append("🚨 ARIA ", style="bold red")
    t.append("DevOps Incident Response  ", style="bold white")
    t.append(f"│  Task: {task_id.upper()}  ", style="bold cyan")
    t.append(f"│  Step: {step}/{max_steps}  ", style="white")
    t.append(f"│  Score: {score:+.3f}  ", style="bold magenta")
    t.append("│  ")
    t.append_text(agent_label)
    return Panel(t, style="on dark_blue", box=box.HORIZONTALS)


def make_services_panel(services, sla_status):
    tbl = Table(box=box.SIMPLE_HEAD, expand=True)
    tbl.add_column("Service",  style="bold", min_width=20)
    tbl.add_column("Status",   min_width=9)
    tbl.add_column("CPU",      justify="right", min_width=4)
    tbl.add_column("MEM",      justify="right", min_width=4)
    tbl.add_column("ERR/s",    justify="right", min_width=6)
    tbl.add_column("SLA",      min_width=7)
    for svc in sorted(services, key=lambda s: s.get('error_rate', 0), reverse=True):
        name   = svc.get('name', '?')
        status = svc.get('status', 'unknown')
        sla    = sla_status.get(name, 'ok')
        tbl.add_row(
            name,
            Text(status.upper(), style=STATUS_COLOR.get(status, 'white')),
            f"{svc.get('cpu_percent', 0):.0f}%",
            f"{svc.get('memory_percent', 0):.0f}%",
            f"{svc.get('error_rate', 0):.3f}",
            Text(sla, style=("red bold" if sla == "breached"
                             else ("yellow" if sla == "warning" else "green"))),
        )
    return Panel(tbl, title="📡 Service Status", border_style="blue")


def make_alerts_panel(alerts):
    if not alerts:
        return Panel("[dim]No active alerts[/dim]",
                     title="🔔 Alerts", border_style="green")
    lines = []
    for a in sorted(alerts, key=lambda x: x.get('severity', ''), reverse=True):
        sev   = a.get('severity', 'info')
        color = SEVERITY_COLOR.get(sev, 'white')
        msg   = escape(a.get('message', '')[:70])
        svc   = escape(a.get('service', ''))
        lines.append(
            f"[{color}][{sev.upper():8s}][/{color}] [bold]{svc}[/bold]: {msg}"
        )
    return Panel("\n".join(lines),
                 title=f"🔔 Alerts ({len(alerts)})", border_style="yellow")


def make_evidence_panel(evidence):
    if not evidence:
        return Panel("[dim]No evidence gathered yet[/dim]",
                     title="📋 Evidence Log", border_style="dim")
    lines = []
    for e in evidence[-5:]:
        src     = escape(e.get('source', e.get('action_type', '?')).upper())
        summary = escape((e.get('summary') or e.get('content') or '')[:80])
        lines.append(f"[cyan]\\[{src}][/cyan] {summary}")
    return Panel("\n".join(lines),
                 title=f"📋 Evidence ({len(evidence)} entries)",
                 border_style="cyan")


def make_reasoning_panel(action, raw_llm_text, use_llm, reward=None, error=None):
    lines = []

    if use_llm and raw_llm_text:
        lines.append("[dim cyan]🧠 Model output:[/dim cyan]")
        lines.append(f"[dim italic]{escape(raw_llm_text[:240])}[/dim italic]")
        lines.append("")

    lines.append("[bold]📋 Parsed action:[/bold]")
    at    = action.get('action_type', 'noop')
    color = ACTION_COLOR.get(at, 'white')
    lines.append(f"  [{color}]{at.upper()}[/{color}]")

    for field in ('service', 'root_cause', 'ip_range', 'table', 'column',
                  'target_region', 'version', 'reason'):
        val = action.get(field)
        if val:
            label = field.replace('_', ' ')
            lines.append(f"  [dim]{label}:[/dim] {escape(str(val)[:60])}")

    if reward is not None:
        r_color = "green" if reward > 0 else ("red" if reward < 0 else "dim")
        lines.append(f"\n  [{r_color}]Reward: {reward:+.3f}[/{r_color}]")

    if error:
        lines.append(f"\n  [red]⚠ {escape(str(error)[:80])}[/red]")

    return Panel("\n".join(lines), title="🤖 Agent Reasoning", border_style="blue")


def make_score_panel(step, max_steps, total_reward, done):
    bar_len  = 20
    filled   = int(bar_len * step / max(max_steps, 1))
    bar      = "█" * filled + "░" * (bar_len - filled)
    status   = "[bold green]RESOLVED ✓[/bold green]" if done else "[dim]in progress…[/dim]"
    return Panel(
        f"[bold magenta]{total_reward:+.3f}[/bold magenta] total reward\n"
        f"[{bar}] {step}/{max_steps}\n"
        f"{status}",
        title="📊 Score",
        border_style="magenta",
    )


def make_leaderboard_panel(entries):
    if not entries:
        return Panel("[dim]—[/dim]", title="🏆 Top Scores", border_style="dim")
    lines = []
    for i, e in enumerate(entries[:5], 1):
        tid   = escape(str(e.get('task_id', '?'))[:8])
        score = e.get('score', 0)
        lines.append(f"[dim]{i}.[/dim] {tid:<8} [bold]{score:.3f}[/bold]")
    return Panel("\n".join(lines), title="🏆 Top Scores", border_style="dim")


def make_footer(task_id, seed, use_llm):
    mode = "[green]LLM[/green]" if use_llm else "[yellow]Heuristic[/yellow]"
    return Panel(
        f"Task: [cyan]{task_id}[/cyan]  │  Seed: [cyan]{seed}[/cyan]  │  "
        f"Agent: {mode}  │  Space: [dim]{BASE_URL}[/dim]",
        box=box.HORIZONTALS,
    )

# ─── Layout factory ───────────────────────────────────────────────────────────

def build_layout():
    """Create the persistent layout skeleton once; update regions each step."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left",  ratio=1),
        Layout(name="right", ratio=1),
    )
    layout["left"].split_column(
        Layout(name="services", ratio=2),
        Layout(name="alerts",   ratio=1),
        Layout(name="evidence", ratio=1),
    )
    layout["right"].split_column(
        Layout(name="reasoning",   ratio=3),
        Layout(name="score",       ratio=1),
        Layout(name="leaderboard", ratio=1),
    )
    return layout


def update_layout(layout, task_id, seed, step, max_steps, score, use_llm,
                  services, sla_status, alerts, evidence,
                  action, raw, reward, error, done, leaderboard):
    layout["header"].update(make_header(task_id, step, max_steps, score, use_llm))
    layout["services"].update(make_services_panel(services, sla_status))
    layout["alerts"].update(make_alerts_panel(alerts))
    layout["evidence"].update(make_evidence_panel(evidence))
    layout["reasoning"].update(make_reasoning_panel(action, raw, use_llm, reward, error))
    layout["score"].update(make_score_panel(step, max_steps, score, done))
    layout["leaderboard"].update(make_leaderboard_panel(leaderboard))
    layout["footer"].update(make_footer(task_id, seed, use_llm))

# ─── Episode loop ─────────────────────────────────────────────────────────────

def run_demo(task_id=DEFAULT_TASK, seed=DEFAULT_SEED,
             use_llm=False, model=None, tokenizer=None):
    console.print(
        f"\n[bold cyan]▶ Episode starting:[/bold cyan] "
        f"task=[cyan]{task_id}[/cyan]  seed=[cyan]{seed}[/cyan]"
    )

    obs          = api_reset(task_id, seed)
    leaderboard  = api_leaderboard()
    total_reward = 0.0
    step_history = []
    last_action  = {"action_type": "noop"}
    last_raw     = ""
    last_reward  = None
    last_error   = None
    done         = False
    step         = obs.get('step', 0)
    max_steps    = obs.get('max_steps', 15)

    layout = build_layout()

    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        while not done and step < max_steps:
            services   = obs.get('services', [])
            alerts     = obs.get('active_alerts', [])
            evidence   = obs.get('evidence_log', [])
            sla_status = obs.get('sla_status', {})

            update_layout(
                layout, task_id, seed, step, max_steps, total_reward, use_llm,
                services, sla_status, alerts, evidence,
                last_action, last_raw, last_reward, last_error, done, leaderboard,
            )
            live.refresh()

            # Choose agent and get next action
            if use_llm:
                last_action, last_raw = get_next_action_llm(
                    model, tokenizer, obs, task_id)
            else:
                last_action = get_next_action(obs, step_history, task_id)
                last_raw    = ""

            step_history.append(last_action)

            # Send to environment
            try:
                result       = api_step(last_action)
                obs          = result.get('observation', obs)
                last_reward  = result.get('reward', 0.0)
                total_reward += last_reward or 0.0
                done         = result.get('done', False)
                last_error   = obs.get('last_action_error') or None
                step         = obs.get('step', step + 1)
            except Exception as exc:
                last_error = str(exc)
                step += 1

            time.sleep(0.8)

        # Hold final frame
        update_layout(
            layout, task_id, seed, step, max_steps, total_reward, use_llm,
            obs.get('services', []), obs.get('sla_status', {}),
            obs.get('active_alerts', []), obs.get('evidence_log', []),
            last_action, last_raw, last_reward, last_error, done, leaderboard,
        )
        live.refresh()
        time.sleep(2.0)

    # Summary card
    console.print()
    resolved     = done and (last_reward or 0) > 0.2
    resolved_txt = ("[bold green]✓ RESOLVED[/bold green]"
                    if resolved else "[bold red]✗ NOT RESOLVED[/bold red]")
    agent_txt    = ("[green]LLM (fine-tuned Llama)[/green]"
                    if use_llm else "[yellow]Heuristic[/yellow]")
    console.print(Panel(
        f"{resolved_txt}\n"
        f"Task: [cyan]{task_id}[/cyan]  │  "
        f"Steps: [cyan]{step}[/cyan]  │  "
        f"Total reward: [bold magenta]{total_reward:+.3f}[/bold magenta]\n"
        f"Agent: {agent_txt}",
        title="Episode Complete",
        border_style="green" if resolved else "red",
    ))

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold red]🚨 ARIA[/bold red] — Adaptive Reward & Incident Architecture\n"
        "[dim]DevOps Incident Response · OpenEnv Live Demo[/dim]\n"
        f"[dim]Space: {BASE_URL}[/dim]",
        border_style="red",
    ))

    # Verify Space is reachable
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        console.print(f"[green]✓ Space online:[/green] {r.json()}")
    except Exception as e:
        console.print(f"[red]✗ Cannot reach Space: {e}[/red]")
        sys.exit(1)

    # Mode selector
    console.print("\nRun with real LLM? \[y/n]: ", end="")
    choice = input().strip().lower()
    if choice == 'y':
        model, tokenizer = load_model()
        use_llm = True
    else:
        use_llm = False
        model, tokenizer = None, None

    import random
    TASK_ROTATION = [
        'easy', 'medium', 'hard', 'security',
        'database', 'failover', 'bonus', 'generated'
    ]
    episode_count = 0

    while True:
        task_id = TASK_ROTATION[episode_count % len(TASK_ROTATION)]
        seed = random.randint(0, 9999)
        episode_count += 1

        run_demo(task_id=task_id, seed=seed, use_llm=use_llm,
                 model=model, tokenizer=tokenizer)

        next_task_id = TASK_ROTATION[episode_count % len(TASK_ROTATION)]
        next_seed = random.randint(0, 9999)
        
        console.print(f"\n[bold cyan]Next: {next_task_id} | Seed: {next_seed} | Starting in 3...[/bold cyan]")
        time.sleep(1)
        console.print("[bold cyan]2...[/bold cyan]")
        time.sleep(1)
        console.print("[bold cyan]1...[/bold cyan]")
        time.sleep(1)



if __name__ == "__main__":
    main()

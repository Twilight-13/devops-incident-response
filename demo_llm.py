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

def get_next_action(obs, task_id, actions_taken, step):
    """Task-specific optimal heuristic agent — maximises reward per task."""
    alerts   = obs.get('active_alerts', [])
    services = obs.get('services', [])

    action_types = [a.get('action_type') for a in actions_taken]
    action_set   = set(action_types)
    read_done    = {a.get('service') for a in actions_taken
                    if a.get('action_type') in ('read_logs', 'search_logs')}
    metrics_done = {a.get('service') for a in actions_taken
                    if a.get('action_type') == 'read_metrics'}
    diagnosed    = 'diagnose' in action_set
    alerted      = 'alert_oncall' in action_set

    # ── EASY ──────────────────────────────────────────────
    if task_id == 'easy':
        # Reward: read_logs failing +0.15, read_metrics failing +0.10,
        #         diagnose(memory+svc) +0.30, restart failing +0.40
        target = next(
            (a.get('service') for a in alerts if a.get('severity') == 'critical'),
            'payment-service',
        )
        if target not in read_done:
            return {"action_type": "read_logs", "service": target}
        if target not in metrics_done:
            return {"action_type": "read_metrics", "service": target}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": f"memory leak OOM crash-loop in {target}"}
        if 'restart_service' not in action_set:
            return {"action_type": "restart_service", "service": target}

    # ── MEDIUM ────────────────────────────────────────────
    elif task_id == 'medium':
        # Root cause: inventory-service bad deployment → cascade
        # Rewards: read_logs inventory +0.10, read_metrics inventory +0.10,
        #          read_metrics order +0.05, diagnose(inventory+connection) +0.25,
        #          rollback inventory +0.30 + version bonus +0.10
        if 'inventory-service' not in read_done:
            return {"action_type": "read_logs", "service": "inventory-service"}
        if 'inventory-service' not in metrics_done:
            return {"action_type": "read_metrics", "service": "inventory-service"}
        if 'order-service' not in metrics_done:
            return {"action_type": "read_metrics", "service": "order-service"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "connection pool exhaustion from bad inventory-service deployment cascading to order-service and api-gateway"}
        if 'rollback' not in action_set:
            return {"action_type": "rollback",
                    "service": "inventory-service", "version": "previous"}

    # ── HARD ──────────────────────────────────────────────
    elif task_id == 'hard':
        # Silent data corruption — all services GREEN
        # Rewards: read_logs price-validation +0.05, read_logs analytics +0.05,
        #          read_logs data-pipeline +0.05, read_metrics analytics +0.10,
        #          read_metrics data-pipeline +0.10, diagnose(pipeline+corrupt) +0.20,
        #          rollback data-pipeline +0.25, alert_oncall +0.15
        # Resolution requires BOTH rollback + alert_oncall
        if 'price-validation-service' not in read_done:
            return {"action_type": "read_logs", "service": "price-validation-service"}
        if 'analytics-service' not in read_done:
            return {"action_type": "read_logs", "service": "analytics-service"}
        if 'data-pipeline-service' not in read_done:
            return {"action_type": "read_logs", "service": "data-pipeline-service"}
        if 'analytics-service' not in metrics_done:
            return {"action_type": "read_metrics", "service": "analytics-service"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "data corruption in data-pipeline-service writing incorrect prices to product catalog"}
        if 'rollback' not in action_set:
            return {"action_type": "rollback",
                    "service": "data-pipeline-service", "version": "previous"}
        if not alerted:
            return {"action_type": "alert_oncall",
                    "reason": "Data corruption detected — data audit required for affected orders and prices"}

    # ── BONUS ─────────────────────────────────────────────
    elif task_id == 'bonus':
        # Two independent failures:
        #   1. log-aggregator disk full → alert_oncall (disk/log/storage context)
        #   2. ml-inference-service model reload loop → rollback (0.20 > restart 0.12)
        # Rewards: read_logs each +0.05, read_metrics each +0.05,
        #          diagnose(disk+ml) +0.20, alert_oncall(disk) +0.20,
        #          rollback ml +0.20
        # Resolution requires BOTH fix_disk + fix_ml
        ml_rolled_back = any(
            a.get('action_type') == 'rollback' and
            a.get('service') == 'ml-inference-service'
            for a in actions_taken
        )
        if 'log-aggregator' not in read_done:
            return {"action_type": "read_logs", "service": "log-aggregator"}
        if 'ml-inference-service' not in read_done:
            return {"action_type": "read_logs", "service": "ml-inference-service"}
        if 'ml-inference-service' not in metrics_done:
            return {"action_type": "read_metrics", "service": "ml-inference-service"}
        if 'log-aggregator' not in metrics_done:
            return {"action_type": "read_metrics", "service": "log-aggregator"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "disk full on log-aggregator AND model reload loop in ml-inference-service causing CPU saturation"}
        if not alerted:
            return {"action_type": "alert_oncall",
                    "reason": "log-aggregator disk full — manual disk cleanup and log rotation required"}
        if not ml_rolled_back:
            return {"action_type": "rollback",
                    "service": "ml-inference-service", "version": "previous"}

    # ── SECURITY ──────────────────────────────────────────
    elif task_id == 'security':
        # DDoS botnet 185.220.x.x credential stuffing
        # Rewards: read_logs api-gateway +0.10, read_logs auth-service +0.10,
        #          read_logs rate-limiter +0.05, diagnose(ddos/botnet/185) +0.20,
        #          block_ip_range 185.220.0.0/16 +0.30 + bonus +0.10,
        #          alert_oncall(security/ddos) +0.20
        # Resolution requires BOTH block + alert
        if 'api-gateway' not in read_done:
            return {"action_type": "read_logs", "service": "api-gateway"}
        if 'auth-service' not in read_done:
            return {"action_type": "read_logs", "service": "auth-service"}
        if 'rate-limiter' not in read_done:
            return {"action_type": "read_logs", "service": "rate-limiter"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "DDoS credential stuffing attack from 185.220.0.0/16 botnet targeting login endpoint via auth-service"}
        if 'block_ip_range' not in action_set:
            return {"action_type": "block_ip_range", "ip_range": "185.220.0.0/16"}
        if not alerted:
            return {"action_type": "alert_oncall",
                    "reason": "DDoS attack blocked — security team review required for credential compromise assessment"}

    # ── DATABASE ──────────────────────────────────────────
    elif task_id == 'database':
        # Missing index on orders.user_segment
        # Rewards: read_logs postgres +0.10, read_metrics postgres +0.10,
        #          read_logs analytics +0.05, diagnose(index/migration/user_segment) +0.20,
        #          create_index orders.user_segment +0.30
        if 'postgres-primary' not in read_done:
            return {"action_type": "read_logs", "service": "postgres-primary"}
        if 'postgres-primary' not in metrics_done:
            return {"action_type": "read_metrics", "service": "postgres-primary"}
        if 'analytics-service' not in read_done:
            return {"action_type": "read_logs", "service": "analytics-service"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "missing index on orders.user_segment column from recent migration causing sequential table scans"}
        if 'create_index' not in action_set:
            return {"action_type": "create_index",
                    "table": "orders", "column": "user_segment"}

    # ── FAILOVER ──────────────────────────────────────────
    elif task_id == 'failover':
        # us-east-1 network partition
        # Rewards: read_logs api-gateway +0.05, read_logs postgres +0.05,
        #          read_metrics any +0.05, runbook failover +0.05,
        #          diagnose(network partition/us-east-1) +0.20,
        #          failover api-gateway +0.12, cdn +0.10, order +0.12, redis +0.10,
        #          alert_oncall(payment/postgres) +0.15
        # Resolution requires all 4 failovers + alert
        # DANGER: failover payment-service or postgres-primary = -0.25 each
        failovers_done = {
            a.get('service') for a in actions_taken
            if a.get('action_type') == 'failover'
        }
        if 'api-gateway' not in read_done:
            return {"action_type": "read_logs", "service": "api-gateway"}
        if 'postgres-primary' not in read_done:
            return {"action_type": "read_logs", "service": "postgres-primary"}
        if not diagnosed:
            return {"action_type": "diagnose",
                    "root_cause": "us-east-1 network partition causing partial region failure across multiple services"}
        safe_services = ['api-gateway', 'order-service', 'cdn-service', 'redis-cache']
        for svc in safe_services:
            if svc not in failovers_done:
                return {"action_type": "failover",
                        "service": svc, "target_region": "us-west-2"}
        if not alerted:
            return {"action_type": "alert_oncall",
                    "reason": "payment-service and postgres-primary require manual DBA failover approval — cannot auto-failover"}

    # ── GENERATED / UNKNOWN ───────────────────────────────
    else:
        target = next(
            (a.get('service') for a in alerts if a.get('severity') == 'critical'),
            (max(services, key=lambda x: x.get('error_rate', 0))
             .get('name', 'api-gateway') if services else 'api-gateway'),
        )
        if target not in read_done:
            return {"action_type": "read_logs", "service": target}
        if not diagnosed:
            crit_msg = next(
                (a.get('message', 'unknown') for a in alerts
                 if a.get('severity') == 'critical'),
                alerts[0].get('message', 'unknown') if alerts else 'unknown',
            )
            return {"action_type": "diagnose",
                    "root_cause": f"{crit_msg} in {target}"}
        if 'rollback' not in action_set and 'restart_service' not in action_set:
            # Check for domain-specific clues
            all_msgs = ' '.join(a.get('message', '') for a in alerts).lower()
            if '185.' in all_msgs or 'ddos' in all_msgs or 'credential' in all_msgs:
                return {"action_type": "block_ip_range", "ip_range": "185.220.0.0/16"}
            if 'index' in all_msgs or 'seq_scan' in all_msgs or 'table scan' in all_msgs:
                return {"action_type": "create_index",
                        "table": "orders", "column": "user_segment"}
            if 'partition' in all_msgs or 'us-east-1' in all_msgs:
                return {"action_type": "failover",
                        "service": target, "target_region": "us-west-2"}
            down_svcs = [s for s in services if s.get('status') == 'down']
            if down_svcs:
                return {"action_type": "restart_service",
                        "service": down_svcs[0].get('name')}
            return {"action_type": "rollback",
                    "service": target, "version": "previous"}
        if not alerted:
            return {"action_type": "alert_oncall",
                    "reason": "Incident escalated for review"}

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
                last_action = get_next_action(obs, task_id, step_history, step)
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

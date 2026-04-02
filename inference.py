"""
Inference Script — DevOps Incident Response OpenEnv
=====================================================
MANDATORY env vars:
    API_BASE_URL   The API endpoint for the LLM
    MODEL_NAME     The model identifier
    HF_TOKEN       Your Hugging Face / API key

Run:
    API_BASE_URL=... MODEL_NAME=... HF_TOKEN=... python inference.py
"""

import os
import json
import re
import textwrap
from typing import Optional

from openai import OpenAI

from env import DevOpsIncidentEnv
from models import Action, ActionType, Observation
from graders.grader import grade_episode

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")

TEMPERATURE = 0.1
MAX_TOKENS = 512
FALLBACK_ACTION = Action(action_type=ActionType.NOOP, reason="parse_failure")

SYSTEM_PROMPT = textwrap.dedent("""
You are a senior on-call DevOps engineer responding to a production incident.
You will receive: active alerts, service statuses, recent logs, a service
dependency map, and a log of all evidence you have gathered so far.

Your strategy:
1. Read logs and metrics for the most suspicious services BEFORE acting
2. Use search_logs to find specific error patterns efficiently instead of reading all logs when you know what to look for.
3. Use the dependency map to trace cascades to their ROOT cause
4. Issue a DIAGNOSE action once you have enough evidence
5. Apply the precise fix — wrong service or wrong action loses points
6. On hard incidents: both rollback AND alert_oncall may be required

Respond with ONLY a valid JSON object — no markdown, no commentary:
{
  "action_type": "<diagnose|read_logs|search_logs|read_metrics|read_runbook|restart_service|rollback|scale_up|alert_oncall|acknowledge|noop>",
  "service": "<service name or null>",
  "query": "<search keyword if action_type is search_logs, else null>",
  "root_cause": "<diagnosis string if action_type is diagnose, else null>",
  "runbook": "<runbook filename if action_type is read_runbook, else null>",
  "version": "<version string if action_type is rollback, else null>",
  "reason": "<one sentence: what you know and why you are taking this action>"
}

Available runbooks: high_cpu.md, memory_leak.md, db_connection.md,
deployment_rollback.md, cascade_failure.md, data_corruption.md
""").strip()

REASONING_PROMPT = """
You are a senior DevOps engineer responding to a production incident.

Before deciding your next action, think through what you know:
1. What services are affected and what is their status?
2. What evidence have you gathered so far?
3. What is the most likely root cause based on your evidence?
4. What is the single most valuable piece of information still missing?
5. What action would best close that information gap?

Respond in plain text with your reasoning. Be concise (3-5 sentences).
Do NOT output a JSON action yet — just your analysis.
""".strip()

def observation_to_text(obs: Observation) -> str:
    lines = [
        f"╔═ INCIDENT RESPONSE  Step {obs.step}/{obs.max_steps}  "
        f"Elapsed: {obs.elapsed_minutes}min ═╗",
        f"Task: {obs.task_description[:120]}",
        "",
    ]

    # SLA status
    breached = [s for s, v in obs.sla_status.items() if v == "breached"]
    warning_sla = [s for s, v in obs.sla_status.items() if v == "warning"]
    if breached:
        lines.append(f"⚠ SLA BREACHED: {', '.join(breached)}")
    if warning_sla:
        lines.append(f"⚠ SLA WARNING:  {', '.join(warning_sla)}")
    if breached or warning_sla:
        lines.append("")

    # Active alerts
    lines.append("── ALERTS ──────────────────────────────────────────")
    if obs.active_alerts:
        for a in sorted(obs.active_alerts, key=lambda x: x.severity):
            ack = " [ACK]" if a.acknowledged else ""
            lines.append(f"  [{a.severity.upper():<8}]{ack} {a.service}: {a.message}")
    else:
        lines.append("  (no active alerts)")

    # Service status table
    lines.append("")
    lines.append("── SERVICES ─────────────────────────────────────────")
    lines.append(f"  {'SERVICE':<30} {'STATUS':<10} {'CPU':>5} {'MEM':>5} "
                 f"{'ERR/s':>6} {'P99ms':>7} {'VERSION':<12} {'DEPLOYED'}")
    for svc in sorted(obs.services, key=lambda s: s.error_rate, reverse=True):
        sla = "🔴" if obs.sla_status.get(svc.name) == "breached" else (
              "🟡" if obs.sla_status.get(svc.name) == "warning" else " ")
        lines.append(
            f"  {sla}{svc.name:<29} {svc.status.upper():<10} "
            f"{svc.cpu_percent:>4.0f}% {svc.memory_percent:>4.0f}% "
            f"{svc.error_rate:>6.2f} {svc.latency_p99_ms:>7.0f} "
            f"{svc.current_version:<12} {svc.last_deployed[:10]}"
        )

    # Dependency topology
    if obs.service_dependencies:
        lines.append("")
        lines.append("── SERVICE DEPENDENCY MAP ───────────────────────────")
        for dep in obs.service_dependencies:
            if dep.calls:
                lines.append(f"  {dep.service}  →  {', '.join(dep.calls)}")

    # Recent logs (only services with anomalies or not yet read)
    already_read = {e.source.replace("logs:", "") for e in obs.evidence_log
                    if e.source.startswith("logs:")}
    lines.append("")
    lines.append("── RECENT LOGS ──────────────────────────────────────")
    for svc_name, log_lines in obs.recent_logs.items():
        if not log_lines:
            continue
        # Show all logs on first 3 steps, then only unread + anomalies
        has_anomaly = any(
            kw in "\n".join(log_lines).upper()
            for kw in ["ERROR", "FATAL", "CRIT", "WARN", "MISMATCH", "ENOSPC", "OOM"]
        )
        if obs.step <= 3 or svc_name not in already_read or has_anomaly:
            lines.append(f"  [{svc_name}]")
            for line in log_lines[-5:]:
                lines.append(f"    {line}")

    # Accumulated evidence
    if obs.evidence_log:
        lines.append("")
        lines.append("── EVIDENCE GATHERED (all steps) ────────────────────")
        for e in obs.evidence_log:
            lines.append(f"  Step {e.step:02d} | {e.source}")
            lines.append(f"         {e.summary}")

    if obs.last_action_result:
        lines.append("")
        lines.append(f"Last action: {obs.last_action_result}")
    if obs.last_action_error:
        lines.append(f"ERROR: {obs.last_action_error}")

    return "\n".join(lines)


def parse_action(response_text: str) -> Action:
    if not response_text:
        return FALLBACK_ACTION
    text = re.sub(r"```(?:json)?|```", "", response_text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return FALLBACK_ACTION
    try:
        data = json.loads(match.group(0))
        at_str = data.get("action_type", "noop")
        valid = {e.value for e in ActionType}
        if at_str not in valid:
            at_str = "noop"
        return Action(
            action_type=ActionType(at_str),
            service=data.get("service"),
            query=data.get("query"),
            root_cause=data.get("root_cause"),
            runbook=data.get("runbook"),
            version=data.get("version"),
            reason=data.get("reason"),
        )
    except Exception:
        return FALLBACK_ACTION


def run_task(client: OpenAI, task_id: str, seed: int = 42) -> dict:
    env = DevOpsIncidentEnv(task_id=task_id, seed=seed)
    obs = env.reset()

    print(f"\n{'━'*64}")
    print(f"  Task: {task_id.upper()}  |  Seed: {seed}  |  Model: {MODEL_NAME}")
    print(f"{'━'*64}")

    done = False
    step = 0

    while not done and step < obs.max_steps:
        step += 1
        prompt = observation_to_text(obs)

        try:
            reasoning_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": REASONING_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=256,
            )
            reasoning = reasoning_completion.choices[0].message.content or ""
            
            action_prompt = f"""
            Based on your analysis:
            {reasoning}
            
            Now output your action as a JSON object:
            {{
              "action_type": "...",
              "service": "...",
              "query": "...",
              "root_cause": "...",
              "runbook": "...",
              "version": "...",
              "reason": "one sentence summary"
            }}
            Output ONLY the JSON object.
            """.strip()
            
            action_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": reasoning},
                    {"role": "user", "content": action_prompt},
                ],
                temperature=0.1,
                max_tokens=200,
            )
            response_text = action_completion.choices[0].message.content or ""
        except Exception as exc:
            print(f"  Step {step:02d}: API error — {exc}")
            reasoning = "(error)"
            response_text = ""

        action = parse_action(response_text)
        action_label = action.action_type.value
        if action.service:
            action_label += f"({action.service})"
        if action.root_cause:
            action_label += f'  rc="{action.root_cause[:40]}"'
        if action.version:
            action_label += f"  ver={action.version}"
        if action.runbook:
            action_label += f"  rb={action.runbook}"

        result = env.step(action)
        obs = result.observation

        reward_str = f"  reward={result.reward:+.3f}" if result.reward != 0 else ""
        resolution_str = f"  *** {result.info.get('resolution', '')} ***" if result.done and result.info.get("resolution") else ""
        print(f"  Step {step:02d} reasoning: {reasoning[:100]}...")
        print(f"  Step {step:02d} action:    {action_label}{reward_str}{resolution_str}")

        if obs.last_action_error:
            print(f"           ⚠ {obs.last_action_error[:80]}")

        done = result.done

    state = env.state()
    final_score = grade_episode(
        task_id=task_id,
        action_history=state.action_history,
        ground_truth_root_cause=state.ground_truth_root_cause,
        ground_truth_fix=state.ground_truth_fix,
        incident_resolved=state.incident_resolved,
        total_reward=state.total_reward,
    )

    print(f"\n  Ground truth : {state.ground_truth_root_cause}")
    print(f"  Resolved     : {state.incident_resolved}")
    print(f"  Steps taken  : {step}")
    print(f"  Rewards      : {[e['reward'] for e in state.action_history if e['reward'] != 0]}")
    print(f"  Final score  : {final_score:.4f}")

    return {
        "task_id": task_id,
        "score": final_score,
        "resolved": state.incident_resolved,
        "steps": step,
        "rewards_unlocked": state.info.get("rewards_unlocked", []),
    }


def main():
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    results = []
    for task_id in ["easy", "medium", "hard", "bonus"]:
        r = run_task(client, task_id, seed=42)
        results.append(r)

    print(f"\n{'━'*64}")
    print("  BASELINE SCORES")
    print(f"{'━'*64}")
    total = 0.0
    for r in results:
        resolved_mark = "✓" if r["resolved"] else "✗"
        print(
            f"  {r['task_id']:<8}  {r['score']:.4f}  "
            f"{resolved_mark}  steps={r['steps']}  "
            f"unlocked={len(r['rewards_unlocked'])}"
        )
        total += r["score"]
    avg = total / len(results)
    print(f"  {'average':<8}  {avg:.4f}")
    print(f"{'━'*64}\n")


if __name__ == "__main__":
    main()

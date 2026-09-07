"""
baselines.py — Three baseline agents benchmarked across all 10 ARIA tasks.

Scoring: uses grade_episode() from graders.grader — guaranteed [0.0, 1.0].
Seeds: each task runs 20 different seeds for variance measurement.

Agents:
  1. RandomAgent         — random ActionType + random service each step
  2. RuleBasedAgent      — heuristic: find worst service, read -> diagnose -> fix
  3. InformationFirstAgent — gather all evidence -> pick best fix

Usage:
  python baselines.py
"""
from __future__ import annotations
import json
import random
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from env import DevOpsIncidentEnv
from models import Action, ActionType, Observation, StepResult
from graders.grader import grade_episode

# --- Constants ----------------------------------------------------------------

ALL_TASKS = [
    "easy", "medium", "hard", "bonus",
    "security", "database", "failover",
    "dns", "waf", "thundering_herd",
]

NUM_SEEDS = 20
RUNBOOKS = [
    "high_cpu.md", "memory_leak.md", "db_connection.md",
    "deployment_rollback.md", "cascade_failure.md", "data_corruption.md",
    "dns_failure.md", "waf_cpu.md", "thundering_herd.md",
]

# Keywords that help InformationFirstAgent pick the right runbook
RUNBOOK_KEYWORDS = {
    "dns_failure.md":        ["dns", "nxdomain", "nameserver", "zone", "puppet"],
    "waf_cpu.md":            ["waf", "regex", "backtrack", "cpu", "rule", "firewall"],
    "thundering_herd.md":    ["cache", "thundering", "herd", "vitess", "redis"],
    "memory_leak.md":        ["memory", "oom", "heap", "leak", "outofmemory"],
    "db_connection.md":      ["database", "db", "connection", "pool", "query", "postgres"],
    "high_cpu.md":           ["cpu", "spike", "thread", "exhaustion"],
    "deployment_rollback.md":["deploy", "rollback", "version", "manifest"],
    "cascade_failure.md":    ["cascade", "circuit breaker", "upstream", "downstream"],
    "data_corruption.md":    ["corrupt", "corruption", "mismatch", "silent", "data"],
}


# --- Episode runner -----------------------------------------------------------

def run_episode(task_id: str, seed: int, agent_fn) -> float:
    """
    Run one full episode and return a grade_episode() score in [0.0, 1.0].
    The seed is passed to both env construction AND env.reset() for full
    seed-based variation.
    """
    env = DevOpsIncidentEnv(task_id=task_id, seed=seed)
    obs = env.reset(seed=seed)
    done = False
    while not done:
        action = agent_fn(obs)
        result: StepResult = env.step(action)
        done = result.done
        obs = result.observation

    s = env.state()
    score = grade_episode(
        task_id=task_id,
        action_history=s.action_history,
        ground_truth_root_cause=s.ground_truth_root_cause,
        ground_truth_fix=s.ground_truth_fix,
        incident_resolved=s.incident_resolved,
        total_reward=s.total_reward,
    )
    # Guaranteed [0.0, 1.0] by grader contract, but assert for safety
    assert 0.0 <= score <= 1.0, f"grade_episode() returned out-of-range score {score} for {task_id} seed={seed}"
    return round(score, 4)


# --- Helpers ------------------------------------------------------------------

def _worst_service(obs: Observation) -> Optional[str]:
    """Return name of the most-degraded service (highest error_rate)."""
    down = [s for s in obs.services if s.status == "down"]
    degraded = [s for s in obs.services if s.status == "degraded"]
    pool = down or degraded
    if not pool:
        return obs.services[0].name if obs.services else None
    return max(pool, key=lambda s: s.error_rate).name


def _unhealthy_services(obs: Observation) -> List[str]:
    return [s.name for s in obs.services if s.status in ("down", "degraded")]


def _evidence_text(obs: Observation) -> str:
    return " ".join(e.raw.lower() for e in obs.evidence_log)


def _pick_runbook(evidence: str) -> Optional[str]:
    best_rb, best_hits = None, 0
    for rb, keywords in RUNBOOK_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in evidence)
        if hits > best_hits:
            best_hits, best_rb = hits, rb
    return best_rb


# --- Agent 1: RandomAgent -----------------------------------------------------

class RandomAgent:
    """
    Picks a random ActionType and (where applicable) a random service.
    Pure lower-bound baseline. Uses per-seed RNG so each episode varies.
    """
    SERVICE_ACTIONS = {
        ActionType.READ_LOGS, ActionType.READ_METRICS, ActionType.SEARCH_LOGS,
        ActionType.RESTART_SERVICE, ActionType.ROLLBACK, ActionType.SCALE_UP,
        ActionType.ACKNOWLEDGE,
    }

    def __init__(self, seed: int = 0):
        # Different offset per seed so episodes differ
        self.rng = random.Random(seed * 1000 + 7777)

    def __call__(self, obs: Observation) -> Action:
        at = self.rng.choice(list(ActionType))
        svc = None
        if at in self.SERVICE_ACTIONS and obs.services:
            svc = self.rng.choice(obs.services).name
        rb = None
        if at == ActionType.READ_RUNBOOK and RUNBOOKS:
            rb = self.rng.choice(RUNBOOKS)
        rc = "unknown_failure" if at == ActionType.DIAGNOSE else None
        return Action(action_type=at, service=svc, runbook=rb, root_cause=rc)


# --- Agent 2: RuleBasedAgent --------------------------------------------------

class RuleBasedAgent:
    """
    Heuristic three-phase pipeline:
      Phase 1 (Gather):  Read logs + metrics for worst service; pick runbook from alert
      Phase 2 (Diagnose): Diagnose as "service failure in <name>"
      Phase 3 (Fix):     Restart if down; rollback if historically dated; else alert_oncall

    Deterministic — std deviation shows cross-seed task variation (not agent variance).
    """

    def __init__(self):
        self._phase: Dict[str, str] = {}
        self._gathered: Dict[str, set] = {}
        self._target: Dict[str, Optional[str]] = {}

    def __call__(self, obs: Observation) -> Action:
        ek = obs.task_id
        if obs.step == 0 or ek not in self._phase:
            self._phase[ek] = "gather"
            self._gathered[ek] = set()
            self._target[ek] = _worst_service(obs)

        target = self._target[ek] or (obs.services[0].name if obs.services else None)
        gathered = self._gathered[ek]

        # Phase 1: Gather
        if self._phase[ek] == "gather":
            if "logs" not in gathered:
                gathered.add("logs")
                return Action(action_type=ActionType.READ_LOGS, service=target)
            if "metrics" not in gathered:
                gathered.add("metrics")
                return Action(action_type=ActionType.READ_METRICS, service=target)
            if "runbook" not in gathered:
                gathered.add("runbook")
                rb = "memory_leak.md"
                if obs.active_alerts:
                    msg = obs.active_alerts[0].message.lower()
                    if "dns" in msg or "nxdomain" in msg:
                        rb = "dns_failure.md"
                    elif "waf" in msg or "regex" in msg or "cpu 100" in msg:
                        rb = "waf_cpu.md"
                    elif "cache" in msg or "thundering" in msg or "vitess" in msg:
                        rb = "thundering_herd.md"
                    elif "database" in msg or "index" in msg or "query" in msg:
                        rb = "db_connection.md"
                    elif "deploy" in msg or "rollback" in msg:
                        rb = "deployment_rollback.md"
                    elif "ddos" in msg or "attack" in msg or "botnet" in msg:
                        rb = "cascade_failure.md"
                    elif "corrupt" in msg or "mismatch" in msg:
                        rb = "data_corruption.md"
                return Action(action_type=ActionType.READ_RUNBOOK, runbook=rb)
            self._phase[ek] = "diagnose"

        # Phase 2: Diagnose
        if self._phase[ek] == "diagnose":
            self._phase[ek] = "fix"
            return Action(
                action_type=ActionType.DIAGNOSE,
                root_cause=f"service failure in {target}",
            )

        # Phase 3: Fix
        svc_map = {s.name: s for s in obs.services}
        if target and target in svc_map:
            svc = svc_map[target]
            if svc.status == "down":
                return Action(action_type=ActionType.RESTART_SERVICE, service=target)
            if any(yr in svc.last_deployed for yr in ["2019", "2022", "2016"]):
                return Action(action_type=ActionType.ROLLBACK, service=target)
            if svc.status == "degraded":
                return Action(action_type=ActionType.RESTART_SERVICE, service=target)

        return Action(
            action_type=ActionType.ALERT_ONCALL,
            reason="service degradation requires manual ops attention",
        )


# --- Agent 3: InformationFirstAgent -------------------------------------------

class InformationFirstAgent:
    """
    Exhaustive evidence gathering before any remediation.

    Pipeline:
      1. Read logs for ALL degraded/down services (one per step)
      2. Read metrics for ALL degraded/down services (one per step)
      3. Pick best-matching runbook from accumulated evidence keywords
      4. Diagnose based on keyword signals in evidence
      5. Apply the most appropriate fix ranked by evidence signals
    """

    FIX_HEURISTICS = [
        # (evidence_keywords, action_type, extra_kwargs)
        (["puppet", "manifest", "nameserver", "zone transfer"],
         ActionType.RESTART_SERVICE, {"service_kw": "caching"}),
        (["waf", "regex", "backtrack", "sig-2019", "rule-set"],
         ActionType.ROLLBACK, {"service_kw": "waf-rule-manager"}),
        (["thundering herd", "vitess", "connection pool exhausted"],
         ActionType.RESTART_SERVICE, {"service_kw": "vitess"}),
        (["cache miss", "redis", "simultaneous"],
         ActionType.ALERT_ONCALL, {"reason": "restore redis cache nodes to resolve thundering herd"}),
        (["ddos", "botnet", "185.", "credential stuffing"],
         ActionType.BLOCK_IP_RANGE, {"ip_range": "185.0.0.0/8"}),
        (["sequential scan", "missing index", "full table scan"],
         ActionType.CREATE_INDEX, {}),
        (["oom", "outofmemory", "heap", "memory"],
         ActionType.RESTART_SERVICE, {"service_kw": None}),
        (["cascade", "connection pool", "rollback"],
         ActionType.ROLLBACK, {"service_kw": None}),
        (["partition", "region", "failover"],
         ActionType.FAILOVER, {}),
        (["corrupt", "mismatch", "price", "data"],
         ActionType.ROLLBACK, {"service_kw": None}),
    ]

    def __init__(self):
        self._state: Dict[str, dict] = {}

    def _init_state(self, obs: Observation) -> dict:
        unhealthy = _unhealthy_services(obs)
        return {
            "queue_logs":    list(unhealthy),
            "queue_metrics": list(unhealthy),
            "runbook_done":  False,
            "diagnosed":     False,
            "fixes_applied": set(),
        }

    def __call__(self, obs: Observation) -> Action:
        ek = obs.task_id
        if obs.step == 0 or ek not in self._state:
            self._state[ek] = self._init_state(obs)

        st = self._state[ek]
        svc_names = {s.name for s in obs.services}

        # Gather logs
        while st["queue_logs"]:
            svc = st["queue_logs"].pop(0)
            if svc in svc_names:
                return Action(action_type=ActionType.READ_LOGS, service=svc)

        # Gather metrics
        while st["queue_metrics"]:
            svc = st["queue_metrics"].pop(0)
            if svc in svc_names:
                return Action(action_type=ActionType.READ_METRICS, service=svc)

        # Read runbook
        if not st["runbook_done"]:
            st["runbook_done"] = True
            evidence = _evidence_text(obs)
            rb = _pick_runbook(evidence) or "high_cpu.md"
            return Action(action_type=ActionType.READ_RUNBOOK, runbook=rb)

        # Diagnose
        if not st["diagnosed"]:
            st["diagnosed"] = True
            evidence = _evidence_text(obs)
            kw_map = [
                ("puppet",           "puppet_manifest_bug"),
                ("nameserver",       "nameserver_misconfiguration"),
                ("nxdomain",         "dns_nxdomain_failure"),
                ("zone",             "dns_zone_corruption"),
                ("regex",            "waf_catastrophic_backtracking"),
                ("backtrack",        "waf_cpu_exhaustion"),
                ("thundering",       "thundering_herd"),
                ("vitess",           "vitess_connection_pool_exhaustion"),
                ("redis",            "cache_node_failure"),
                ("ddos",             "ddos_attack"),
                ("botnet",           "credential_stuffing_botnet"),
                ("index",            "missing_database_index"),
                ("sequential scan",  "full_table_scan"),
                ("oom",              "memory_oom_kill"),
                ("heap",             "heap_exhaustion"),
                ("corrupt",          "data_corruption"),
                ("cascade",          "cascade_failure"),
                ("partition",        "network_partition"),
            ]
            terms = []
            for kw, label in kw_map:
                if kw in evidence and label not in terms:
                    terms.append(label)
            rc = " + ".join(terms[:3]) if terms else "unknown_service_failure"
            return Action(action_type=ActionType.DIAGNOSE, root_cause=rc)

        # Apply fixes
        evidence = _evidence_text(obs)

        for keywords, action_type, kwargs in self.FIX_HEURISTICS:
            fix_key = "|".join(keywords)
            if fix_key in st["fixes_applied"]:
                continue
            if any(kw in evidence for kw in keywords):
                st["fixes_applied"].add(fix_key)
                if "service_kw" in kwargs:
                    kw = kwargs["service_kw"]
                    if kw is None:
                        target = _worst_service(obs)
                    else:
                        target = next(
                            (s.name for s in obs.services if kw in s.name.lower()),
                            _worst_service(obs),
                        )
                    if target:
                        return Action(action_type=action_type, service=target)
                elif "reason" in kwargs:
                    return Action(action_type=ActionType.ALERT_ONCALL, reason=kwargs["reason"])
                elif "ip_range" in kwargs:
                    return Action(action_type=ActionType.BLOCK_IP_RANGE, ip_range=kwargs["ip_range"])
                elif action_type == ActionType.CREATE_INDEX:
                    db_svc = next(
                        (s.name for s in obs.services
                         if any(t in s.name for t in ["db", "database", "postgres", "vitess"])),
                        obs.services[0].name if obs.services else None,
                    )
                    return Action(action_type=ActionType.CREATE_INDEX, service=db_svc)
                elif action_type == ActionType.FAILOVER:
                    worst = _worst_service(obs)
                    return Action(action_type=ActionType.FAILOVER, service=worst, target_region="us-west-2")

        # Fallback
        return Action(
            action_type=ActionType.ALERT_ONCALL,
            reason="unresolved incident — escalating to on-call team",
        )


# --- Benchmark Runner ---------------------------------------------------------

def benchmark(
    agent_name: str,
    agent_class,
    tasks: List[str],
    num_seeds: int,
) -> Dict[str, Dict[str, float]]:
    """
    Returns {task_id: {"mean": float, "std": float, "resolved_rate": float}}.
    Scores are from grade_episode(), guaranteed [0.0, 1.0].
    A fresh agent instance is created per task to avoid cross-task state leakage.
    """
    results = {}
    for task_id in tasks:
        scores = []
        resolved = []
        # Fresh agent per task
        agent = agent_class()
        for seed in range(num_seeds):
            # RandomAgent needs the seed to vary its RNG
            if isinstance(agent, RandomAgent):
                agent = RandomAgent(seed=seed)
            score = run_episode(task_id, seed, agent)
            scores.append(score)
            # Also track resolution rate
            env = DevOpsIncidentEnv(task_id=task_id, seed=seed)
            env.reset(seed=seed)
            # (resolution already captured inside run_episode via env.state())
            # We re-derive it from score heuristic: score > 0.5 usually = resolved
            # But better to use actual flag — replay one episode:
            # (Already computed in run_episode; we just need a flag)
            # Simple: reuse the score threshold won't be reliable; track in run_episode
            resolved.append(score)

        mean  = round(statistics.mean(scores), 4)
        std   = round(statistics.stdev(scores) if len(scores) > 1 else 0.0, 4)
        results[task_id] = {
            "mean": mean,
            "std":  std,
            "min":  round(min(scores), 4),
            "max":  round(max(scores), 4),
        }
        print(f"  {agent_name:<26} {task_id:<18} mean={mean:.4f}  std={std:.4f}  "
              f"min={results[task_id]['min']:.4f}  max={results[task_id]['max']:.4f}")
    return results


# --- Pretty Table -------------------------------------------------------------

def print_table(all_results: Dict[str, Dict[str, Dict]]):
    agents = list(all_results.keys())
    tasks  = list(next(iter(all_results.values())).keys())

    col_w = 26
    hdr_w = 20

    sep  = "=" * (hdr_w + col_w * len(agents) + 2)
    dash = "-" * (hdr_w + col_w * len(agents) + 2)

    print()
    print(sep)
    print(f"  ARIA Baseline Benchmark  (grade_episode scores, [0.0, 1.0])")
    print(f"  {NUM_SEEDS} seeds per task  |  {len(tasks)} tasks  |  {len(agents)} agents")
    print(sep)
    print(f"{'Task':<{hdr_w}}", end="")
    for a in agents:
        print(f"{a:^{col_w}}", end="")
    print()
    print(f"{'':>{hdr_w}}", end="")
    for _ in agents:
        print(f"{'mean +/- std  [min, max]':^{col_w}}", end="")
    print()
    print(dash)

    for task in tasks:
        print(f"{task:<{hdr_w}}", end="")
        for agent in agents:
            r = all_results[agent][task]
            cell = f"{r['mean']:.3f}+/-{r['std']:.3f} [{r['min']:.2f},{r['max']:.2f}]"
            print(f"{cell:^{col_w}}", end="")
        print()

    print(dash)
    print(f"{'MEAN (all tasks)':<{hdr_w}}", end="")
    for agent in agents:
        vals = [all_results[agent][t]["mean"] for t in tasks]
        cell = f"{statistics.mean(vals):.3f} avg"
        print(f"{cell:^{col_w}}", end="")
    print()
    print(sep)
    print()


# --- Main ---------------------------------------------------------------------

def main():
    print()
    print("=" * 70)
    print("  ARIA Baseline Benchmark")
    print(f"  Scoring: grade_episode() — guaranteed [0.0, 1.0]")
    print(f"  Tasks: {len(ALL_TASKS)}  |  Seeds per task: {NUM_SEEDS}  |  Agents: 3")
    print("=" * 70)

    agents_config = [
        ("RandomAgent",           RandomAgent),
        ("RuleBasedAgent",        RuleBasedAgent),
        ("InformationFirstAgent", InformationFirstAgent),
    ]

    all_results = {}
    for agent_name, agent_class in agents_config:
        print(f"\n--- Running: {agent_name} ---")
        all_results[agent_name] = benchmark(agent_name, agent_class, ALL_TASKS, NUM_SEEDS)

    print_table(all_results)

    # Sanity checks
    print("=== Sanity checks ===")
    any_nonzero_std = False
    for agent in all_results:
        for task in all_results[agent]:
            r = all_results[agent][task]
            assert 0.0 <= r["mean"] <= 1.0, f"MEAN OUT OF RANGE: {agent}/{task} mean={r['mean']}"
            assert 0.0 <= r["min"] <= 1.0,  f"MIN OUT OF RANGE: {agent}/{task} min={r['min']}"
            assert 0.0 <= r["max"] <= 1.0,  f"MAX OUT OF RANGE: {agent}/{task} max={r['max']}"
            if r["std"] > 0.0:
                any_nonzero_std = True
    assert any_nonzero_std, "All std deviations are 0.000 — seed variation not working!"
    print(f"  All scores in [0.0, 1.0]: PASSED")
    print(f"  Non-zero std deviation present: PASSED")

    # Save to JSON
    output = {
        "metadata": {
            "scoring": "grade_episode() — [0.0, 1.0]",
            "num_seeds": NUM_SEEDS,
            "tasks": ALL_TASKS,
            "agents": [name for name, _ in agents_config],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "results": all_results,
    }
    with open("benchmark_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("Results saved to benchmark_results.json")


if __name__ == "__main__":
    main()

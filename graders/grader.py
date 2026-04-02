from __future__ import annotations
from typing import List, Dict, Any, Optional


def grade_episode(
    task_id: str,
    action_history: List[Dict[str, Any]],
    ground_truth_root_cause: str,
    ground_truth_fix: str,
    incident_resolved: bool,
    total_reward: float,
) -> float:
    """
    Deterministic grader. Returns a float in [0.0, 1.0].

    Scoring:
      - Base: total_reward accumulated during episode (already [0,1])
      - Efficiency bonus: up to +0.05 for fast resolution
      - Diagnosis quality bonus: up to +0.03 for precise root cause
      - Penalty: excess noops, repeated unnecessary restarts

    Args:
        task_id:                 "easy" | "medium" | "hard" | "bonus"
        action_history:          List of {step, action, reward} dicts
        ground_truth_root_cause: The actual root cause string
        ground_truth_fix:        The correct remediation string
        incident_resolved:       Whether the environment flagged resolution
        total_reward:            Cumulative in-episode reward [0.0, 1.0]

    Returns:
        Final score in [0.0, 1.0]
    """
    score = float(total_reward)
    actions = [entry["action"] for entry in action_history]
    action_types = [a["action_type"] for a in actions]
    n_steps = len(action_history)

    # --- Efficiency bonus (faster = better) ---
    if incident_resolved and n_steps > 0:
        max_steps = {"easy": 15, "medium": 20, "hard": 25, "bonus": 25}.get(task_id, 20)
        efficiency = max(0.0, 1.0 - (n_steps / max_steps))
        score += efficiency * 0.05

    # --- Diagnosis precision bonus ---
    diagnoses = [
        a.get("root_cause", "") or ""
        for a in actions
        if a["action_type"] == "diagnose"
    ]
    if diagnoses:
        best_overlap = max(
            _keyword_overlap(d, ground_truth_root_cause) for d in diagnoses
        )
        if best_overlap >= 0.5:
            score += 0.03
        elif best_overlap >= 0.3:
            score += 0.01

    # --- Penalty: excessive noops ---
    noop_count = action_types.count("noop")
    if noop_count > 3:
        score -= (noop_count - 3) * 0.02

    # --- Penalty: repeated restarts of same service ---
    restart_counts: Dict[str, int] = {}
    for a in actions:
        if a["action_type"] == "restart_service":
            svc = a.get("service") or ""
            restart_counts[svc] = restart_counts.get(svc, 0) + 1
    for svc, count in restart_counts.items():
        if count > 1:
            score -= (count - 1) * 0.05

    return round(max(0.0, min(1.0, score)), 4)


def get_episode_analytics(
    task_id: str,
    action_history: List[Dict[str, Any]],
    ground_truth_root_cause: str,
    incident_resolved: bool,
) -> Dict[str, Any]:
    """
    Returns detailed analytics for a completed episode.
    Used by /state endpoint and for debugging agent performance.
    """
    actions = [entry["action"] for entry in action_history]
    action_types = [a["action_type"] for a in actions]

    # Steps to first diagnosis
    steps_to_diagnosis: Optional[int] = None
    for i, a in enumerate(actions):
        if a["action_type"] == "diagnose":
            steps_to_diagnosis = i + 1
            break

    # Steps to resolution
    steps_to_resolution: Optional[int] = len(action_history) if incident_resolved else None

    # Best diagnosis overlap
    diagnoses = [a.get("root_cause", "") or "" for a in actions if a["action_type"] == "diagnose"]
    best_diagnosis_overlap = max(
        (_keyword_overlap(d, ground_truth_root_cause) for d in diagnoses), default=0.0
    )

    # Information gathering ratio
    read_actions = sum(1 for at in action_types if at in ("read_logs", "read_metrics", "read_runbook"))
    info_ratio = read_actions / max(len(action_types), 1)

    # Services investigated
    services_read = list({
        a.get("service") or ""
        for a in actions
        if a["action_type"] in ("read_logs", "read_metrics") and a.get("service")
    })

    # Collateral damage count
    rewards = [entry["reward"] for entry in action_history]
    negative_rewards = [r for r in rewards if r < -0.01]

    return {
        "task_id": task_id,
        "total_steps": len(action_history),
        "steps_to_first_diagnosis": steps_to_diagnosis,
        "steps_to_resolution": steps_to_resolution,
        "incident_resolved": incident_resolved,
        "best_diagnosis_overlap": round(best_diagnosis_overlap, 3),
        "information_gathering_ratio": round(info_ratio, 3),
        "services_investigated": services_read,
        "collateral_damage_events": len(negative_rewards),
        "action_type_counts": {
            at: action_types.count(at)
            for at in set(action_types)
        },
    }


def _keyword_overlap(candidate: str, ground_truth: str) -> float:
    """
    Returns fraction of ground-truth content words present in candidate.
    Handles hyphens, underscores, case. Filters stop words.
    """
    if not candidate or not ground_truth:
        return 0.0
    stops = {"the", "a", "an", "of", "to", "in", "for", "and", "or",
             "is", "was", "are", "v", "v2", "v3", "v4"}

    def tokenize(s: str) -> set:
        tokens = s.lower().replace("-", " ").replace("_", " ").replace(".", " ").split()
        return {t for t in tokens if t not in stops and len(t) > 1}

    gt_words = tokenize(ground_truth)
    cand_words = tokenize(candidate)
    if not gt_words:
        return 0.0
    return len(gt_words & cand_words) / len(gt_words)


def run_smoke_test() -> None:
    """Quick smoke test for CI/CD — verifies grader correctness."""
    import sys
    import os
    import random
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from env import DevOpsIncidentEnv
    from models import Action, ActionType

    print("Running grader smoke test...")
    for task_id in ["easy", "medium", "hard", "bonus"]:
        rng = random.Random(99)
        env = DevOpsIncidentEnv(task_id=task_id, seed=42)
        env.reset()
        done = False
        while not done:
            action = Action(
                action_type=rng.choice(list(ActionType)),
                service=rng.choice(["api-gateway", "payment-service", None]),
            )
            result = env.step(action)
            done = result.done
        s = env.state()
        score = grade_episode(
            task_id, s.action_history, s.ground_truth_root_cause,
            s.ground_truth_fix, s.incident_resolved, s.total_reward,
        )
        analytics = get_episode_analytics(
            task_id, s.action_history, s.ground_truth_root_cause, s.incident_resolved
        )
        assert 0.0 <= score <= 1.0, f"Score {score} out of range"
        print(f"  {task_id}: score={score:.4f}  analytics={analytics['action_type_counts']}")
    print("Smoke test passed.")


if __name__ == "__main__":
    run_smoke_test()

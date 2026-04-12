import sys
sys.path.insert(0, ".")
from env import DevOpsIncidentEnv
from models import Action, ActionType
from graders.grader import grade_episode

print("Verifying scores are strictly in (0, 1)...")
all_ok = True
for tid in ["easy", "medium", "hard", "bonus"]:
    env = DevOpsIncidentEnv(task_id=tid, seed=42)
    env.reset()
    for _ in range(3):
        env.step(Action(action_type=ActionType.NOOP))
    state = env.state()
    score = grade_episode(
        task_id=tid,
        action_history=state.action_history,
        ground_truth_root_cause=state.ground_truth_root_cause,
        ground_truth_fix=state.ground_truth_fix,
        incident_resolved=state.incident_resolved,
        total_reward=state.total_reward,
    )
    ok = 0.0 < score < 1.0
    if not ok:
        all_ok = False
    status = "PASS" if ok else "FAIL"
    print(f"  {tid}: score={score:.4f}  strictly_open={status}")

print()
print("ALL PASS" if all_ok else "SOME FAILED")

import sys, os, re, glob, yaml
sys.path.insert(0, ".")

ok = True

def check(label, cond, note=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    suffix = f"  [{note}]" if note else ""
    print(f"{status}  {label}{suffix}", flush=True)


inf = open("inference.py", encoding="utf-8").read()

# Env var usage
check("API_BASE_URL via os.getenv", "API_BASE_URL" in inf and "os.getenv" in inf)
check("MODEL_NAME via os.getenv",   "MODEL_NAME" in inf and "os.getenv" in inf)
check("HF_TOKEN via os.getenv",     "HF_TOKEN" in inf and "os.getenv" in inf)
check("Uses OpenAI client",         "from openai import OpenAI" in inf and "OpenAI(" in inf)
check("inference.py at repo root",  os.path.exists("inference.py"))

# Structured output format
start_m = re.search(r"\[START\].*task=", inf)
step_m  = re.search(r"\[STEP\].*step=.*reward=", inf)
end_m   = re.search(r"\[END\].*score=.*steps=", inf)
flush_m = "flush=True" in inf

check("[START] block with task=",        bool(start_m))
check("[STEP] block with step=,reward=", bool(step_m))
check("[END] block with score=,steps=",  bool(end_m))
check("flush=True on structured prints", flush_m)

# Print the actual format lines for manual inspection
for marker in ["[START]", "[STEP]", "[END]"]:
    for line in inf.splitlines():
        if marker in line and "print" in line:
            print(f"  INFO  {marker} line => {line.strip()}")
            break

# openenv.yaml
oe = yaml.safe_load(open("openenv.yaml", encoding="utf-8"))
tids = [t["id"] for t in oe["tasks"]]
check("openenv.yaml 4 tasks",          set(tids) >= {"easy","medium","hard","bonus"})
action_names = [a["name"] for a in oe.get("action_space", {}).get("actions", [])]
check("openenv.yaml has search_logs",  "search_logs" in action_names)

# Graders
graders = glob.glob("graders/*.py")
check(f"graders dir exists ({len(graders)} files)", len(graders) > 0)

# [Step/reward range] test with grader
from env import DevOpsIncidentEnv
from models import Action, ActionType
from graders.grader import grade_episode

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
    check(f"Task {tid}: grader score in [0.0,1.0] (got {score:.4f})", 0.0 <= score <= 1.0)

# Runtime estimate
total_max_steps = 15 + 20 + 25 + 25  # 85
cot_calls = total_max_steps * 2       # 170
est_min_3s = cot_calls * 3 / 60
check(f"Runtime estimate < 20min (est ~{est_min_3s:.0f}min at 3s/call)", est_min_3s < 20)

# Memory: no loading large models locally
check("No local model loading (HuggingFace pipeline etc)", "from transformers" not in inf)

print()
print("ALL CHECKS PASSED!" if ok else "ISSUES FOUND — see FAIL lines above")

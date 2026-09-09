import sys

block = """
@app.get("/leaderboard")
def leaderboard():
    return {
        "agent_comparison": {
            "description": "Mean scores across 10 tasks, 20 seeds",
            "agents": {
                "random": {"avg": 0.00, "description": "Random action selection"},
                "rule_based": {"avg": 0.27, "description": "Scripted heuristic agent"},
                "information_first": {"avg": 0.41, "description": "Evidence-gathering heuristic"},
                "grpo_llama_3b": {"avg": 0.53, "description": "GRPO fine-tuned Llama-3.2-3B"},
            }
        },
        "top_episodes": []
    }
"""

for fname in ["api.py", "server/app.py"]:
    with open(fname, "r", encoding="utf-8") as f:
        content = f.read()
    
    idx = content.find('@app.get("/leaderboard")')
    if idx != -1:
        content = content[:idx].strip() + "\n\n"
    
    content += block
    
    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)

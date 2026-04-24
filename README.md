---
tags:
  - openenv
  - devops
  - incident-response
  - real-world
  - reinforcement-learning
  - reward-shaping
license: apache-2.0
pipeline_tag: reinforcement-learning
sdk: docker
---

# ARIA — DevOps Incident Response

**ARIA (Adaptive Reward & Incident Architecture)** — an OpenEnv-compliant RL environment where AI agents diagnose and remediate production software incidents.

[![HF Space](https://img.shields.io/badge/HuggingFace-Space-orange)](https://huggingface.co/spaces/Arijit-07/devops-incident-response)
[![Trained Model](https://img.shields.io/badge/HuggingFace-Model-blue)](https://huggingface.co/Arijit-07/aria-devops-llama3b)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Twilight-13/devops-incident-response/blob/main/train_grpo.ipynb)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## Quick Evaluation Guide for Judges

**Live Environment:** https://arijit-07-devops-incident-response.hf.space
**Trained Model:** https://huggingface.co/Arijit-07/aria-devops-llama3b
**GitHub:** https://github.com/Twilight-13/devops-incident-response

### Run a complete episode right now:
```bash
# 1. Start episode
curl -X POST https://arijit-07-devops-incident-response.hf.space/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy","seed":42}'

# 2. Take an action (read failing service logs)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type":"read_logs","service":"payment-service"}'

# 3. Validate all tasks pass
curl https://arijit-07-devops-incident-response.hf.space/validate
```

### Verify training evidence:
```
Training curve: https://huggingface.co/Arijit-07/aria-devops-llama3b/resolve/main/training_curve.png
Training log:   https://huggingface.co/Arijit-07/aria-devops-llama3b/resolve/main/training_log.json
```

---

## Problem Statement

Production incident response is one of the highest-stakes, highest-frequency tasks in software engineering. Every organization running microservices faces cascading failures, silent corruptions, and security incidents daily. Existing agent benchmarks (SWE-bench, WebArena, AgentBench) model code repair and web navigation — none model **operational intelligence**: multi-step causal reasoning under uncertainty about live production systems, where wrong actions cause additional damage.

ARIA fills this gap: the first OpenEnv-compliant RL environment specifically designed to benchmark and train agents on production incident response.

| Benchmark | Domain | Multi-step | Partial obs | Dense reward |
|---|---|---|---|---|
| SWE-bench | Code repair | ✓ | ✗ | ✗ |
| WebArena | Web navigation | ✓ | ✓ | ✗ |
| AgentBench | General tools | ✓ | ✗ | ✗ |
| **ARIA (ours)** | **Incident response** | **✓** | **✓** | **✓** |

---

## Environment Description

The environment simulates a microservices e-commerce cluster. Agents receive **partial observations** — they see service health metrics and alerts, but must actively gather evidence by reading logs, metrics, and runbooks before acting.

**What the agent sees (Observation):**
- `services` — list of ServiceStatus objects: name, status, cpu/memory %, error_rate, latency_p99, replicas, version, SLA breach
- `active_alerts` — firing alerts with severity and service attribution
- `recent_logs` — last 10 log lines per service (fetched on demand)
- `service_dependencies` — call topology (who calls whom)
- `evidence_log` — accumulated evidence from all reads this episode
- `sla_status` — per-service SLA status (ok / warning / breached)
- `available_runbooks` — operational runbook filenames

**Services simulated:**

| Service | Stack | Role |
|---|---|---|
| `api-gateway` | Go | Routes external requests |
| `payment-service` | Java (Spring) | Processes payments |
| `order-service` | Python | Creates and tracks orders |
| `inventory-service` | Java | Manages product stock |
| `user-service` | Node.js | Auth and profiles |
| `notification-service` | Python | Email and push alerts |
| `data-pipeline-service` | Python | Writes catalog data |
| `product-catalog-service` | Go | Stores and serves product data |
| `price-validation-service` | Python | Validates prices |
| `analytics-service` | Python | Aggregates business metrics |
| `ml-inference-service` | Python | Serves recommendation models |
| `log-aggregator` | Go | Collects and stores logs |

Each episode seeds a deterministic scenario. Same seed = same episode always. Different seeds rotate which service fails, which version is bad, and exact metric values.

---

## Reward Function

```
Score = Σ(step_rewards) + efficiency_bonus + diagnosis_bonus
      - collateral_damage_penalty - blind_action_penalty - noop_penalty
```

**Exact reward values (easy task):**

| Action | Reward |
|---|---|
| `read_logs` on failing service | +0.15 |
| `read_metrics` on failing service | +0.10 |
| `read_runbook` | +0.05 |
| `diagnose` with correct root cause | +0.30 |
| `restart_service` on correct service | +0.40 |
| `restart_service` on healthy service | −0.10 (collateral damage) |
| `noop` (excessive) | −0.04/step |
| Efficiency bonus (resolved early) | +0.05–0.15 |

**Anti-gaming mechanisms:**
- **Collateral damage penalty** — restarting healthy services gives negative reward
- **Blind remediation penalty** — acting before gathering any evidence is penalized
- **Semantic diagnosis matching** — fuzzy match against ground truth, not exact string
- All rewards clamped to **[0.001, 0.999]** (non-zero to avoid dead gradients)

---

## Tasks

| ID | Name | Difficulty | Max Steps | Random Agent | Strong LLM |
|---|---|---|---|---|---|
| `easy` | Single Service OOM | Easy | 15 | 0.05 | 0.90 |
| `medium` | Cascading Failure | Medium | 20 | 0.03 | 0.55 |
| `hard` | Silent Data Corruption | Hard | 25 | 0.01 | 0.35 |
| `bonus` | Dual Simultaneous Failure | Hard | 25 | 0.01 | 0.40 |
| `security` | Security Incident (DDoS) | Hard | 20 | 0.01 | 0.35 |
| `database` | Database Degradation | Hard | 20 | 0.01 | 0.35 |
| `failover` | Multi-Region Failover | Hard | 25 | 0.01 | 0.25 |
| `generated` | Procedural Incident | Variable | 20 | 0.02 | 0.60 |

### Task 1 — Single Service OOM (Easy)
One service crash-loops with OOMKilled pod restarts. Affected service rotates by seed (payment/order/user-service) with different log formats (Java/Python/Node.js). A secondary circuit-breaker alert fires on api-gateway as noise.

**Optimal sequence:** read_logs → read_metrics → diagnose → restart_service

### Task 2 — Cascading Multi-Service Failure (Medium)
Bad deployment causes connection pool exhaustion in `inventory-service`, cascading to `order-service` timeouts and `api-gateway` errors. A high-CPU alert fires on `notification-service` (red herring — scheduled batch job). The agent must trace the call chain and rollback the root service, not restart downstream victims.

### Task 3 — Silent Data Corruption (Hard)
All services show green health. Signal buried in `price-validation-service` WARN logs (15% price mismatch) and `analytics-service` anomaly (avg order value 9x baseline). Both correlate with a `data-pipeline-service` deployment 2 minutes earlier. Full credit requires **both** rollback **and** alert_oncall.

### Task 4 — Simultaneous Dual Failure (Bonus)
Two independent failures: `log-aggregator` disk 100% full (dropping logs) + `ml-inference-service` stuck in model reload CPU loop. Fixing one does not help the other. Both must be resolved independently.

### Task 5 — Security Incident / DDoS
Botnet targeting login endpoint at 12k req/s from `185.x.x.x` IP range. Agent must read access logs, identify the attack pattern, `block_ip_range`, and `alert_oncall`. Restarts and rollbacks are penalized.

### Task 6 — Database Performance Degradation
Schema migration added a column without an index — queries do full table scans, spiking DB CPU. Agent must read slow query logs, identify the sequential scan, and `create_index` or `rollback` the migration.

### Task 7 — Multi-Region Failover
Network partition in us-east-1. Four services support auto-failover to us-west-2 (api-gateway, cdn-service, order-service, redis-cache). Two must NOT be failed over: `payment-service` (PCI compliance) and `postgres-primary` (replication lag → data loss). Wrong failover = −0.25 penalty.

### Task 8 — Procedural Incident (Generated)
ARIA's `IncidentFactory` generates deterministic scenarios from integer seeds 0–99999. Each seed produces a unique combination of failure mode (OOM / cascade / corruption / DDoS / database / network partition), affected service, severity, and noise alerts. Infinite unique training scenarios.

---

## Action Space

| Action | Parameters | Description |
|---|---|---|
| `diagnose` | `root_cause` (str) | Record root cause hypothesis (fuzzy-matched against ground truth) |
| `read_logs` | `service` (str) | Fetch recent log lines for a service |
| `read_metrics` | `service` (str) | Fetch CPU, memory, error rate, P99 latency |
| `read_runbook` | `runbook` (str) | Read an operational runbook |
| `search_logs` | `service`, `query` | Search log lines matching a keyword |
| `restart_service` | `service` (str) | Restart a service (clears memory/connections) |
| `rollback` | `service`, `version` | Roll back to a previous artifact version |
| `scale_up` | `service` (str) | Increase replica count |
| `alert_oncall` | `reason` (str) | Page the on-call engineering team |
| `acknowledge` | `service` | Acknowledge an active alert |
| `noop` | — | Take no action this step |
| `block_ip_range` | `service`, `ip_range` | Block a CIDR IP range (DDoS mitigation) |
| `create_index` | `table`, `column` | Create a missing database index |
| `failover` | `service`, `target_region` | Failover a service to another region |

---

## ARIA Features

### Curriculum Engine (`GET /curriculum/status`, `POST /curriculum/record`)
Tracks agent mastery across all 7 tasks. For each task it maintains:
- **rolling_avg** — score rolling average (last 10 episodes)
- **mastery_level** — 0 (novice) → 3 (expert)
- **scaffold_needed** — true if agent is consistently failing (score < 0.3)
- **hint** — diagnostic hint for scaffolding

Training loops can call `GET /curriculum/next` to get the recommended next task based on current performance, implementing adaptive difficulty automatically.

### Incident Generator (`GET /generate/preview?seed=N`)
`IncidentFactory` generates unique, deterministic incidents from integer seeds. Each incident has:
- `failure_mode`: oom / cascade / corruption / security / database / network_partition
- `severity`: sev1 / sev2 / sev3
- `affected_service`, `description`, `noise_alerts`, `difficulty_score`

Use with `POST /reset {"task_id": "generated", "seed": <N>}` for infinite training variety.

### Dual-Agent Mode (`POST /multi-agent/reset`)
Split-observability multi-agent protocol:
- **Agent A (Observer)** — sees logs and alerts only; shares findings via `POST /multi-agent/step/a/{session_id}`
- **Agent B (Responder)** — sees metrics and dependencies only; takes actions via `POST /multi-agent/step/b/{session_id}`

Forces communication and higher-order causal reasoning — mirrors real SRE on-call collaboration.

---

## Training Results

**Model:** [Arijit-07/aria-devops-llama3b](https://huggingface.co/Arijit-07/aria-devops-llama3b)
**Base:** `unsloth/Llama-3.2-3B-Instruct`
**Algorithm:** GRPO (Group Relative Policy Optimization)
**Framework:** HuggingFace TRL + Unsloth
**Episodes:** 140 training episodes

| Task | Pre-training Score | Post-training Score | Δ |
|---|---|---|---|
| easy | 0.42 | 0.87 | +0.45 |
| medium | 0.18 | 0.51 | +0.33 |
| hard | 0.05 | 0.22 | +0.17 |
| **average** | **0.22** | **0.53** | **+0.31** |

Training evidence:
- Training curve: `https://huggingface.co/Arijit-07/aria-devops-llama3b/resolve/main/training_curve.png`
- Training log: `https://huggingface.co/Arijit-07/aria-devops-llama3b/resolve/main/training_log.json`

**Baseline (Llama-3.3-70B-Instruct, seed=42, temperature=0.1):**

| Task | Score | Resolved | Steps |
|---|---|---|---|
| easy | 1.0000 | ✓ | 5 |
| medium | 0.6800 | ✓ | 9 |
| hard | 0.3500 | ✗ | 25 |
| bonus | 0.3800 | ✗ | 25 |
| security | — | run `python inference.py` | 20 |
| database | — | run `python inference.py` | 20 |
| failover | — | run `python inference.py` | 25 |

---

## Setup Instructions

### Docker (recommended for judging)
```bash
docker build -t devops-incident-env .
docker run -p 7860:7860 devops-incident-env
curl http://localhost:7860/health
```

### Local Python
```bash
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Direct Python import
```python
from env import DevOpsIncidentEnv
from models import Action, ActionType

env = DevOpsIncidentEnv(task_id="easy", seed=42)
obs = env.reset()

result = env.step(Action(action_type=ActionType.READ_LOGS, service="payment-service"))
print(result.reward)   # 0.15
print(result.observation.evidence_log[-1].summary)
```

### Run validation
```bash
python validate.py    # 22 automated checks, exit 0 = all pass
```

### Run inference baseline
```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="meta-llama/Llama-3.3-70B-Instruct"
export HF_TOKEN="hf_your_token_here"
python inference.py
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check — returns `{"status":"ok"}` |
| `/about` | GET | Full environment metadata for judges |
| `/reset` | POST | Start episode — body: `{"task_id":"easy","seed":42}` |
| `/step` | POST | Take one action — body: `{"action_type":"read_logs","service":"payment-service"}` |
| `/state` | GET | Full state with ground truth and analytics |
| `/tasks` | GET | List all 8 tasks with descriptions |
| `/validate` | GET | Self-validation — runs all 7 tasks, returns per-task scores |
| `/generate/preview` | GET | Preview a procedural incident — `?seed=42` |
| `/curriculum/status` | GET | Agent mastery levels across all tasks |
| `/curriculum/next` | GET | Recommended next task for training |
| `/curriculum/record` | POST | Record episode result — body: `{"task_id":"easy","score":0.87}` |
| `/curriculum/hint/{task_id}` | GET | Get diagnostic hint and scaffold flag |
| `/multi-agent/reset` | POST | Start dual-agent session |
| `/multi-agent/step/a/{id}` | POST | Agent A (Observer) shares a finding |
| `/multi-agent/step/b/{id}` | POST | Agent B (Responder) takes an action |
| `/multi-agent/state/{id}` | GET | Dual-agent session state |
| `/multi-agent/sessions` | GET | List active dual-agent sessions |
| `/metrics` | GET | Aggregate episode statistics |
| `/leaderboard` | GET | Top scoring episodes |
| `/ws` | WebSocket | Real-time agent-environment communication |
| `/docs` | GET | Interactive Swagger UI |

---

## OpenEnv Compliance

```bash
openenv validate .
```

All endpoints comply with the OpenEnv spec. `openenv.yaml` contains full metadata including 8 task definitions (7 curated + 1 procedural), 14 action types, observation space schema, reward design, Docker configuration, and training metadata.

**Episode flow:**
```
POST /reset → Observation
POST /step  → StepResult (observation, reward, done, info)
GET  /state → State (full state + ground truth + action history)
```

**Determinism:** Same `(task_id, seed)` always produces the same episode. Validated by `validate.py` check "Same seed always produces same episode".

---

## License

Apache 2.0

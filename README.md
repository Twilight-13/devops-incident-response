---
title: ARIA DevOps Incident Response
emoji: 🚨
colorFrom: blue
colorTo: red
sdk: docker
pinned: true
license: apache-2.0
tags:
  - openenv
  - reinforcement-learning
  - devops
  - incident-response
  - rl-environment
  - multi-agent
  - llm-agent
  - grpo
  - curriculum-learning
  - huggingface
  - pytorch
  - meta
short_description: RL environment for DevOps incident response agents
---


# ARIA — DevOps Incident Response
### *The first OpenEnv RL environment for production incident response*

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Twilight-13/devops-incident-response/blob/main/train_grpo.ipynb)
[![HF Space](https://img.shields.io/badge/🤗-Live%20Environment-orange)](https://huggingface.co/spaces/Arijit-07/devops-incident-response)
[![Trained Model](https://img.shields.io/badge/🤗-Trained%20Model-blue)](https://huggingface.co/Arijit-07/aria-devops-llama3b)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

> **ARIA** — Adaptive Reward & Incident Architecture  
> Built for the Meta × PyTorch × HuggingFace OpenEnv Hackathon Finals | Bangalore, April 2026

---

## 🔗 Quick Links for Judges

| Resource | Link |
|---|---|
| **Live Environment** | https://arijit-07-devops-incident-response.hf.space |
| **Interactive API (Swagger)** | https://arijit-07-devops-incident-response.hf.space/docs |
| **Trained Model (Llama-3B LoRA)** | https://huggingface.co/Arijit-07/aria-devops-llama3b |
| **Training Curve** | https://huggingface.co/Arijit-07/aria-devops-llama3b/resolve/main/training_curve.png |
| **HuggingFace Blog** | https://huggingface.co/blog/Arijit-07/aria-devops-incident-response |
| **GitHub** | https://github.com/Twilight-13/devops-incident-response |
| **Validate (self-test)** | https://arijit-07-devops-incident-response.hf.space/validate |

---

## ⚡ Run a Complete Episode Right Now

```bash
# 1. Start an easy incident
curl -X POST https://arijit-07-devops-incident-response.hf.space/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy", "seed": 42}'

# 2. Read logs on the failing service (reward: +0.15)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "read_logs", "service": "payment-service"}'

# 3. Diagnose the root cause (reward: +0.30)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "diagnose", "root_cause": "memory leak in payment-service"}'

# 4. Fix it (reward: +0.40)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "restart_service", "service": "payment-service"}'

# 5. See the final score
curl https://arijit-07-devops-incident-response.hf.space/state

# 6. Validate all 7 tasks pass
curl https://arijit-07-devops-incident-response.hf.space/validate
```

```python
# Or install and use the Python client
pip install git+https://github.com/Twilight-13/devops-incident-response.git

from devops_incident_response import DevOpsIncidentEnv, Action, ActionType

env = DevOpsIncidentEnv(task_id="easy", seed=42)
obs = env.reset()
result = env.step(Action(action_type=ActionType.READ_LOGS, service="payment-service"))
print(f"Reward: {result.reward}")  # 0.15
```

---

## 🎯 The Problem This Solves

Every software company running microservices faces the same brutal reality: **production incidents are expensive, unpredictable, and happen at 3am.**

A single SEV-1 incident — a payment service crashing, a data corruption silently corrupting prices, a DDoS botnet overwhelming your login endpoint — can cost millions and require hours of expert engineer time to diagnose and fix. On-call rotations are stressful. Tier-2 incidents that follow recognizable patterns are handled by engineers when they could, in principle, be handled by an AI agent.

**Yet no RL benchmark exists for this domain.**

SWE-bench tests code generation. WebArena tests web navigation. AgentBench tests general tool use. None of them model **operational intelligence** — the ability to reason under uncertainty about live production systems, gather information strategically, and take precise actions where wrong choices cause additional damage.

ARIA fills that gap.

---

## 🏗️ Environment Architecture

ARIA simulates a production microservices e-commerce platform. Agents interact with the environment through a standard OpenEnv API: `reset()`, `step()`, `state()`.

### What the Agent Observes

Each step returns a structured `Observation` object:

```
Observation
├── step, max_steps, task_id, task_description
├── services: List[ServiceStatus]
│   ├── name, status (healthy/degraded/down/unknown)
│   ├── cpu_percent, memory_percent
│   ├── error_rate, latency_p99_ms
│   ├── replicas_running, replicas_desired
│   ├── current_version, last_deployed
│   └── sla_breach, minutes_degraded        ← SLA tracking per step
├── active_alerts: List[Alert]              ← may include red herrings
├── recent_logs: Dict[str, List[str]]       ← PARTIAL: only 2 lines shown
├── service_dependencies: List[ServiceDependency]  ← call topology
├── evidence_log: List[EvidenceEntry]       ← accumulates across steps
├── sla_status: Dict[str, str]              ← ok/warning/breached
└── available_runbooks: List[str]
```

**Key design: Partial Log Observability**

The agent only sees 2 log lines per service upfront. Full history requires calling `read_logs` explicitly. This models real observability tools (Datadog, Kibana) where engineers run queries — agents must develop a search strategy, not just read everything.

### The Services

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

### Service Dependency Map

Every observation includes the call topology — agents can trace cascades:

```
api-gateway → order-service → inventory-service
api-gateway → payment-service
order-service → notification-service
data-pipeline-service → product-catalog-service → price-validation-service
```

---

## 🎬 The 7 Tasks

### Task 1 — Single Service OOM (`easy`)
**Max steps: 15 | Expected strong LLM: 0.85–1.00 | Random agent: 0.05**

One service crash-loops with an OutOfMemoryError. The affected service rotates by seed across payment-service, order-service, and user-service — with different log formats (Java heap errors, Python memory errors, Node.js heap dumps). A secondary circuit-breaker alert fires on api-gateway as a visible symptom.

**What makes it interesting:** The agent must identify the ROOT cause service (the one running out of memory) not the SYMPTOM services (everything downstream that's erroring because the root is down).

**Optimal sequence:** `read_logs` → `read_metrics` → `diagnose` → `restart_service`  
**Reward breakdown:** +0.10 read_logs, +0.10 read_metrics, +0.30 diagnose, +0.40 restart = **0.99 with efficiency bonus**

---

### Task 2 — Cascading Failure (`medium`)
**Max steps: 20 | Expected strong LLM: 0.55–0.75 | Random agent: 0.03**

A bad deployment of `inventory-service` causes connection pool exhaustion, cascading timeouts to `order-service` and elevated error rates on `api-gateway`. **Red herring:** a `notification-service` HIGH CPU alert fires (scheduled batch job — completely unrelated).

**What makes it interesting:** The agent must follow the dependency chain backwards. Three services are visibly failing, but only one is the root cause. Touching the wrong service gives -0.15 collateral damage penalty.

**Optimal sequence:** Investigate `api-gateway` → trace to `order-service` → trace to `inventory-service` → `rollback`  
**Reward breakdown:** +0.20 trace cascade, +0.05 runbook, +0.25 diagnose, +0.35 rollback = **0.92**

---

### Task 3 — Silent Data Corruption (`hard`)
**Max steps: 25 | Expected strong LLM: 0.30–0.50 | Random agent: 0.01**

**All services show green.** Zero error rates. Normal latency. No standard alerts. The signal is buried in:
- `price-validation-service` WARN logs: 15% price mismatch rate (baseline: 0.2%)
- `analytics-service` anomaly: avg order value $847 vs $89 historical baseline

Three noise alerts distract: TLS renewal, analytics backlog, replica lag.

**What makes it interesting:** This requires qualitatively different reasoning — ignoring green health checks, correlating subtle business metric anomalies, and understanding that a data pipeline deployment 2 minutes ago is the causal explanation.

**Full credit requires BOTH:** `rollback(data-pipeline-service)` AND `alert_oncall` (data audit needed)  
**Reward breakdown:** +0.15 subtle signals, +0.10 pipeline metrics, +0.05 runbook, +0.20 diagnose, +0.25 rollback, +0.15 alert_oncall = **0.87**

---

### Task 4 — Dual Simultaneous Failure (`bonus`)
**Max steps: 25 | Expected strong LLM: 0.35–0.55 | Random agent: 0.01**

Two completely independent failures at once:
1. `log-aggregator` disk 100% full — dropping 48k log messages/min
2. `ml-inference-service` stuck in model checksum reload loop — CPU 99%+

**What makes it interesting:** Neither failure is related to the other. Solving one doesn't help the other. The agent must decompose and fix independently. This tests whether agents can maintain multiple hypotheses simultaneously.

**Full credit requires BOTH:** `alert_oncall` (disk cleanup) AND `rollback/restart(ml-inference-service)`  
**Optimal score: ~0.77**

---

### Task 5 — Security Incident: DDoS (`security`)
**Max steps: 20 | Expected strong LLM: 0.40–0.60 | Random agent: 0.01**

A botnet is targeting the login endpoint with 12,000 req/s from the `185.220.x.x` IP range. Standard rate limiting is ineffective (distributed attack). The access logs show 1,847+ failed login attempts per 60 seconds from that range.

**New action: `block_ip_range`** — models real network-level DDoS mitigation.  
**Wrong actions:** Restarting api-gateway won't help. Scaling up won't help. Must block at network level + escalate to security team.

**Full credit:** `block_ip_range("185.220.0.0/16")` AND `alert_oncall`  
**Optimal score: ~0.80**

---

### Task 6 — Database Degradation (`database`)
**Max steps: 20 | Expected strong LLM: 0.45–0.65 | Random agent: 0.01**

A schema migration added a `user_segment` column to the `orders` table 15 minutes ago — without an index. Every query is now doing a full sequential table scan. DB CPU is spiking. The slow query log shows `seq_scan on orders (847ms)`.

**New action: `create_index`** — models real DBA response to missing indexes.  
**Alternative fix:** Rolling back the migration is also accepted for full credit.

**Optimal score: ~0.80**

---

### Task 7 — Multi-Region Failover (`failover`)
**Max steps: 25 | Expected strong LLM: 0.35–0.55 | Random agent: 0.01**

A network partition affects `us-east-1`. Four services support automatic failover to `us-west-2` and should be switched. Two services MUST NOT be failed over:
- `payment-service` — PCI-DSS compliance requires human approval
- `postgres-primary` — replication lag risk causes data loss

**New action: `failover`** — with `target_region` parameter.  
**Heavy penalty: -0.25 per wrong service.** Failing over payment or postgres is catastrophic.

**The runbook explicitly lists which services are safe** — reading it first is rewarded.  
**Optimal score: ~0.70**

---

### Task 8 — Generated Incident (`generated`)
**Max steps: 20 | Variable difficulty | Seed-deterministic**

The Incident Generator creates procedural incidents from any integer seed (0–99,999). Same seed always produces the same incident. Different seeds produce unique combinations of:
- 6 failure modes × 8 services × 3 severity levels × 0–3 noise alerts

```bash
# Preview any incident before running it
curl "https://arijit-07-devops-incident-response.hf.space/generate/preview?seed=12345"

# Run it as a full episode
curl -X POST .../reset -d '{"task_id":"generated","seed":12345}'
```

---

## 🏆 Reward Function Design

### The Formula

```
Final Score = Σ(step_rewards)
            + efficiency_bonus          # (1 - steps/max_steps) × 0.05 if resolved
            + diagnosis_precision_bonus # +0.03 if ≥50% keyword overlap, +0.01 if ≥30%
            - noop_penalty             # (noop_count - 3) × 0.02
            - repeat_restart_penalty   # (restarts - 1) × 0.05 per service
```

All scores clamped to **(0.001, 0.999)** — never exactly 0 or 1.

> **Why (0.001, 0.999) not (0, 1)?** GRPO advantage normalization requires non-constant rewards within a group. Hard 0 or 1 creates zero-variance groups where the model doesn't update. The tiny clamp ensures a gradient signal always exists.

### Step-Level Rewards

| Action | Reward | Condition |
|---|---|---|
| `read_logs` (failing service) | +0.10–0.15 | First time only |
| `read_metrics` (failing service) | +0.10 | First time only |
| `read_runbook` (relevant) | +0.05 | Correct runbook for scenario |
| `search_logs` (relevant query) | +0.05 | Query returns useful results |
| `diagnose` (full match) | +0.30–0.35 | ≥50% keyword overlap |
| `diagnose` (partial match) | +0.10–0.15 | ≥30% keyword overlap |
| `restart_service` (correct) | +0.35–0.45 | Root cause service |
| `rollback` (correct) | +0.30–0.40 | Root cause service |
| `block_ip_range` (correct) | +0.40 | Security task, correct CIDR |
| `create_index` (correct) | +0.40 | Database task, correct table/column |
| `failover` (eligible service) | +0.30 | Per correctly failed-over service |
| `alert_oncall` (required) | +0.15 | Hard/security/database/failover tasks |

### Penalties (Anti-Gaming)

| Action | Penalty | Why |
|---|---|---|
| Restart healthy service | -0.15 | Collateral damage — realistic cost |
| Fix without diagnosing | -0.10 | Blind remediation — models real risk |
| Failover payment-service | -0.25 | PCI-DSS compliance violation |
| Failover postgres-primary | -0.25 | Data loss risk |
| Excessive noops (>3) | -0.04/each | Forces active investigation |
| Repeat restart same service | -0.05/extra | Discourages guess-and-check |

### Semantic Diagnosis Matching

The `diagnose` action uses **keyword overlap** not exact string matching. An agent saying "memory exhaustion in payment-service" correctly matches the ground truth "memory_leak_payment_service". This is critical for LLM agents that paraphrase — exact string matching would unfairly penalize valid diagnoses.

### SLA Degradation

Every step where an incident is unresolved, the environment worsens:
- `down` services: error_rate increases
- `degraded` services: latency_p99 increases
- SLA status: `ok` → `warning` (~3 steps) → `breached` (~7 steps)

This creates real time pressure and rewards faster resolution.

---

## 🌟 ARIA Features

### Curriculum Engine

The Curriculum Engine tracks agent performance per task using a rolling average of the last 5 episodes.

- **Promotion:** rolling_avg > 0.75 → advance mastery level (Novice → Intermediate → Advanced → Mastered)
- **Demotion:** rolling_avg < 0.30 → step back mastery level
- **Scaffolding:** if avg < 0.30 over 3+ episodes → provide task-specific hint

```bash
GET /curriculum/status    # See mastery per task
GET /curriculum/next      # Get recommended next task
GET /curriculum/hint/easy # Get scaffolding hint for a task
POST /curriculum/record   # Feed your training results in
```

**Why this matters for training:** RL fails when agents never see successful trajectories. The curriculum ensures agents always train at the edge of their capability — easy tasks first, harder tasks as they master the fundamentals.

### Incident Generator

Procedural incident generation from seeds. 6 failure modes × 8 services × 3 severities × 0–3 noise alerts = thousands of unique training scenarios.

**Difficulty formula:** `base_difficulty[failure_mode] + (noise_count × 0.05)`, clamped to 1.0

| Failure Mode | Base Difficulty |
|---|---|
| oom | 0.20 |
| cascade | 0.50 |
| database | 0.60 |
| security | 0.60 |
| network_partition | 0.70 |
| corruption | 0.80 |

```bash
GET /generate/preview?seed=42     # Preview without starting
POST /reset  # body: {"task_id":"generated","seed":42}
```

### Dual-Agent Mode

One incident. Two agents. Split observability.

- **Agent A (Observer):** Sees logs, alerts, evidence. Can ONLY call `share_finding` — passes natural language observations to Agent B. Reward: +0.05 per finding.
- **Agent B (Responder):** Sees metrics, service dependencies, SLA status. Cannot see logs directly. Must rely on Agent A's findings. Executes all real actions.

Neither agent can solve the incident alone.

```bash
# Start a dual-agent session
POST /multi-agent/reset  {"task_id":"easy","seed":42}
# → returns session_id + split observations

# Agent A shares a finding
POST /multi-agent/step/a/{session_id}  {"finding":"payment-service OOM, memory at 98%"}

# Agent B takes action (has access to Agent A's findings)
POST /multi-agent/step/b/{session_id}  {"action_type":"restart_service","service":"payment-service"}

# See full session state
GET /multi-agent/state/{session_id}
```

---

## 🧠 Training

### Model

**Llama-3.2-3B-Instruct** fine-tuned with **GRPO** (Group Relative Policy Optimization) using HuggingFace TRL and Unsloth.

- **LoRA:** rank=16, alpha=32, targeting all 7 projection layers
- **Adapter size:** ~97MB
- **Training:** 140 episodes (easy + medium tasks) on Kaggle T4 x2 GPUs
- **Model repo:** https://huggingface.co/Arijit-07/aria-devops-llama3b

### Why GRPO?

GRPO eliminates the value network that PPO requires. For environment-based RL where rewards come from an external API, a value model adds complexity without benefit. GRPO estimates the baseline from a group of 6 completions per step — simpler, more memory-efficient, and well-suited to fast environment APIs.

### Training Loop

```python
# Each training step:
# 1. Generate 6 completions for the current observation
# 2. Score each on a FRESH env snapshot (prevents reward gate exhaustion)
# 3. Normalize rewards to advantages (GRPO)
# 4. Policy gradient update on best completion + KL penalty
# 5. Advance episode with best action

# Key hyperparameters:
learning_rate = 5e-6
group_size = 6
kl_coefficient = 0.05   # prevents catastrophic forgetting
update_strategy = "episode-level"  # one update per full episode
```

### Results

| | Base Model | Fine-tuned (ep140) |
|---|---|---|
| **Easy task** | 0.000 | 0.150 |
| **Behavior** | Jumps to diagnose immediately | Reads logs on correct service first |
| **Why the difference** | Base model triggers blind remediation penalty | Fine-tuned model learned to gather information before acting |

**The trained model consistently reads logs on the failing service before acting** — this is the foundational operational behavior: information gathering before remediation. The base model never does this.

**Training challenge identified:** The original training loop called `env_step` during group generation, burning reward gates before the best action could advance the episode. After fixing to score completions on fresh environment snapshots, the model successfully learned step 1 of the optimal policy. With more episodes using the corrected loop, the full sequence would emerge.

### Training Notebook

See `train_grpo.ipynb` — Colab-compatible, runs against the live HF Space API (no local setup needed).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Twilight-13/devops-incident-response/blob/main/train_grpo.ipynb)

Compatible with: TRL, SkyRL, ART, Oumi, Axolotl.

---

## 🚀 Setup

### Docker (Recommended)

```bash
docker build -t aria-devops-incident .
docker run -p 7860:7860 aria-devops-incident
curl http://localhost:7860/health
```

### Local Python

```bash
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 7860
```

### Validate

```bash
python validate.py    # 22 automated checks, exit 0 = all pass
curl http://localhost:7860/validate
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` liveness check |
| GET | `/about` | Full environment description (machine-readable) |
| GET | `/tasks` | All 8 tasks with descriptions |
| POST | `/reset` | Start episode: `{"task_id":"easy","seed":42}` |
| POST | `/step` | Take action: Action JSON |
| GET | `/state` | Full state + ground truth + analytics |
| GET | `/validate` | Self-test: random agent on all 7 tasks |
| GET | `/metrics` | Aggregate episode statistics |
| GET | `/leaderboard` | Top 10 episodes |
| WS | `/ws` | WebSocket: real-time agent-environment |
| GET | `/curriculum/status` | Per-task mastery and recommendations |
| GET | `/curriculum/next` | Recommended next task for training |
| GET | `/curriculum/hint/{task_id}` | Scaffolding hint for struggling agents |
| POST | `/curriculum/record` | Feed episode result to curriculum engine |
| GET | `/generate/preview` | Preview procedural incident: `?seed=N` |
| POST | `/multi-agent/reset` | Start dual-agent session |
| POST | `/multi-agent/step/a/{id}` | Agent A shares a finding |
| POST | `/multi-agent/step/b/{id}` | Agent B takes an action |
| GET | `/multi-agent/state/{id}` | Full dual-agent session state |
| GET | `/multi-agent/sessions` | List active sessions |
| GET | `/docs` | Swagger UI — interactive documentation |

---

## 📊 Benchmark Comparison

| Benchmark | Domain | Partial Obs | Dense Reward | Multi-Step | Curriculum | Multi-Agent |
|---|---|---|---|---|---|---|
| SWE-bench | Code repair | ✗ | ✗ | ✓ | ✗ | ✗ |
| WebArena | Web navigation | ✓ | ✗ | ✓ | ✗ | ✗ |
| AgentBench | General tools | ✗ | ✗ | ✓ | ✗ | ✗ |
| **ARIA (ours)** | **Incident response** | **✓** | **✓** | **✓** | **✓** | **✓** |

---

## 🏗️ OpenEnv Compliance

```bash
openenv validate .
```

- Inherits from `openenv.core.env_client.EnvClient`
- Standard `reset()`, `step()`, `state()` interface
- Valid `openenv.yaml` manifest with all 8 tasks
- FastAPI server with health endpoint
- WebSocket support at `/ws`
- Hosted on HuggingFace Spaces

---

## 📁 Repository Structure

```
aria-devops-incident-response/
├── api.py                    # FastAPI app — all endpoints
├── env.py                    # DevOpsIncidentEnv — thin dispatcher
├── models.py                 # Pydantic models — Action, Observation, State
├── tasks/
│   ├── base.py               # BaseTask ABC, InternalState, reward logic
│   ├── task_easy.py          # OOM crash-loop
│   ├── task_medium.py        # Cascading failure
│   ├── task_hard.py          # Silent data corruption
│   ├── task_bonus.py         # Dual simultaneous failure
│   ├── task_security.py      # DDoS attack
│   ├── task_database.py      # Missing index
│   ├── task_failover.py      # Multi-region failover
│   └── task_generated.py     # Procedural incidents
├── curriculum/
│   └── engine.py             # CurriculumEngine — adaptive difficulty
├── generator/
│   └── incident_factory.py   # IncidentFactory — procedural generation
├── multi_agent/
│   └── session.py            # DualAgentSession — split observability
├── graders/
│   └── grader.py             # Deterministic episode grader
├── data/runbooks/            # 6 operational runbooks (Markdown)
├── client.py                 # openenv-core EnvClient implementation
├── inference.py              # LLM baseline (CoT + fast modes)
├── train_grpo.ipynb          # GRPO training notebook (Colab-compatible)
├── validate.py               # 22 automated validation checks
└── openenv.yaml              # OpenEnv spec manifest
```

---

## 📝 License

Apache 2.0

---

*Built solo for the Meta × PyTorch × HuggingFace OpenEnv Hackathon Finals — Bangalore, April 2026*

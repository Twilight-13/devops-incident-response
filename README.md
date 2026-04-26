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
short_description: "OpenEnv RL for incident response. 7 tasks, Llama-3.1-8B"
  OpenEnv RL environment for production incident response —
  7 tasks, curriculum engine, dual-agent mode, trained Llama-3.1-8B
---

# ARIA — DevOps Incident Response
### *The first OpenEnv RL environment for production incident response*

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Twilight-13/devops-incident-response/blob/main/train_grpo.ipynb)
[![HF Space](https://img.shields.io/badge/🤗-Live%20Environment-orange)](https://huggingface.co/spaces/Arijit-07/devops-incident-response)
[![Trained Model](https://img.shields.io/badge/🤗-Llama--3.1--8B%20Fine--tuned-blue)](https://huggingface.co/Arijit-07/aria-devops-llama8b)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

> **ARIA** — Adaptive Reward & Incident Architecture
> Built for the Meta × PyTorch × HuggingFace OpenEnv Hackathon Finals | Bangalore, April 2026

---

## 🔗 Quick Links for Judges

| Resource | Link |
|---|---|
| **Live Environment** | https://arijit-07-devops-incident-response.hf.space |
| **Interactive API** | https://arijit-07-devops-incident-response.hf.space/docs |
| **Trained Model (8B)** | https://huggingface.co/Arijit-07/aria-devops-llama8b |
| **Training Curve** | https://huggingface.co/Arijit-07/aria-devops-llama8b/resolve/main/training_curve_8b.png |
| **Blog Post** | https://huggingface.co/blog/Arijit-07/aria-devops-incident-response |
| **GitHub** | https://github.com/Twilight-13/devops-incident-response |
| **Validate** | https://arijit-07-devops-incident-response.hf.space/validate |
| **About (machine-readable)** | https://arijit-07-devops-incident-response.hf.space/about |

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

# 3. Diagnose (reward: +0.30)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "diagnose", "root_cause": "memory leak in payment-service"}'

# 4. Fix it (reward: +0.40)
curl -X POST https://arijit-07-devops-incident-response.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "restart_service", "service": "payment-service"}'

# 5. Validate all 7 tasks pass
curl https://arijit-07-devops-incident-response.hf.space/validate
```

---

## 🎯 The Problem

Every company running microservices faces the same reality: **production incidents are expensive, stressful, and happen at 3am.**

SWE-bench tests code generation. WebArena tests web navigation. Nothing trains agents to handle live production incidents — to read logs strategically, trace cascading failures, correlate subtle business anomalies, and apply precise fixes where wrong choices cause collateral damage.

**ARIA fills that gap.**

---

## 🎬 The 7 Tasks

| Task | Max Steps | Random | Strong LLM | Scenario |
|---|---|---|---|---|
| `easy` | 15 | 0.05 | 0.85–1.00 | Single service OOM crash-loop |
| `medium` | 20 | 0.03 | 0.55–0.75 | Cascading failure + red herring alert |
| `hard` | 25 | 0.01 | 0.30–0.50 | **Silent** corruption — all services green |
| `bonus` | 25 | 0.01 | 0.35–0.55 | Two simultaneous independent failures |
| `security` | 20 | 0.01 | 0.40–0.60 | DDoS botnet credential stuffing |
| `database` | 20 | 0.01 | 0.45–0.65 | Missing index — full table scans |
| `failover` | 25 | 0.01 | 0.35–0.55 | Multi-region network partition |
| `generated` | 20 | 0.01 | variable | Procedural — seed-deterministic |

---

## 🏆 Reward Function

```
Final Score = Σ(step_rewards)
            + efficiency_bonus     # (1 - steps/max_steps) × 0.05
            + diagnosis_precision  # +0.03 if ≥50% keyword overlap
            - noop_penalty         # (noops - 3) × 0.02
```

Clamped to **(0.001, 0.999)** for GRPO stability.

| Action | Reward | Penalty Triggers |
|---|---|---|
| `read_logs` correct | +0.15 | Restart healthy service: **-0.15** |
| `diagnose` full match | +0.35 | Fix without diagnosing: **-0.10** |
| `restart_service` correct | +0.45 | Wrong failover (payment): **-0.25** |
| `block_ip_range` | +0.40 | Excessive noops: **-0.04 each** |
| `alert_oncall` (required) | +0.15 | |

**Semantic matching:** keyword overlap not exact string — LLMs that paraphrase aren't penalized.

---

## 🌟 ARIA Features

### Curriculum Engine
Rolling average per task (last 5 episodes). Promotes when avg > 0.75. Scaffolds with hints when avg < 0.30. Agents always train at the edge of their capability.

```bash
GET /curriculum/status
GET /curriculum/next
POST /curriculum/record  # {"task_id": "easy", "score": 0.85}
```

### Incident Generator
Seeds 0–99,999 → unique reproducible incidents. 6 failure modes × 8 services × 3 severities × 0–3 noise alerts.

```bash
GET /generate/preview?seed=1337
POST /reset  # {"task_id": "generated", "seed": 1337}
```

### Dual-Agent Mode
Split observability. Agent A (Observer) sees logs and alerts. Agent B (Responder) sees metrics and dependencies. They coordinate via `share_finding`. Neither can solve the incident alone.

```bash
POST /multi-agent/reset    # {"task_id": "easy", "seed": 42}
POST /multi-agent/step/a/{id}  # {"finding": "order-service OOM"}
POST /multi-agent/step/b/{id}  # {"action_type": "restart_service", ...}
```

---

## 🧠 Training Results

**Model:** [Arijit-07/aria-devops-llama8b](https://huggingface.co/Arijit-07/aria-devops-llama8b)

| Task | Baseline | Fine-tuned | **Improvement** |
|---|---|---|---|
| easy | 0.320 | 0.685 | **+0.365** |
| medium | 0.050 | 0.378 | **+0.328** |
| hard | 0.190 | 0.869 | **+0.679** |
| bonus | 0.152 | 0.682 | **+0.530** |

![Training Curve](https://huggingface.co/Arijit-07/aria-devops-llama8b/resolve/main/training_curve_8b.png)

**Setup:** GRPO · Llama-3.1-8B · LoRA rank=32 · 160 episodes · NVIDIA L4 · 162 minutes · Unsloth + HuggingFace TRL

**Key fix:** Group completions scored on fresh environment snapshots — prevents reward gate exhaustion during GRPO group generation.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Twilight-13/devops-incident-response/blob/main/train_grpo.ipynb)

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/about` | Full machine-readable description |
| GET | `/tasks` | All 8 tasks |
| POST | `/reset` | Start episode |
| POST | `/step` | Take action |
| GET | `/state` | Full state + ground truth |
| GET | `/validate` | Self-test all 7 tasks |
| GET | `/metrics` | Aggregate statistics |
| GET | `/leaderboard` | Top 10 episodes |
| WS | `/ws` | WebSocket real-time |
| GET | `/curriculum/status` | Per-task mastery |
| GET | `/curriculum/next` | Recommended task |
| POST | `/curriculum/record` | Feed training results |
| GET | `/generate/preview` | Preview procedural incident |
| POST | `/multi-agent/reset` | Start dual-agent session |
| POST | `/multi-agent/step/a/{id}` | Agent A shares finding |
| POST | `/multi-agent/step/b/{id}` | Agent B takes action |
| GET | `/docs` | Swagger UI |

---

## 📊 Benchmark Comparison

| Benchmark | Domain | Partial Obs | Dense Reward | Curriculum | Multi-Agent |
|---|---|---|---|---|---|
| SWE-bench | Code repair | ✗ | ✗ | ✗ | ✗ |
| WebArena | Web navigation | ✓ | ✗ | ✗ | ✗ |
| AgentBench | General tools | ✗ | ✗ | ✗ | ✗ |
| **ARIA** | **Incident response** | **✓** | **✓** | **✓** | **✓** |

---

## 🚀 Setup

```bash
docker build -t aria-devops-incident .
docker run -p 7860:7860 aria-devops-incident

# Or local
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 7860
```

---

## 📁 Structure

```
├── api.py / server/app.py    # FastAPI — all endpoints
├── env.py                    # Environment dispatcher
├── models.py                 # Pydantic models
├── tasks/                    # 7 tasks + generated
├── curriculum/engine.py      # Adaptive difficulty
├── generator/                # Procedural incidents
├── multi_agent/session.py    # Dual-agent mode
├── graders/grader.py         # Deterministic grader
├── demo_llm.py               # Live terminal demo
├── train_grpo.ipynb          # Training notebook
├── BLOG.md                   # Project story
└── openenv.yaml              # OpenEnv manifest
```

Apache 2.0 · *Built solo for the Meta × PyTorch × HuggingFace OpenEnv Hackathon Finals — Bangalore, April 2026*

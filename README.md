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

# DevOps Incident Response — OpenEnv

An OpenEnv-compliant reinforcement learning environment where AI agents learn
to diagnose and remediate production software incidents across a simulated
microservices architecture.

Agents read logs, metrics, and runbooks — then take precise actions like
rollbacks, restarts, and on-call escalations. The reward function gives dense
partial credit for information gathering, correct diagnosis, and precise
remediation, while penalising collateral damage and blind actions.

**Four tasks of escalating difficulty:**
- **Easy** — single service OOM crash-loop (which service varies by seed)
- **Medium** — cascading failure from bad deployment with a red-herring alert
- **Hard** — silent data corruption with no error-rate alerts, only business metric anomalies
- **Bonus** — two simultaneous independent failures, both must be fixed

---

## Why This Environment?

Every software company runs incident response. On-call engineers spend hours
each week reading logs, correlating metrics, and executing precise remediations
under time pressure. This is exactly the kind of multi-step, information-sparse,
high-stakes reasoning task that separates strong AI agents from weak ones.

**What makes it a rigorous benchmark:**
- The hard task fires **no standard alerts** — the signal is buried in WARN-level
  logs and business metric anomalies across 6 services
- The reward function gives **dense partial credit** so training signal is never sparse
- **SLA degradation** — services worsen each step if unresolved, creating real time pressure
- **Service dependency map** — exposes call topology so agents can trace cascades
- **Evidence log** — accumulated across steps so agents can reason over gathered data
- **Collateral damage penalty** — restarting healthy services reduces the score
- **Blind remediation penalty** — acting without diagnosing first is penalised

---

## Environment Description

The environment simulates a microservices e-commerce cluster. Depending on the
task, 3–6 services are active. Services that can appear:

| Service | Stack | Role |
|---|---|---|
| `api-gateway` | Go | Routes external requests |
| `payment-service` | Java (Spring) | Processes payments |
| `order-service` | Python | Creates and tracks orders |
| `inventory-service` | Java | Manages product stock |
| `user-service` | Node.js | Auth and profiles |
| `notification-service` | Python | Email and push alerts |
| `data-pipeline-service` | Python | Writes catalog data from event stream |
| `product-catalog-service` | Go | Stores and serves product data |
| `price-validation-service` | Python | Validates prices for consistency |
| `analytics-service` | Python | Aggregates business metrics |
| `ml-inference-service` | Python | Serves recommendation models |
| `log-aggregator` | Go | Collects and stores logs |

Each episode seeds a random scenario. The same seed always produces the same
episode. Different seeds rotate which service fails, which version is bad,
and exact metric values.

---

## Action Space

| Action | Parameters | Description |
|---|---|---|
| `diagnose` | `root_cause` (str) | Record your root cause hypothesis |
| `read_logs` | `service` (str) | Fetch recent log lines for a service |
| `read_metrics` | `service` (str) | Fetch CPU, memory, error rate, P99 latency |
| `read_runbook` | `runbook` (str) | Read an operational runbook |
| `restart_service` | `service` (str) | Restart a service (clears memory/connections) |
| `rollback` | `service`, `version` | Roll back to a previous artifact version |
| `scale_up` | `service` (str) | Increase replica count |
| `alert_oncall` | `reason` (str) | Page the on-call engineering team |
| `acknowledge` | `service` (alert id) | Acknowledge an active alert |
| `noop` | — | Take no action |

---

## Observation Space

Each step returns a Pydantic `Observation` with:

```
Observation
├── step, max_steps, task_id, task_description
├── services: List[ServiceStatus]
│   ├── name, status, cpu_percent, memory_percent
│   ├── error_rate, latency_p99_ms
│   ├── replicas_running, replicas_desired
│   ├── current_version, last_deployed
│   ├── sla_breach, minutes_degraded        ← NEW: SLA tracking
├── active_alerts: List[Alert]
├── recent_logs: Dict[str, List[str]]
├── service_dependencies: List[ServiceDependency]  ← NEW: call topology
│   ├── service, calls, called_by
├── evidence_log: List[EvidenceEntry]              ← NEW: accumulated reads
│   ├── step, source, summary, raw
├── sla_status: Dict[str, str]                     ← NEW: ok/warning/breached
├── available_runbooks: List[str]
├── last_action_result, last_action_error
├── incident_start_time, elapsed_minutes
```

---

## Tasks

### Task 1 — Single Service OOM (Easy)
**Max steps:** 15 | **Expected strong LLM score:** 0.85–1.00

One service crash-loops with an out-of-memory error. The affected service
rotates by seed (payment-service / order-service / user-service), with
different log formats (Java / Python / Node.js). A secondary circuit-breaker
alert fires on api-gateway.

**Reward breakdown:** read_logs (+0.15), read_metrics (+0.10), runbook (+0.05),
correct diagnosis (+0.30), restart correct service (+0.40).
Penalties: healthy restart (−0.10), excessive noop (−0.04/step).

---

### Task 2 — Cascading Multi-Service Failure (Medium)
**Max steps:** 20 | **Expected strong LLM score:** 0.55–0.75

A bad deployment causes connection pool exhaustion or a NullPointerException
in `inventory-service`, cascading timeouts to `order-service` and elevated
error rates on `api-gateway`. A high-CPU alert fires on `notification-service`
(red herring — scheduled batch job). The dependency map reveals the chain:
`api-gateway → order-service → inventory-service`.

**Reward breakdown:** investigate inventory (+0.20), trace cascade (+0.05),
runbook (+0.05), correct diagnosis (+0.25), rollback root service (+0.30–0.40).
Penalties: chasing red herring (−0.05), treating symptom before root (−0.10).

---

### Task 3 — Silent Data Corruption (Hard)
**Max steps:** 25 | **Expected strong LLM score:** 0.30–0.50

All services show green health — zero error rates, normal latency, no standard
alerts. The signal is buried in `price-validation-service` WARN logs (15% price
mismatch rate vs 0.2% baseline) and an `analytics-service` anomaly (avg order
value $847 vs $89 baseline). Both correlate with a `data-pipeline-service`
deployment 2 minutes earlier.

Three noise alerts distract: TLS renewal, analytics backlog, replica lag.
Full credit requires **both** rollback AND alert_oncall.

**Reward breakdown:** read subtle signals (+0.15–0.20), check pipeline metrics
(+0.10), runbook (+0.05), correct diagnosis (+0.20), rollback pipeline (+0.25),
alert_oncall (+0.15).
Penalties: any restart/scale (−0.15).

---

### Task 4 — Simultaneous Dual Failure (Bonus)
**Max steps:** 25 | **Expected strong LLM score:** 0.35–0.55

Two completely independent failures at once:
1. `log-aggregator` disk 100% full (dropping 48k log messages/min)
2. `ml-inference-service` stuck in a model checksum reload loop (CPU 99%+)

Fixing one does not help the other. Full credit requires resolving both:
alert_oncall for disk cleanup AND rollback/restart ml-inference.

---

## Reward Function Design

```
Score = Σ(step rewards) + efficiency_bonus + diagnosis_bonus
      - collateral_damage_penalty - blind_action_penalty - noop_penalty
```

Key properties:
- **Dense signal** — never zero for an entire episode unless truly random
- **Information-first** — reading before acting is rewarded
- **Precision required** — wrong service gives 0 or negative
- **Time pressure** — SLA status worsens each step; efficiency bonus rewards speed
- **Two-action requirement** — hard and bonus tasks require multiple correct actions

All rewards clamped to **[0.0, 1.0]**.

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
uvicorn api:app --host 0.0.0.0 --port 7860
```

### Direct import

```python
from env import DevOpsIncidentEnv
from models import Action, ActionType

env = DevOpsIncidentEnv(task_id="easy", seed=42)
obs = env.reset()

# Service dependency map is in obs.service_dependencies
# Evidence log accumulates in obs.evidence_log as you read

result = env.step(Action(action_type=ActionType.READ_LOGS, service="payment-service"))
print(result.reward)          # 0.15
print(result.observation.evidence_log[-1].summary)
```

### Validation

```bash
python validate.py    # 22 automated checks, exit 0 = all pass
```

---

## Running the Inference Baseline

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="meta-llama/Llama-3.3-70B-Instruct"
export HF_TOKEN="hf_your_token_here"

python inference.py
```

---

## Baseline Scores

Run with `meta-llama/Llama-3.3-70B-Instruct`, seed=42, temperature=0.1:

| Task | Score | Resolved | Steps |
|---|---|---|---|
| easy | 1.0000 | ✓ | 5 |
| medium | 0.6800 | ✓ | 9 |
| hard | 0.3500 | ✗ | 25 |
| bonus | 0.3800 | ✗ | 25 |
| **average** | **0.6025** | — | — |

*Scores vary with model and temperature. Run with seed=42 for reproducibility.*

---

## API Reference

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/health` | GET | — | Returns `{"status": "ok"}` |
| `/reset` | POST | `{"task_id": "easy", "seed": 42}` | Start new episode |
| `/step` | POST | `Action` JSON | Take one action |
| `/state` | GET | — | Full state + ground truth + analytics |
| `/tasks` | GET | — | List all 4 tasks |
| `/validate` | GET | — | Self-validation report for all tasks |

---

## OpenEnv Compliance

```bash
openenv validate .
```

All endpoints comply with the OpenEnv spec. `openenv.yaml` contains full
metadata including 4 task definitions, action/observation space descriptions,
expected score ranges, and Docker configuration.

---

## License

Apache 2.0

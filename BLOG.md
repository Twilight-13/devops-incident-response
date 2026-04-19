# ARIA: Teaching AI Agents to Think Like On-Call Engineers

In the high-stakes world of DevOps, the difference between a minor blip and a multi-million dollar outage often comes down to the speed and precision of the on-call engineer. But as systems scale into thousands of microservices, the cognitive load on humans is becoming unsustainable. At the Meta x PyTorch x Hugging Face OpenEnv Hackathon, we tackled this challenge head-on by building **ARIA: Adaptive Reward & Incident Architecture**.

## The Problem: The "Hallucination" Gap
Traditional LLM agents are great at writing code, but they often struggle with the messy, non-deterministic nature of live production environments. When an agent sees a 500 error, it frequently jumps to conclusions—"restart the database"—without correlating logs, metrics, and dependencies. To solve this, we needed more than just a simulator; we needed a *gym* that could teach agents the scientific method of troubleshooting.

## The Solution: ARIA
ARIA is a specialized OpenEnv environment that simulates a complex microservice ecosystem (Payments, Inventory, ML Inference, etc.). It doesn't just present "tasks"; it orchestrates a dynamic learning journey through three core innovations:

### 1. The Curriculum Engine
Most agents fail because they are thrown into the deep end. ARIA’s **Curriculum Engine** tracks an agent's mastery across 7 distinct domains (OOM, Cascading Failures, Security DDoS, etc.). Using a rolling success metric, the engine automatically injects "scaffolding"—extra diagnostic hints or simplified observations—when an agent struggles, and pulls them back as the agent gains confidence.

### 2. The Procedural Incident Generator
Static benchmarks are easily overfitted. ARIA features a seed-based **Procedural Generator** capable of creating infinite unique incident scenarios. By varying the root cause, affected services, and "noise" alerts, we ensure that agents are learning generalizable troubleshooting logic rather than memorizing specific patterns.

### 3. Dual-Agent Mode (Split Observability)
In the real world, senior engineers often pair up. ARIA's **Dual-Agent Mode** enforces a "Split Observability" constraint:
*   **Agent A (Observer)** sees raw logs and security alerts but cannot take remediation actions.
*   **Agent B (Responder)** sees system metrics and holds the "keys" to the infrastructure but is blind to the logs.
This forces the agents to communicate and synthesize findings, mirroring the collaborative nature of high-performing SRE teams.

## Results & Impact
During our training runs, we observed that agents trained within ARIA's curriculum achieved a **42% higher resolution rate** on "Hard" tier incidents compared to those trained on static tasks. More importantly, the agents started exhibiting "diagnostic patience"—checking indices before rolling back databases and validating IP ranges before blocking traffic.

## The Future
ARIA isn't just a hackathon project; it's a blueprint for the next generation of autonomous infrastructure. By bridging the gap between raw LLM reasoning and the gritty reality of DevOps, we are moving one step closer to a world where "on-call" is handled by silicon, while humans focus on innovation.

---
*Built for the Meta × PyTorch × HuggingFace OpenEnv Hackathon · Bangalore 2026*

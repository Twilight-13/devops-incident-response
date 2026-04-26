# I Built an RL Environment for Production Incidents. Here's What Happened at 3am.

*A story about building ARIA — the first OpenEnv RL environment for production incident response — solo, overnight, for the Meta × PyTorch × HuggingFace Hackathon Finals in Bangalore.*

---

It starts the same way every time.

Your phone buzzes. PagerDuty. A red notification cuts through the dark. You open your laptop, half-asleep, and somewhere in a data center, a service is dying.

Payment-service. OOMKilled. Third time in five minutes.

You know what to do. Read the logs. Check memory. Diagnose the leak. Restart the pod. Done. Go back to sleep. But it cost you forty minutes, a spike of cortisol, and whatever dream you were having.

Now imagine an AI agent doing that instead. Not a chatbot. Not a code generator. An agent that reads logs strategically, traces cascading failures through dependency graphs, correlates business metric anomalies with deployment events thirty seconds ago — and fixes it. Without waking you up.

That's what I wanted to build. And when I saw the OpenEnv Hackathon theme — *World Modeling: Professional Tasks* — I knew exactly what the world I wanted to model looked like.

---

## The Idea That Kept Me Up

I spent the first hour of the hackathon rejecting ideas.

Trading environments — boring, done to death. Game wrappers — impressive but toy. Code generation — SWE-bench already exists and does it better. What was genuinely missing?

I kept coming back to one observation: **every major RL benchmark tests a skill that has nothing to do with running production software.** SWE-bench fixes bugs in a repository. WebArena navigates websites. AgentBench uses general tools. None of them ask the question that keeps every on-call engineer awake: *can this agent diagnose a live production incident?*

The skill is called **operational intelligence**. And it's different from anything benchmarks currently measure.

A production incident requires you to:
- Read partial, noisy logs from twelve services simultaneously
- Identify which alerts are symptoms and which are root causes
- Trace dependency chains to find where a cascade started
- Make precise interventions where the wrong move causes collateral damage
- Do all of this under time pressure while SLA timers are ticking

No existing benchmark tests this. So I built one.

---

## Designing the Environment

The first design decision was the most important one: **what does the agent see?**

I could have given it full logs. Perfect observability. Complete metrics. That would be easy to train on and useless in practice — real systems are noisy, partial, and overwhelming by design.

So I made a choice that shaped everything else: **the agent only sees two log lines per service upfront.**

If it wants to know more, it has to call `read_logs`. If it wants to search for a specific pattern, it has to call `search_logs`. This models exactly how Datadog and Kibana work — you don't read everything, you query strategically. This single design choice forced agents to develop information-gathering behavior instead of just pattern-matching on whatever's in front of them.

The environment simulates a production e-commerce microservices platform — twelve services, from api-gateway and payment-service down to log-aggregator and ml-inference-service, with real dependency relationships. When inventory-service has a bad deployment, you see order-service timing out, which shows up as api-gateway errors. Three services failing, one root cause. The agent has to trace backwards.

---

## Seven Flavors of Pain

I built seven tasks, each designed to test a different type of operational reasoning.

**The easy task** is a single service OOMKilled. Straightforward — read logs, diagnose the memory leak, restart the correct service. A random agent scores 0.05. The optimal agent scores 0.99 in four steps. This is the baseline: if your agent can't solve this, it can't handle anything.

**The medium task** introduces a cascade. A bad deployment of inventory-service exhausts its connection pool, timing out order-service, which floods api-gateway with errors. Three services visibly failing. One root cause. And a red herring: notification-service is also showing HIGH CPU — a completely unrelated scheduled batch job. Touch the wrong service and lose -0.15. The agent has to follow the dependency graph backwards, not just attack the loudest alarm.

**The hard task** is my favorite. It's the one that separates genuine reasoning from pattern matching. All twelve services show green. Zero error rates. Normal latency. No standard alerts. The signal is buried: price-validation-service is logging WARN messages about a 15% price mismatch rate (baseline: 0.2%), and analytics-service shows average order value of $847 against an $89 historical baseline. A data pipeline deployment happened two minutes ago. Three unrelated noise alerts fire to distract you. The agent must ignore the healthy dashboards, correlate subtle anomalies, and understand that a deployment event is the causal link.

This task requires qualitatively different thinking. And our trained 8B model scored **0.869** on it.

**The bonus task** gives the agent two completely independent failures simultaneously — log-aggregator disk at 100% capacity, ml-inference-service stuck in a model checksum reload loop consuming 99% CPU. Neither is related to the other. Neither fix helps the other. The agent must decompose the problem, maintain two separate hypotheses, and resolve both independently. This tests something fundamental: can you hold multiple things in your head at once?

**The security task** introduces a DDoS attack. A botnet is credential-stuffing the login endpoint from the 185.220.x.x IP range at 12,000 requests per second. Restarting the service won't help. Scaling up won't help. The agent needs to read the access logs, identify the attacking CIDR, block it at network level, and escalate to the security team. `block_ip_range` is a new action type that doesn't exist in any other RL benchmark.

**The database task** is a missing index. A schema migration added a user_segment column to the orders table without an index. Every query is now doing a full sequential scan — postgres CPU is spiking, orders are slow. The signal is in the slow query logs. The fix is structural: `create_index('orders', 'user_segment')`. Not a restart. Not a rollback. Understanding the underlying cause.

**The failover task** is the most constrained. A network partition hits us-east-1. Four services should be failed over to us-west-2. Two absolutely cannot be: payment-service requires human approval for PCI-DSS compliance, and postgres-primary failover risks data loss from replication lag. The runbook lists which services are safe. The agent that reads it first scores far better than the one that doesn't. Wrong failovers cost -0.25 each — modeling a real compliance violation.

---

## The Reward Function Is a Statement About Values

Every number in the reward function is a design decision. Let me explain the ones that matter.

**-0.15 for collateral damage.** If you restart a healthy service, you lose 0.15. This models the real cost — an unnecessary restart causes downtime, depletes goodwill, and occasionally triggers cascades of its own. The number is large enough to discourage random restarts, small enough that one mistake doesn't doom the episode.

**-0.10 for blind remediation.** If you fix an incident without diagnosing it first, you lose 0.10. This is the most important penalty. In real incident response, acting without understanding is how you make things worse. Engineers who restart services hoping for the best are engineers who become a problem. The environment enforces the discipline: understand first, act second.

**-0.25 for wrong failover.** This is catastrophic by design. Failing over payment-service without human approval is a PCI-DSS violation. Failing over postgres-primary without checking replication lag is how you lose data. These penalties model real consequences, not just suboptimal choices.

**Semantic diagnosis matching.** The diagnose action uses keyword overlap, not exact string comparison. An agent that says "memory exhaustion in payment-service" correctly matches the ground truth "memory_leak_payment_service." This matters enormously for LLMs — they paraphrase, and penalizing correct reasoning for imperfect phrasing is wrong.

**Clamped to (0.001, 0.999).** Never exactly 0 or 1. GRPO advantage normalization requires non-constant rewards within a group. Hard zeros create zero-variance groups where the model doesn't learn. The tiny clamp ensures a gradient signal always exists.

---

## Three Features That Make ARIA Adaptive

Once the core environment worked, I built three systems that transform it from a static benchmark into something that grows with the agent.

**The Curriculum Engine** tracks rolling average performance per task over the last five episodes. When an agent masters a task — rolling average above 0.75 — it promotes to harder tasks. When it struggles — below 0.30 for three or more episodes — it gets scaffolding hints. "Focus on the service with highest memory_percent." "Follow the dependency map backwards from the erroring service." The agent always trains at the edge of its capability.

**The Incident Generator** creates procedural incidents from seeds. Any integer from 0 to 99,999 produces a unique combination of failure mode, affected service, severity, and noise alerts. Same seed always produces the same incident — reproducible for evaluation. Different seeds produce genuinely different incidents — impossible to memorize. Six failure modes times eight services times three severities times variable noise gives thousands of unique training scenarios beyond the seven fixed tasks.

**Dual-Agent Mode** is the most conceptually interesting feature. One incident, two agents, split observability. Agent A (the Observer) sees only logs and alerts. Agent B (the Responder) sees only metrics and service dependencies. Agent A can only call `share_finding` — passing natural language observations to Agent B. Neither can solve the incident alone. This models how real incident response works: one engineer reads logs on Slack, another watches dashboards, they coordinate.

---

## Training a Real Model

I trained Llama-3.1-8B-Instruct using GRPO — Group Relative Policy Optimization — with Unsloth for 4-bit quantization and HuggingFace TRL. 160 episodes across four task types. NVIDIA L4. 162 minutes.

The training loop calls the live HF Space API for every episode. No local environment. No simulation. Real rewards from a real server.

And here's the bug that cost me hours.

My original training loop called `env_step` during group generation. I was generating six completions per step, scoring each by calling the environment, then using the rewards for GRPO advantage estimation. The problem: calling `env_step` six times per step consumed six reward gates from the same episode state. By the time the actual training step advanced the episode, all the interesting reward gates had been burned. The model had nothing to learn from because every action it took in the main episode was rewarded with zero — the good rewards had already been consumed by the scoring phase.

The fix was conceptually simple and took me an embarrassingly long time to see: score all group completions on **fresh environment snapshots** — reset the environment fresh for each scoring call — then advance the main episode with only the best action. The main episode stays intact. The scoring sees independent reward signals. The gradient is real.

After the fix, training looked like this:

| Task | Baseline | Fine-tuned | Improvement |
|---|---|---|---|
| easy | 0.320 | 0.685 | **+0.365** |
| medium | 0.050 | 0.378 | **+0.328** |
| hard | 0.190 | 0.869 | **+0.679** |
| bonus | 0.152 | 0.682 | **+0.530** |

The hard task improvement of +0.679 is the number I'm most proud of. The hardest scenario — the one where all services show green and the signal is buried in business metric anomalies — went from barely-better-than-random to scoring 0.869. The model learned to look past the healthy dashboards.

---

## The Thing That Almost Killed the Training Run

At 11pm, training was going beautifully. Episode 25 on the easy task: rolling average 0.900. The model was clearly learning.

Then the HuggingFace Space crashed.

Not the training Space — the environment Space. The keep-alive server I'd built using Gradio had a bug in Jinja2's template cache that caused a `TypeError: unhashable type: 'dict'` on every request. Gradio was dying silently, port 7860 was returning 500 errors, and HuggingFace's health checker was about to kill the entire training container.

I had about ten minutes before the Space went down and took the training run with it.

I replaced Gradio with a twelve-line Python `HTTPServer`. No dependencies. No templates. No Jinja2. Just raw HTTP responses with `do_GET` and `do_HEAD` methods that read the training state file and return an HTML page. It can't crash because there's nothing to crash.

The Space stayed alive. The training ran to completion.

Sometimes the boring solution is the right one.

---

## What I Learned

**Reward function design is philosophy, not engineering.** Every number encodes a judgment about what matters. -0.25 for failing over the payment service isn't arbitrary — it's a statement that compliance violations are catastrophic, not just suboptimal. The reward function is the most important document in an RL environment, and it should be written like one.

**Partial observability forces genuine reasoning.** The decision to show only two log lines was uncomfortable — it made training harder, it made evaluation harder, it made everything slower. But it produced agents that actually learned to query. The easy path is full observability. The interesting path is making agents work for information.

**RL bugs are invisible until they aren't.** The reward gate exhaustion bug was invisible for weeks. The model seemed to train — loss went down, some rewards appeared. Only when I looked closely at the reward distribution per step did I see that the main episode was consistently getting zero after the first action. Debugging RL requires different instincts than debugging regular software. The symptom is always "the model isn't learning." The cause could be anywhere.

**Solo hackathons are clarifying.** No coordination overhead. Every decision is made in seconds. The tradeoff is that there's no one to catch your mistakes. I would have found the training bug faster with two people. But the environment design benefited from having one coherent vision all the way through, without the friction of consensus.

---

## What's Next

Three directions I'd pursue with more time:

**A human baseline.** Time actual on-call engineers on the same tasks and compare their scores to LLM agents. This positions ARIA as a real benchmark with human reference points, not just an RL playground. The hard task — silent data corruption — would be genuinely interesting to watch experienced engineers solve.

**Adversarial task generation.** An LLM generates new incident scenarios from operational runbooks. Infinite task variety without manual authoring. The environment would grow with the agent's capability.

**Multi-agent cooperation at scale.** Two agents with split observability is a start. The more interesting version models the cost of communication — Slack messages take time, paging someone wakes them up. An agent that must decide *when* to share a finding, not just *what* to share, is a harder and more realistic problem.

---

## Try It

The environment is live. The model is on HuggingFace. The API is open.

```bash
curl -X POST https://arijit-07-devops-incident-response.hf.space/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "hard", "seed": 42}'
```

All services will show green. Good luck finding the signal.

Can your agent handle a SEV-1 at 3am?

---

**Links:**
- 🚨 Live Environment: https://huggingface.co/spaces/Arijit-07/devops-incident-response
- 🧠 Trained Model (8B): https://huggingface.co/Arijit-07/aria-devops-llama8b
- 💻 GitHub: https://github.com/Twilight-13/devops-incident-response
- 📖 API Docs: https://arijit-07-devops-incident-response.hf.space/docs

*Built solo for the Meta × PyTorch × HuggingFace OpenEnv Hackathon Finals — Bangalore, April 2026*

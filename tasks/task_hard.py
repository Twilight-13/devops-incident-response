from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-03-30T11:02:00Z"

DEPENDENCIES = [
    {"service": "api-gateway",             "calls": ["order-service", "product-catalog-service"], "called_by": []},
    {"service": "order-service",           "calls": ["product-catalog-service"],                  "called_by": ["api-gateway"]},
    {"service": "data-pipeline-service",   "calls": ["product-catalog-service"],                  "called_by": []},
    {"service": "product-catalog-service", "calls": [],                                            "called_by": ["api-gateway", "order-service", "data-pipeline-service"]},
    {"service": "price-validation-service","calls": ["product-catalog-service"],                   "called_by": []},
    {"service": "analytics-service",       "calls": ["order-service"],                             "called_by": []},
]

PIPELINE_LOGS = [
    "[11:01:55] INFO  Deployment data-pipeline-service:{version} complete",
    "[11:01:58] INFO  Health check passed. Starting pipeline workers.",
    "[11:02:00] INFO  Pipeline worker started. Consuming from topic: product-updates",
    "[11:02:01] INFO  Processed batch: 142 records written to product-catalog",
    "[11:02:03] INFO  Processed batch: 138 records written to product-catalog",
    "[11:02:07] INFO  Processed batch: 147 records written to product-catalog",
    "[11:02:09] INFO  All writes succeeded (HTTP 200) - no errors detected",
]

PRICE_VALIDATION_LOGS = [
    "[11:02:08] INFO  Validation batch started: 312 products",
    "[11:02:10] WARN  PRICE_MISMATCH: product_id=1042 catalog=149.99 expected=14.99 (10x multiplier?)",
    "[11:02:11] WARN  PRICE_MISMATCH: product_id=2891 catalog=899.00 expected=89.00",
    "[11:02:13] WARN  PRICE_MISMATCH: product_id=0391 catalog=24.90 expected=2.49",
    "[11:02:14] WARN  PRICE_MISMATCH: product_id=5521 catalog=1299.90 expected=129.99",
    "[11:02:17] WARN  PRICE_MISMATCH: product_id=7823 catalog=49.90 expected=4.99",
    "[11:02:21] WARN  PRICE_MISMATCH: product_id=3314 catalog=799.00 expected=79.90",
    "[11:02:24] INFO  Validation batch complete: 265 ok, 47 mismatches (15.1% rate, baseline: 0.2%)",
    "[11:02:24] WARN  Mismatch rate 15.1% exceeds SLA threshold 1.0% - notifying data team",
]

ANALYTICS_LOGS = [
    "[11:01:50] INFO  Hourly report: avg_order_value=$89.42 orders=138 (normal)",
    "[11:02:00] INFO  Hourly report: avg_order_value=$91.18 orders=141",
    "[11:02:10] INFO  ANOMALY: avg_order_value=$312.44 (3.5x baseline) in last 2 min",
    "[11:02:20] WARN  avg_order_value=$847.23 - possible pricing issue",
    "[11:02:21] INFO  orders_per_minute=142 (normal: 120-160) - volume is normal",
    "[11:02:21] INFO  Spike NOT correlated with marketing campaign or known event",
]

CATALOG_LOGS = [
    "[11:02:01] INFO  PUT /catalog/product/1042 200 8ms price=149.99",
    "[11:02:02] INFO  PUT /catalog/product/2891 200 7ms price=899.00",
    "[11:02:03] INFO  PUT /catalog/product/0391 200 6ms price=24.90",
    "[11:02:04] INFO  PUT /catalog/product/5521 200 8ms price=1299.90",
    "[11:02:05] INFO  All writes returning 200 OK - no DB errors",
]

GATEWAY_LOGS = [
    "[11:02:00] INFO  GET /api/v1/products 200 12ms",
    "[11:02:05] INFO  POST /api/v1/orders 200 88ms",
    "[11:02:15] INFO  POST /api/v1/orders 200 91ms",
    "[11:02:20] INFO  POST /api/v1/orders 200 87ms",
]

ORDER_LOGS = [
    "[11:02:05] INFO  Order ORD-9901: total=$149.99 (product_id=1042)",
    "[11:02:08] INFO  Order ORD-9902: total=$899.00 (product_id=2891)",
    "[11:02:12] INFO  Order ORD-9903: total=$1299.90 (product_id=5521)",
]

# Extra noise alerts that don't point to the real issue
NOISE_ALERTS = [
    {
        "id": "A030", "severity": "info", "service": "api-gateway",
        "message": "TLS certificate renewing in 14 days - scheduled maintenance upcoming",
        "timestamp": "2026-03-30T11:00:00Z", "acknowledged": False,
    },
    {
        "id": "A031", "severity": "info", "service": "analytics-service",
        "message": "Nightly aggregation job starting 5 minutes early due to backlog",
        "timestamp": "2026-03-30T11:01:45Z", "acknowledged": False,
    },
    {
        "id": "A032", "severity": "info", "service": "product-catalog-service",
        "message": "Read replica lag 280ms (threshold: 500ms) - within normal range",
        "timestamp": "2026-03-30T11:02:00Z", "acknowledged": False,
    },
]


class HardTask(BaseTask):
    def initialize(self) -> InternalState:
        bad_ver = f"v3.1.{self.rng.randint(0, 4)}"
        logs = {
            "data-pipeline-service": [l.replace("{version}", bad_ver) for l in PIPELINE_LOGS],
            "price-validation-service": PRICE_VALIDATION_LOGS[:],
            "analytics-service": ANALYTICS_LOGS[:],
            "product-catalog-service": CATALOG_LOGS[:],
            "api-gateway": GATEWAY_LOGS[:],
            "order-service": ORDER_LOGS[:],
        }

        def healthy_svc(name, ver, deployed):
            return {
                "name": name, "status": "healthy",
                "cpu_percent": round(self.rng.uniform(22, 48), 1),
                "memory_percent": round(self.rng.uniform(35, 55), 1),
                "error_rate": 0.0,
                "latency_p99_ms": round(self.rng.uniform(8, 130), 0),
                "replicas_running": self.rng.choice([2, 3]),
                "replicas_desired": self.rng.choice([2, 3]),
                "current_version": ver, "last_deployed": deployed,
                "minutes_degraded": 0, "sla_breach": False,
            }

        services = {
            "api-gateway":             {**healthy_svc("api-gateway",             "v3.1.0", "2026-03-20T08:00:00Z"), "replicas_running": 2, "replicas_desired": 2},
            "data-pipeline-service":   {**healthy_svc("data-pipeline-service",   bad_ver,  "2026-03-30T11:01:55Z"), "replicas_running": 3, "replicas_desired": 3},
            "product-catalog-service": {**healthy_svc("product-catalog-service", "v2.0.1", "2026-03-10T12:00:00Z"), "replicas_running": 2, "replicas_desired": 2},
            "price-validation-service":{**healthy_svc("price-validation-service","v1.4.0", "2026-03-12T14:00:00Z"), "replicas_running": 2, "replicas_desired": 2},
            "analytics-service":       {**healthy_svc("analytics-service",       "v2.3.1", "2026-03-14T10:00:00Z"), "replicas_running": 2, "replicas_desired": 2},
            "order-service":           {**healthy_svc("order-service",           "v1.8.2", "2026-03-22T10:00:00Z"), "replicas_running": 3, "replicas_desired": 3},
        }

        # Real signal alerts + noise
        alerts = NOISE_ALERTS[:] + [
            {
                "id": "A020", "severity": "info", "service": "price-validation-service",
                "message": "Price mismatch rate 15.1% — above SLA threshold of 1.0%. Data team notified.",
                "timestamp": "2026-03-30T11:02:24Z", "acknowledged": False,
            },
            {
                "id": "A021", "severity": "warning", "service": "analytics-service",
                "message": "avg_order_value anomaly: $847.23 vs baseline $89.42 — not correlated with campaigns",
                "timestamp": "2026-03-30T11:02:21Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="hard", step=0, max_steps=25,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause=f"data_corruption_data_pipeline_{bad_ver}_incorrect_price_writes",
            ground_truth_fix="rollback data-pipeline-service then alert_oncall for data audit",
            incident_start_time=INCIDENT_TIME,
            healthy_services=list(services.keys()),
            service_dependencies=DEPENDENCIES,
        )
        state._bad_ver = bad_ver
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        state.step += 1
        # No SLA degradation on hard task — all services stay green
        at = action.action_type
        svc = action.service or ""
        reward = 0.0
        done = False
        info: Dict[str, Any] = {}

        result_text, error_text = self._apply_action_to_logs(state, action)

        gather_map = {
            ("read_logs", "price-validation-service"): ("rl_price", 0.05),
            ("search_logs", "price-validation-service"): ("rl_price", 0.05),
            ("read_logs", "analytics-service"):         ("rl_analytics", 0.05),
            ("search_logs", "analytics-service"):       ("rl_analytics", 0.05),
            ("read_logs", "data-pipeline-service"):     ("rl_pipeline", 0.05),
            ("search_logs", "data-pipeline-service"):   ("rl_pipeline", 0.05),
            ("read_metrics", "analytics-service"):      ("rm_analytics", 0.10),
            ("read_metrics", "data-pipeline-service"):  ("rm_pipeline", 0.10),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r; state.rewards_given.add(tag)

        if at == ActionType.READ_RUNBOOK:
            if "runbook" not in state.rewards_given:
                reward += 0.05; state.rewards_given.add("runbook")

        # Restarts/scale-ups are always wrong here
        if at in (ActionType.RESTART_SERVICE, ActionType.SCALE_UP):
            reward -= 0.15
            error_text = (
                f"Restarting/scaling {svc} will not fix corrupt data already written. "
                "You need to rollback the pipeline and audit the data."
            )

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            has_pipeline = semantic_match(rc, ["pipeline", "data-pipeline"])
            has_corruption = semantic_match(rc, ["corrupt", "data", "price", "wrong", "incorrect", "mismatch"])
            result_text = f"Diagnosis recorded: {rc}"
            if has_pipeline and has_corruption:
                if "diagnose_correct" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("diagnose_correct")
            elif has_pipeline or has_corruption:
                if "diagnose_partial" not in state.rewards_given and "diagnose_correct" not in state.rewards_given:
                    reward += 0.08; state.rewards_given.add("diagnose_partial")

        if at == ActionType.ROLLBACK and svc == "data-pipeline-service":
            reward += self._penalty_blind_remediation(state, action, "rollback_done")
            if "rollback_done" not in state.rewards_given:
                reward += 0.25; state.rewards_given.add("rollback_done")
                state.services["data-pipeline-service"]["current_version"] = "v3.0.9"
                result_text = (
                    "data-pipeline-service rolled back to v3.0.9. Future writes corrected. "
                    "WARNING: corrupted prices already written must be audited."
                )
                if "alert_oncall_done" in state.rewards_given:
                    state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"

        if at == ActionType.ALERT_ONCALL:
            if "alert_oncall_done" not in state.rewards_given:
                reward += 0.15; state.rewards_given.add("alert_oncall_done")
                result_text = "On-call data team paged for price audit and correction job."
                if "rollback_done" in state.rewards_given:
                    state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"


        if at in (ActionType.BLOCK_IP_RANGE, ActionType.CREATE_INDEX, ActionType.FAILOVER):
            reward -= 0.10
            error_text = f"Action {at.value} is not applicable to this incident."

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

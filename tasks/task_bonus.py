from __future__ import annotations
import uuid
from typing import Dict, Any, List
from models import Action, ActionType
from tasks.base import BaseTask, InternalState, StepOutput, semantic_match

INCIDENT_TIME = "2026-03-30T14:22:00Z"

DEPENDENCIES = [
    {"service": "api-gateway",         "calls": ["ml-inference-service", "product-service"], "called_by": []},
    {"service": "ml-inference-service","calls": [],                                           "called_by": ["api-gateway"]},
    {"service": "log-aggregator",      "calls": [],                                           "called_by": []},
    {"service": "product-service",     "calls": [],                                           "called_by": ["api-gateway"]},
]

AGGREGATOR_LOGS = [
    "[14:20:01] INFO  Log ingestion running: 48MB/s",
    "[14:21:05] WARN  Disk usage at 91% (/var/log/aggregated)",
    "[14:21:45] WARN  Disk usage at 95% - log rotation overdue",
    "[14:22:01] ERROR Disk usage at 99% - write failure imminent",
    "[14:22:02] ERROR Failed to write log chunk: No space left on device (ENOSPC)",
    "[14:22:04] WARN  Dropping incoming logs: buffer overflow (48000 messages dropped)",
    "[14:22:05] ERROR Log rotation job FAILED: No space left on device",
    "[14:22:10] CRIT  Disk 100% full - all log writes failing",
]

ML_LOGS = [
    "[14:21:00] INFO  ml-inference-service starting",
    "[14:21:01] INFO  Loading model: recommendation-v2.1 (2.3GB)",
    "[14:21:12] INFO  Model loaded in 11.2s",
    "[14:21:12] WARN  Model checksum mismatch - reloading",
    "[14:21:23] INFO  Model loaded in 11.1s",
    "[14:21:23] WARN  Model checksum mismatch - reloading",
    "[14:21:34] WARN  Model reload loop detected: 6 reloads in 60s",
    "[14:22:01] ERROR CPU throttled: 100% sustained for 120s",
    "[14:22:02] WARN  Deployment {version} introduced new model checksum validation - may have bug",
]

API_LOGS = [
    "[14:22:00] INFO  GET /api/v1/recommendations 200 145ms",
    "[14:22:05] WARN  GET /api/v1/recommendations 200 4823ms (ml-inference slow)",
    "[14:22:15] ERROR GET /api/v1/recommendations 504 Gateway Timeout",
]


class BonusTask(BaseTask):
    def initialize(self) -> InternalState:
        ml_ver = f"v2.{self.rng.randint(0, 3)}.{self.rng.randint(0, 5)}"

        logs = {
            "log-aggregator": AGGREGATOR_LOGS[:],
            "ml-inference-service": [l.replace("{version}", ml_ver) for l in ML_LOGS],
            "api-gateway": API_LOGS[:],
            "product-service": ["[14:22:00] INFO  Service healthy - 0 errors"],
        }

        services = {
            "api-gateway": {
                "name": "api-gateway", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(40, 58), 1),
                "memory_percent": round(self.rng.uniform(44, 56), 1),
                "error_rate": round(self.rng.uniform(3.0, 6.0), 2),
                "latency_p99_ms": round(self.rng.uniform(8000, 12000), 0),
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": "v3.1.0", "last_deployed": "2026-03-20T08:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "ml-inference-service": {
                "name": "ml-inference-service", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(94, 100), 1),
                "memory_percent": round(self.rng.uniform(55, 72), 1),
                "error_rate": round(self.rng.uniform(1.5, 4.0), 2),
                "latency_p99_ms": round(self.rng.uniform(9000, 14000), 0),
                "replicas_running": 2, "replicas_desired": 2,
                "current_version": ml_ver, "last_deployed": "2026-03-30T14:20:55Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "log-aggregator": {
                "name": "log-aggregator", "status": "degraded",
                "cpu_percent": round(self.rng.uniform(18, 30), 1),
                "memory_percent": round(self.rng.uniform(40, 52), 1),
                "error_rate": round(self.rng.uniform(5.0, 9.0), 2),
                "latency_p99_ms": round(self.rng.uniform(200, 500), 0),
                "replicas_running": 1, "replicas_desired": 1,
                "current_version": "v1.3.0", "last_deployed": "2026-03-01T10:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
            "product-service": {
                "name": "product-service", "status": "healthy",
                "cpu_percent": round(self.rng.uniform(25, 38), 1),
                "memory_percent": round(self.rng.uniform(35, 48), 1),
                "error_rate": 0.0,
                "latency_p99_ms": round(self.rng.uniform(15, 35), 0),
                "replicas_running": 3, "replicas_desired": 3,
                "current_version": "v2.0.1", "last_deployed": "2026-03-15T12:00:00Z",
                "minutes_degraded": 0, "sla_breach": False,
            },
        }

        alerts = [
            {
                "id": "B001", "severity": "critical", "service": "log-aggregator",
                "message": "Disk 100% full on log-aggregator - dropping 48000 log messages/min",
                "timestamp": "2026-03-30T14:22:10Z", "acknowledged": False,
            },
            {
                "id": "B002", "severity": "critical", "service": "ml-inference-service",
                "message": f"CPU sustained 99%+ for 120s - model reload loop detected ({ml_ver})",
                "timestamp": "2026-03-30T14:22:01Z", "acknowledged": False,
            },
            {
                "id": "B003", "severity": "warning", "service": "api-gateway",
                "message": "P99 latency 10200ms on /recommendations - upstream ml-inference slow",
                "timestamp": "2026-03-30T14:22:15Z", "acknowledged": False,
            },
        ]

        state = InternalState(
            episode_id=str(uuid.uuid4()), task_id="bonus", step=0, max_steps=25,
            services=services, alerts=alerts, logs=logs,
            action_history=[], total_reward=0.0, incident_resolved=False,
            ground_truth_root_cause="disk_full_log_aggregator AND model_reload_loop_ml_inference",
            ground_truth_fix="alert_oncall for disk cleanup AND rollback ml-inference-service",
            incident_start_time=INCIDENT_TIME,
            healthy_services=["product-service"],
            service_dependencies=DEPENDENCIES,
        )
        state._ml_version = ml_ver
        return state

    def step(self, state: InternalState, action: Action) -> StepOutput:
        state.step += 1
        state._apply_sla_degradation()
        at = action.action_type
        svc = action.service or ""
        reward = 0.0
        done = False
        info: Dict[str, Any] = {}

        result_text, error_text = self._apply_action_to_logs(state, action)

        gather_map = {
            ("read_logs", "log-aggregator"):       ("rl_agg", 0.05),
            ("read_logs", "ml-inference-service"): ("rl_ml", 0.05),
            ("read_metrics", "log-aggregator"):    ("rm_agg", 0.05),
            ("read_metrics", "ml-inference-service"): ("rm_ml", 0.05),
        }
        k = (at.value, svc)
        if k in gather_map:
            tag, r = gather_map[k]
            if tag not in state.rewards_given:
                reward += r; state.rewards_given.add(tag)

        if at == ActionType.READ_RUNBOOK:
            if "runbook" not in state.rewards_given:
                reward += 0.04; state.rewards_given.add("runbook")

        if at == ActionType.DIAGNOSE:
            rc = action.root_cause or ""
            has_disk = semantic_match(rc, ["disk", "storage", "full", "space", "log", "aggregat"])
            has_ml = semantic_match(rc, ["ml", "inference", "model", "reload", "cpu", "loop"])
            result_text = f"Diagnosis recorded: {rc}"
            if has_disk and has_ml:
                if "diagnose_both" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("diagnose_both")
            elif has_disk or has_ml:
                if "diagnose_one" not in state.rewards_given:
                    reward += 0.08; state.rewards_given.add("diagnose_one")

        # Fix 1: disk issue via oncall
        if at == ActionType.ALERT_ONCALL:
            reason = (action.reason or "").lower()
            if semantic_match(reason, ["disk", "log", "storage", "space", "aggregat"]):
                if "fix_disk" not in state.rewards_given:
                    reward += 0.20; state.rewards_given.add("fix_disk")
                    result_text = "SRE paged for disk cleanup. Volume extension underway (~5 min)."
                    if "fix_ml" in state.rewards_given:
                        state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"
            else:
                if "fix_disk" not in state.rewards_given:
                    reward += 0.08
                    result_text = "On-call paged. Clarify disk/log issue for faster resolution."

        # Fix 2: ML reload loop via rollback or restart
        if at in (ActionType.ROLLBACK, ActionType.RESTART_SERVICE) and svc == "ml-inference-service":
            if "fix_ml" not in state.rewards_given:
                r_base = 0.20 if at == ActionType.ROLLBACK else 0.12
                reward += r_base; state.rewards_given.add("fix_ml")
                state.services["ml-inference-service"]["cpu_percent"] = round(self.rng.uniform(22, 38), 1)
                state.services["ml-inference-service"]["latency_p99_ms"] = round(self.rng.uniform(80, 140), 0)
                state.services["ml-inference-service"]["error_rate"] = 0.0
                action_word = "rolled back" if at == ActionType.ROLLBACK else "restarted"
                result_text = f"ml-inference-service {action_word}. Reload loop stopped. CPU recovering."
                if "fix_disk" in state.rewards_given:
                    state.incident_resolved = True; done = True; info["resolution"] = "incident_resolved"

        if at in (ActionType.RESTART_SERVICE, ActionType.ROLLBACK) and svc in state.healthy_services:
            reward -= 0.08
        if at == ActionType.NOOP and state.step > 5:
            reward -= 0.03

        state.total_reward = self._clamp(state.total_reward + reward)
        if state.step >= state.max_steps and not done:
            done = True; info["reason"] = "max_steps_reached"

        obs = state._build_observation(last_action_result=result_text, last_action_error=error_text)
        state.action_history.append({"step": state.step, "action": action.model_dump(), "reward": round(reward, 4)})
        return StepOutput(next_state=state, reward=round(reward, 4), done=done, info=info)

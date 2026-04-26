import random

class IncidentFactory:
    FAILURE_MODES = ["oom", "cascade", "corruption", "security", "database", "network_partition", "network_latency", "config_drift"]
    SERVICES = ["payment-service", "order-service", "user-service", 
                "inventory-service", "api-gateway", "notification-service", 
                "data-pipeline", "ml-inference-service"]
    SEVERITIES = ["sev1", "sev2", "sev3"]
    NOISE_ALERTS = [
        "Scheduled batch job running — high CPU expected",
        "SSL certificate renewal in progress",
        "Nightly analytics aggregation running",
        "CDN cache warming after deployment",
        "Routine health check latency spike"
    ]
    NOISE_ALERTS_NETWORK_LATENCY = [
        "INFO: Scheduled maintenance window active — some latency variation expected",
        "CDN edge node rotation in progress",
        "Routine health check latency spike",
    ]
    NOISE_ALERTS_CONFIG_DRIFT = [
        "WARNING: data-pipeline memory usage elevated (85%) — not yet critical",
        "INFO: Scheduled batch job running — high CPU expected",
    ]

    def generate(self, seed: int) -> dict:
        rng = random.Random(seed)
        failure_mode = rng.choice(self.FAILURE_MODES)
        affected_service = rng.choice(self.SERVICES)
        severity = rng.choice(self.SEVERITIES)
        noise_count = rng.randint(0, 3)
        if failure_mode == "network_latency":
            noise_pool = self.NOISE_ALERTS_NETWORK_LATENCY
            noise_count = min(noise_count + 1, len(noise_pool))
        elif failure_mode == "config_drift":
            noise_pool = self.NOISE_ALERTS_CONFIG_DRIFT
            noise_count = min(noise_count + 1, len(noise_pool))
        else:
            noise_pool = self.NOISE_ALERTS
        noise_alerts = rng.sample(noise_pool, min(noise_count, len(noise_pool)))

        # Templates for description
        descriptions = {
            "oom": f"{affected_service} is crash-looping due to memory exhaustion. Process memory exceeded limits.",
            "cascade": f"{affected_service} bad deployment causing downstream connection pool exhaustion across dependent services.",
            "corruption": f"Silent data corruption in {affected_service}. Invalid records being written. No error-rate alerts — signal buried in business metrics.",
            "security": f"Credential stuffing botnet targeting {affected_service} from IP range 185.220.x.x.",
            "database": f"Missing index on {affected_service} database after migration. Full table scans degrading all queries.",
            "network_partition": f"Network partition isolating {affected_service} in us-east-1. Failover decision required.",
            "network_latency": f"Gradual latency degradation in {affected_service}. All services remain running but P99 latency is 10–50x normal. No crashes, no OOM — signal is purely in latency metrics.",
            "config_drift": f"{affected_service} deployed with incorrect environment variables. Service appears healthy — error rate is low — but outputs are wrong. Signal buried in CONFIG_ERROR log warnings and downstream data validation failures.",
        }
        description = descriptions[failure_mode]

        # Templates for root cause
        root_causes = {
            "oom": f"Memory leak in {affected_service} causing OOM crash-loop",
            "cascade": f"Bad deployment in {affected_service} causing cascading connection failures",
            "corruption": f"Data corruption in {affected_service} writing invalid records",
            "security": f"DDoS credential stuffing from 185.220.0.0/16 targeting {affected_service}",
            "database": f"Missing index causing sequential scans on {affected_service}",
            "network_partition": f"Network partition in us-east-1 affecting {affected_service}",
            "network_latency": f"Network latency degradation in {affected_service}",
            "config_drift": f"Config drift in {affected_service} writing incorrect output",
        }
        ground_truth_root_cause = root_causes[failure_mode]

        # Templates for fix
        fixes = {
            "oom": "restart_service",
            "cascade": "rollback",
            "corruption": "rollback",
            "security": "block_ip_range",
            "database": "create_index",
            "network_partition": "failover",
            "network_latency": "rollback",
            "config_drift": "rollback",
        }
        ground_truth_fix = fixes[failure_mode]

        # Difficulty score
        base_scores = {
            "oom": 0.2, "cascade": 0.5, "corruption": 0.8,
            "security": 0.6, "database": 0.6, "network_partition": 0.7,
            "network_latency": 0.55, "config_drift": 0.75,
        }
        score = base_scores[failure_mode] + (noise_count * 0.05)
        score = min(score, 1.0)

        return {
            "task_id": "generated",
            "incident_id": f"INC-{seed:05d}",
            "seed": seed,
            "failure_mode": failure_mode,
            "affected_service": affected_service,
            "severity": severity,
            "noise_alerts": noise_alerts,
            "description": description,
            "ground_truth_root_cause": ground_truth_root_cause,
            "ground_truth_fix": ground_truth_fix,
            "difficulty_score": round(score, 2),
            "estimated_optimal_score": round(0.99 - score * 0.3, 2)
        }

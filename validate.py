#!/usr/bin/env python3
"""
validate.py — Pre-submission validation script.

Run this before submitting to confirm all checklist items pass:
    python validate.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""
import sys
import os
import random
import traceback

sys.path.insert(0, os.path.dirname(__file__))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"

failures = []


def check(name: str, fn):
    try:
        result = fn()
        if result is True or result is None:
            print(f"  {PASS}  {name}")
            return True
        else:
            print(f"  {FAIL}  {name}: {result}")
            failures.append(name)
            return False
    except Exception as e:
        print(f"  {FAIL}  {name}: {e}")
        traceback.print_exc()
        failures.append(name)
        return False


def main():
    print("\n=== DevOps Incident Response — OpenEnv Validation ===\n")

    # --- Imports ---
    print("[ Imports ]")

    def check_imports():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType, Observation, StepResult, State
        from graders.grader import grade_episode
        return True

    check("All modules import cleanly", check_imports)

    # --- Reset returns valid Observation ---
    print("\n[ reset() ]")

    def check_reset_easy():
        from env import DevOpsIncidentEnv
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        obs = env.reset()
        assert obs.step == 0
        assert len(obs.services) > 0
        assert len(obs.active_alerts) > 0
        assert obs.task_id == "easy"
        return True

    def check_reset_all_tasks():
        from env import DevOpsIncidentEnv
        for task_id in ["easy", "medium", "hard", "bonus", "security", "database", "failover"]:
            env = DevOpsIncidentEnv(task_id=task_id, seed=42)
            obs = env.reset()
            assert obs.task_id == task_id, f"task_id mismatch for {task_id}"
            assert obs.max_steps > 0
        return True

    def check_reset_reproducible():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        results = []
        for _ in range(3):
            env = DevOpsIncidentEnv(task_id="easy", seed=42)
            obs = env.reset()
            results.append(obs.services[0].memory_percent)
        assert len(set(results)) == 1, f"Different results for same seed: {results}"
        return True

    def check_seed_variety():
        from env import DevOpsIncidentEnv
        roots = set()
        for seed in range(10):
            env = DevOpsIncidentEnv(task_id="easy", seed=seed)
            env.reset()
            s = env.state()
            roots.add(s.ground_truth_root_cause)
        assert len(roots) > 1, f"All seeds produce same scenario: {roots}"
        return True

    check("reset() returns valid Observation for easy task", check_reset_easy)
    check("reset() works for all 4 tasks", check_reset_all_tasks)
    check("Same seed always produces same episode", check_reset_reproducible)
    check("Different seeds produce different scenarios", check_seed_variety)

    # --- step() ---
    print("\n[ step() ]")

    def check_step_returns_result():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType, StepResult
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        env.reset()
        result = env.step(Action(action_type=ActionType.NOOP))
        assert isinstance(result, StepResult)
        assert isinstance(result.reward, float)
        assert isinstance(result.done, bool)
        assert result.observation.step == 1
        return True

    def check_step_reward_in_range():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        rng = random.Random(0)
        for task_id in ["easy", "medium", "hard", "bonus", "security", "database", "failover"]:
            env = DevOpsIncidentEnv(task_id=task_id, seed=42)
            env.reset()
            done = False
            steps = 0
            while not done and steps < 30:
                action = Action(action_type=rng.choice(list(ActionType)))
                result = env.step(action)
                assert -1.0 <= result.reward <= 1.0, f"reward={result.reward} out of range"
                done = result.done
                steps += 1
        return True

    def check_max_steps_terminates():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        env.reset()
        done = False
        steps = 0
        while not done:
            result = env.step(Action(action_type=ActionType.NOOP))
            done = result.done
            steps += 1
            assert steps <= 20, "Episode never terminated"
        return True

    check("step() returns valid StepResult", check_step_returns_result)
    check("step() rewards always in [-1.0, 1.0]", check_step_reward_in_range)
    check("Episode terminates at max_steps", check_max_steps_terminates)

    # --- state() ---
    print("\n[ state() ]")

    def check_state_has_ground_truth():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        env = DevOpsIncidentEnv(task_id="medium", seed=42)
        env.reset()
        env.step(Action(action_type=ActionType.NOOP))
        s = env.state()
        assert s.ground_truth_root_cause != ""
        assert s.ground_truth_fix != ""
        assert len(s.action_history) == 1
        return True

    check("state() returns ground truth and action history", check_state_has_ground_truth)

    # --- Graders ---
    print("\n[ Graders ]")

    def check_graders_in_range():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        from graders.grader import grade_episode
        rng = random.Random(99)
        for task_id in ["easy", "medium", "hard", "bonus", "security", "database", "failover"]:
            env = DevOpsIncidentEnv(task_id=task_id, seed=42)
            env.reset()
            done = False
            steps = 0
            while not done and steps < 30:
                action = Action(action_type=rng.choice(list(ActionType)))
                result = env.step(action)
                done = result.done
                steps += 1
            s = env.state()
            score = grade_episode(
                task_id, s.action_history, s.ground_truth_root_cause,
                s.ground_truth_fix, s.incident_resolved, s.total_reward,
            )
            assert 0.0 <= score <= 1.0, f"{task_id} score={score} out of [0,1]"
        return True

    def check_graders_not_constant():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        from graders.grader import grade_episode
        scores = []
        for seed in [1, 2, 3, 42, 99]:
            rng = random.Random(seed * 7)
            env = DevOpsIncidentEnv(task_id="easy", seed=seed)
            env.reset()
            done = False
            steps = 0
            while not done and steps < 15:
                action = Action(action_type=rng.choice(list(ActionType)))
                result = env.step(action)
                done = result.done
                steps += 1
            s = env.state()
            score = grade_episode(
                "easy", s.action_history, s.ground_truth_root_cause,
                s.ground_truth_fix, s.incident_resolved, s.total_reward,
            )
            scores.append(score)
        assert len(set(scores)) > 1, f"Grader returns constant score: {scores}"
        return True

    def check_optimal_agent_scores_high():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        from graders.grader import grade_episode
        # Easy task optimal sequence
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        env.reset()
        s0 = env.state()
        failing = s0.ground_truth_root_cause.replace("memory_leak_", "").replace("_", "-")
        for act in [
            Action(action_type=ActionType.READ_LOGS, service=failing),
            Action(action_type=ActionType.READ_METRICS, service=failing),
            Action(action_type=ActionType.DIAGNOSE, root_cause=f"memory leak {failing}"),
            Action(action_type=ActionType.RESTART_SERVICE, service=failing),
        ]:
            result = env.step(act)
            if result.done:
                break
        s = env.state()
        score = grade_episode(
            "easy", s.action_history, s.ground_truth_root_cause,
            s.ground_truth_fix, s.incident_resolved, s.total_reward,
        )
        assert score >= 0.85, f"Optimal agent scored only {score:.3f} on easy"
        return True

    check("All graders return scores in [0.0, 1.0]", check_graders_in_range)
    check("Grader does not return constant scores across episodes", check_graders_not_constant)
    check("Optimal agent scores >= 0.85 on easy task", check_optimal_agent_scores_high)

    # --- Collateral damage penalty ---
    print("\n[ Reward shaping ]")

    def check_collateral_damage_penalty():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        env.reset()
        s0 = env.state()
        healthy = [svc for svc in s0.current_observation.services
                   if svc.status == "healthy"]
        assert len(healthy) > 0, "No healthy services to test with"
        result = env.step(Action(action_type=ActionType.RESTART_SERVICE,
                                 service=healthy[0].name))
        assert result.reward < 0, f"Expected negative reward for healthy restart, got {result.reward}"
        return True

    def check_info_gathering_rewarded():
        from env import DevOpsIncidentEnv
        from models import Action, ActionType
        env = DevOpsIncidentEnv(task_id="easy", seed=42)
        env.reset()
        s0 = env.state()
        failing = s0.ground_truth_root_cause.replace("memory_leak_", "").replace("_", "-")
        result = env.step(Action(action_type=ActionType.READ_LOGS, service=failing))
        assert result.reward > 0, f"Expected positive reward for reading failing service logs, got {result.reward}"
        return True

    check("Restarting healthy service gives negative reward", check_collateral_damage_penalty)
    check("Reading failing service logs gives positive reward", check_info_gathering_rewarded)

    # --- Files present ---
    print("\n[ Required files ]")

    for fname in ["openenv.yaml", "Dockerfile", "requirements.txt",
                  "inference.py", "README.md", "env.py", "api.py"]:
        path = os.path.join(os.path.dirname(__file__), fname)
        check(f"{fname} exists", lambda p=path: os.path.exists(p) or f"Missing: {p}")

    # --- Summary ---
    print()
    if not failures:
        print(f"{PASS} All checks passed! Ready to submit.\n")
        sys.exit(0)
    else:
        print(f"{FAIL} {len(failures)} check(s) failed: {failures}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

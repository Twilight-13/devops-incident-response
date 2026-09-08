from __future__ import annotations

from collections import deque


class CurriculumEngine:
    def __init__(self):
        self.tasks = ["easy", "medium", "hard", "bonus", "security", "database", "failover"]
        self.scores: dict[str, deque] = {
            task_id: deque(maxlen=5) for task_id in self.tasks
        }
        self.mastery: dict[str, int] = {task_id: 0 for task_id in self.tasks}
        self._hints: dict[str, str] = {
            "easy": "Focus on the service with highest memory_percent. Read its logs before acting.",
            "medium": "Follow the dependency map backwards from the erroring service to find the root cause.",
            "hard": "All services look green. Check WARN-level logs and business metrics, not error rates.",
            "bonus": "There are two independent failures. Fix each one separately — do not conflate them.",
            "security": "Look for repeated login failures from the same IP range in the access logs.",
            "database": "Check for sequential scans in slow query logs. The fix is structural, not a restart.",
            "failover": "Read the failover runbook first. Not all services are safe — check compliance constraints.",
        }
        self._rotation_index = 0
        self._total_episodes_recorded = 0

    def _ensure_task(self, task_id: str) -> None:
        if task_id not in self.scores:
            raise ValueError(f"Unknown task_id: {task_id}")

    def record_episode(self, task_id: str, score: float) -> None:
        self._ensure_task(task_id)
        self.scores[task_id].append(float(score))
        self._total_episodes_recorded += 1
        self._update_mastery(task_id)

    def _update_mastery(self, task_id: str) -> None:
        self._ensure_task(task_id)
        rolling_avg = self.get_rolling_avg(task_id)
        if rolling_avg > 0.75 and self.mastery[task_id] < 3:
            self.mastery[task_id] += 1
        elif rolling_avg < 0.30 and self.mastery[task_id] > 0:
            self.mastery[task_id] -= 1

    def get_mastery(self, task_id: str) -> int:
        self._ensure_task(task_id)
        return self.mastery[task_id]

    def get_rolling_avg(self, task_id: str) -> float:
        self._ensure_task(task_id)
        recent_scores = self.scores[task_id]
        if not recent_scores:
            return 0.0
        return sum(recent_scores) / len(recent_scores)

    def should_scaffold(self, task_id: str) -> bool:
        self._ensure_task(task_id)
        return len(self.scores[task_id]) >= 3 and self.get_rolling_avg(task_id) < 0.30

    def get_hint(self, task_id: str) -> str:
        self._ensure_task(task_id)
        return self._hints[task_id]

    def _get_non_mastered_tasks(self) -> list[str]:
        return [task_id for task_id in self.tasks if self.mastery[task_id] < 3]

    def _sorted_candidates(self) -> list[str]:
        candidates = self._get_non_mastered_tasks()
        return sorted(
            candidates,
            key=lambda task_id: (self.get_rolling_avg(task_id), self.tasks.index(task_id)),
        )

    def get_recommended_task(self) -> str:
        candidates = self._sorted_candidates()
        if not candidates:
            return "bonus"
        return candidates[0]

    def get_next_curriculum_task(self) -> str:
        candidates = self._sorted_candidates()
        if not candidates:
            return "bonus"
        task_id = candidates[self._rotation_index % len(candidates)]
        self._rotation_index = (self._rotation_index + 1) % len(candidates)
        return task_id

    def get_status(self) -> dict:
        mastery_labels = {
            0: "novice",
            1: "intermediate",
            2: "advanced",
            3: "mastered",
        }
        tasks = {}
        for task_id in self.tasks:
            scaffold_needed = self.should_scaffold(task_id)
            tasks[task_id] = {
                "mastery_level": self.mastery[task_id],
                "mastery_label": mastery_labels[self.mastery[task_id]],
                "rolling_avg": self.get_rolling_avg(task_id),
                "recent_scores": list(self.scores[task_id]),
                "scaffold_needed": scaffold_needed,
                "hint": self.get_hint(task_id) if scaffold_needed else None,
            }
        return {
            "tasks": tasks,
            "recommended_task": self.get_recommended_task(),
            "total_episodes_recorded": self._total_episodes_recorded,
        }


class CurriculumScheduler:
    """
    Level-based curriculum scheduler implementing mastery-based progression.

    Automatically selects task difficulty based on the agent's recent
    performance. Agents start on beginner tasks and advance through four
    difficulty levels as their average score crosses thresholds.  Falling
    back to an easier level is also supported so the agent always receives
    a meaningful learning signal.

    Task difficulty levels
    ----------------------
    Level 0 (Beginner):      easy, dns
    Level 1 (Intermediate):  medium, waf, database
    Level 2 (Advanced):      hard, thundering_herd, security
    Level 3 (Expert):        bonus, failover

    Progression rules
    -----------------
    Advance  : avg score of current-level tasks in last WINDOW_SIZE episodes
               >= ADVANCE_THRESHOLD  (and not already at level 3)
    Fall back : avg score < FALLBACK_THRESHOLD  (and not already at level 0)
    """

    LEVELS: dict[int, list[str]] = {
        0: ["easy", "dns"],
        1: ["medium", "waf", "database"],
        2: ["hard", "thundering_herd", "security"],
        3: ["bonus", "failover"],
    }

    ADVANCE_THRESHOLD: float = 0.65
    FALLBACK_THRESHOLD: float = 0.25
    WINDOW_SIZE: int = 10

    def __init__(self) -> None:
        self.current_level: int = 0
        self.episode_history: list[tuple[str, float]] = []
        self.level_history: list[tuple[int, int]] = []  # (episode_num, level)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def select_task(self) -> str:
        """Return a random task from the current difficulty level."""
        import random
        return random.choice(self.LEVELS[self.current_level])

    def record_episode(self, task_id: str, score: float) -> dict:
        """
        Record a completed episode and potentially update the current level.

        Returns a dict with keys:
            level      – int, new current level
            action     – "advance" | "fallback" | "stay"
            avg_score  – float, recent average across current-level tasks
            message    – human-readable explanation
        """
        self.episode_history.append((task_id, float(score)))
        self.level_history.append((len(self.episode_history), self.current_level))

        if len(self.episode_history) < self.WINDOW_SIZE:
            return {
                "level": self.current_level,
                "action": "stay",
                "avg_score": float(score),
                "message": "Collecting initial episodes",
            }

        recent = self.episode_history[-self.WINDOW_SIZE:]
        current_level_scores = [
            s for t, s in recent if t in self.LEVELS[self.current_level]
        ]

        if not current_level_scores:
            return {
                "level": self.current_level,
                "action": "stay",
                "avg_score": 0.0,
                "message": "No recent episodes at current level",
            }

        avg_score = sum(current_level_scores) / len(current_level_scores)

        if avg_score >= self.ADVANCE_THRESHOLD and self.current_level < 3:
            self.current_level += 1
            return {
                "level": self.current_level,
                "action": "advance",
                "avg_score": avg_score,
                "message": (
                    f"Advanced to level {self.current_level}! "
                    f"Avg score: {avg_score:.3f}"
                ),
            }

        if avg_score < self.FALLBACK_THRESHOLD and self.current_level > 0:
            self.current_level -= 1
            return {
                "level": self.current_level,
                "action": "fallback",
                "avg_score": avg_score,
                "message": (
                    f"Fell back to level {self.current_level}. "
                    f"Avg score: {avg_score:.3f}"
                ),
            }

        return {
            "level": self.current_level,
            "action": "stay",
            "avg_score": avg_score,
            "message": (
                f"Staying at level {self.current_level}. "
                f"Avg score: {avg_score:.3f}"
            ),
        }

    def get_stats(self) -> dict:
        """Return curriculum statistics for monitoring."""
        return {
            "current_level": self.current_level,
            "current_tasks": self.LEVELS[self.current_level],
            "total_episodes": len(self.episode_history),
            "level_history": self.level_history[-20:],
            "recent_avg_score": (
                sum(s for _, s in self.episode_history[-10:])
                / min(10, len(self.episode_history))
                if self.episode_history
                else 0.0
            ),
        }


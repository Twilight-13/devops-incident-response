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

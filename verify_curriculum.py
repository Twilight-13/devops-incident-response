import sys
sys.path.insert(0, '.')
from curriculum import CurriculumScheduler
import random

random.seed(42)
scheduler = CurriculumScheduler()

# Simulate good performance — should advance to level 1
advanced = False
for i in range(12):
    task = scheduler.select_task()
    assert task in ['easy', 'dns'], f'Expected level 0 task, got {task}'
    result = scheduler.record_episode(task, 0.80)
    if result['action'] == 'advance':
        print(f"Episode {i}: Advanced to level {result['level']}")
        advanced = True
        break

assert advanced, 'Never advanced after 12 episodes of 0.80 score!'
assert scheduler.current_level == 1, f'Should be at level 1, at {scheduler.current_level}'

# Simulate bad performance — should fall back to level 0
fell_back = False
for i in range(15):
    task = scheduler.select_task()
    result = scheduler.record_episode(task, 0.10)
    if result['action'] == 'fallback':
        print(f"Fell back to level {result['level']}")
        fell_back = True
        break

assert fell_back, 'Never fell back after 15 episodes of 0.10 score!'
assert scheduler.current_level == 0, f'Should be at level 0, at {scheduler.current_level}'
print('Curriculum learning: ALL CHECKS PASSED')

import sys
sys.path.insert(0, '.')
from multi_agent_env import MultiAgentDevOpsEnv
from models import Action, ActionType

env = MultiAgentDevOpsEnv(task_id='bonus', seed=42)
obs = env.reset()
print('Multi-agent reset: OK')
print('Investigator services:', [s.name for s in obs.investigator_obs.services])

# Investigator reads logs
result = env.step_investigator(Action(action_type=ActionType.READ_LOGS, service='log-aggregator'))
inv_rew = result['investigator_reward']
print(f'Investigator reward: {inv_rew}')
assert inv_rew > 0, f'Expected > 0, got {inv_rew}'

# Test that responder cannot read logs
result2 = env.step_responder(Action(action_type=ActionType.READ_LOGS, service='log-aggregator'))
assert result2.get('error') is not None, 'Responder should not be able to read logs'
print('Role enforcement: PASSED')

# Responder rolls back ML inference
result3 = env.step_responder(Action(action_type=ActionType.ROLLBACK, service='ml-inference-service', version='previous'))
resp_rew = result3['responder_reward']
print(f'Responder reward: {resp_rew}')
assert resp_rew > 0, f'Expected > 0, got {resp_rew}'

# Joint reward
joint = env.get_joint_reward()
print(f'Joint reward: {joint:.4f}')

# State
state = env.get_state()
print(f'Session ID: {state["session_id"][:8]}...')
print('Multi-agent mode: ALL CHECKS PASSED')

"""Run DRB FACT evaluation steps with env vars pre-set."""
import os
import sys
import subprocess

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

env = os.environ.copy()
env['LLM_BACKEND'] = 'openai'
env['OPENAI_API_KEY'] = env.get('DEEPSEEK_API_KEY', '')
env['OPENAI_BASE_URL'] = 'https://api.deepseek.com/v1'
env['FACT_MODEL'] = 'deepseek-v4-flash'
env['JINA_API_KEY'] = env.get('JINA_API_KEY', os.environ.get('JINA_API_KEY', ''))
env['PYTHONPATH'] = os.path.dirname(os.path.abspath(__file__))

step = sys.argv[1]
args = sys.argv[2:]
cmd = [sys.executable, '-m', f'utils.{step}'] + args

print(f'Running: {" ".join(cmd)}')
result = subprocess.run(cmd, env=env, cwd=os.path.dirname(os.path.abspath(__file__)))
sys.exit(result.returncode)

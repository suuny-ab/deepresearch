"""Run DRB RACE evaluation with DeepSeek API.

Usage::
    cd drb_eval
    python run_race_deepseek.py <model_name> [--max_workers N] [--only_zh]

Examples::
    python run_race_deepseek.py pipeline --only_zh
    python run_race_deepseek.py multi-agent --max_workers 4
    python run_race_deepseek.py react
"""

import os
import sys

# Add drb_eval/ to Python path so prompt/ and utils/ can be imported
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Load DeepSeek key from project .env
from dotenv import load_dotenv
load_dotenv(os.path.join(_SCRIPT_DIR, '..', '.env'))

ds_key = os.environ.get('DEEPSEEK_API_KEY', '')
if not ds_key:
    print('ERROR: DEEPSEEK_API_KEY not found in .env')
    sys.exit(1)

os.environ['LLM_BACKEND'] = 'openai'
os.environ['OPENAI_API_KEY'] = ds_key
os.environ['OPENAI_BASE_URL'] = 'https://api.deepseek.com/v1'
os.environ['RACE_MODEL'] = 'deepseek-v4-pro'
os.environ['FACT_MODEL'] = 'deepseek-v4-flash'

# Check: model_name is required as first argument
if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
    print('ERROR: <model_name> argument is required.')
    print('Usage: python run_race_deepseek.py <model_name> [--max_workers N] [--only_zh]')
    print('  <model_name> must match data/test_data/raw_data/<model_name>.jsonl')
    sys.exit(1)

# Run the actual DRB RACE main() — it parses sys.argv via argparse
from deepresearch_bench_race import main
main()

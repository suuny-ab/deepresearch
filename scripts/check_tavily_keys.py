"""One-time script to check Tavily key quota status. Run manually."""
import os
import sys
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()
from deepresearch.clients.tavily import TavilySearchClient

all_keys = []

# Primary key
pk = os.getenv("TAVILY_API_KEY")
if pk:
    all_keys.append(("PRIMARY", pk))

# Numbered keys
for i in range(1, 20):
    key = os.getenv(f"TAVILY_API_KEY_{i}")
    if key:
        all_keys.append((f"KEY_{i}", key))

print(f"Checking {len(all_keys)} Tavily keys...\n")

available = []
exhausted = []
errors = []

for label, key in all_keys:
    mask = key[:25] + "..."
    try:
        client = TavilySearchClient(api_key=key)
        results = client.search("test", subquestion_id="check", max_results=1)
        n = len(results) if results else 0
        available.append((label, key))
        print(f"  ✅ {label}: {mask} — OK ({n} results)")
    except Exception as e:
        msg = str(e)
        is_quota = any(w in msg.lower() for w in [
            "429", "quota", "exceed", "limit", "rate",
            "insufficient", "usage", "monthly", "daily",
        ])
        if is_quota:
            exhausted.append((label, key))
            print(f"  ❌ {label}: {mask} — QUOTA EXHAUSTED")
        else:
            errors.append((label, key, msg[:100]))
            print(f"  ⚠️  {label}: {mask} — {msg[:120]}")

print(f"\n{'='*50}")
print(f"Available:  {len(available)}")
print(f"Exhausted:  {len(exhausted)}")
print(f"Errors:     {len(errors)}")

if exhausted:
    print(f"\nExhausted keys (remove or wait for monthly refresh):")
    for label, _ in exhausted:
        print(f"  - {label}")

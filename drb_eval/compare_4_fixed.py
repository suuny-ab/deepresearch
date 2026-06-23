import json, os, requests, sys, dotenv

sys.path.insert(0, r"C:\Users\23514\code\deepsearch\drb_eval")
dotenv.load_dotenv(r"C:\Users\23514\code\deepsearch\.env")
ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not ds_key: print("No key"); sys.exit(1)

# Load reports - all should be Q43
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\pipeline.jsonl", encoding="utf-8") as f: pipe = json.loads(f.readline())
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\multi-agent.jsonl", encoding="utf-8") as f: multi = json.loads(f.readline())
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\react.jsonl", encoding="utf-8") as f: react = json.loads(f.readline())

# Read Q43 from reference.jsonl (it has 100 entries now)
ref = None
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\cleaned_data\reference.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["id"] == 43:
            ref = r
            break

print(f"Loaded: Pipeline Q{pipe['id']}, Multi Q{multi['id']}, React Q{react['id']}, Gold Q{ref['id']}")

reports = {
    "Pipeline": pipe["article"].replace("\\n", " ").replace("\\r", ""),
    "Multi-Agent": multi["article"].replace("\\n", " ").replace("\\r", ""),
    "React": react["article"].replace("\\n", " ").replace("\\r", ""),
    "黄金报告": ref["article"].replace("\\n", " ").replace("\\r", "")
}

# Load Q43 criteria
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\criteria_data\criteria.jsonl", encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        if c["id"] == 43: criteria_data = c; break

criteria_lines = []
for dim in ["comprehensiveness", "insight", "instruction_following", "readability"]:
    for item in criteria_data["criterions"][dim]:
        criteria_lines.append(f"- {dim}: {item['criterion']}")
criteria_text = "\\n".join(criteria_lines)

prompt = f"""你是一名调研报告评估专家。以下有四篇关于同一调研任务的文章。

调研任务：{pipe["prompt"]}

文章长度：
- Pipeline: {len(pipe["article"])} 字
- Multi-Agent: {len(multi["article"])} 字
- React: {len(react["article"])} 字
- 黄金报告: {len(ref["article"])} 字

===== Pipeline =====
{reports["Pipeline"]}

===== Multi-Agent =====
{reports["Multi-Agent"]}

===== React =====
{reports["React"]}

===== 黄金报告 =====
{reports["黄金报告"]}

请根据以下标准，对这四篇文章进行比较。对于每条标准，请从"Pipeline", "Multi-Agent", "React", "黄金报告"中选择最符合该标准的一篇，并简要说明理由。

{criteria_text}

请以JSON格式输出，格式如下：
{{
    "results": [
        {{"criterion": "标准原文", "best": "架构名", "reason": "理由"}},
        ...
    ],
    "overall_ranking": ["第一名", "第二名", "第三名", "第四名"],
    "overall_reason": "总的评价"
}}
"""

data = {"model": "deepseek-v4-pro", "messages": [{"role": "user", "content": prompt}], "max_tokens": 8000}
resp = requests.post("https://api.deepseek.com/v1/chat/completions", 
    headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
    json=data, timeout=180)
result = resp.json()
content = result["choices"][0]["message"]["content"]

with open(r"C:\Users\23514\code\deepsearch\drb_eval\compare_4_v2.json", "w", encoding="utf-8") as f:
    f.write(json.dumps({"raw": content}, ensure_ascii=False, indent=2))

try:
    parsed = json.loads(content)
    print("\\n=== 各标准胜出情况 ===")
    counts = {"Pipeline": 0, "Multi-Agent": 0, "React": 0, "黄金报告": 0}
    for r in parsed["results"]:
        counts[r["best"]] = counts.get(r["best"], 0) + 1
        print(f"  [{r['best']}] {r['criterion'][:25]} - {r['reason'][:50]}")
    print()
    print("=== 各架构赢得的条款数 ===")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} 条")
    print()
    if "overall_ranking" in parsed:
        print("=== 总排名 ===")
        for i, r in enumerate(parsed["overall_ranking"], 1):
            print(f"  {i}. {r}")
    if "overall_reason" in parsed:
        print(f"\\n总体评价: {parsed['overall_reason']}")
except Exception as e:
    print(f"Parse error: {e}")
    print("Raw:\n", content[:2000])

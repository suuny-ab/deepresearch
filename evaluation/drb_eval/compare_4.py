import json, os, requests, sys, dotenv

sys.path.insert(0, r"C:\Users\23514\code\deepsearch\drb_eval")
dotenv.load_dotenv(r"C:\Users\23514\code\deepsearch\.env")
ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not ds_key: print("No key"); sys.exit(1)

# Load reports
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\pipeline.jsonl", encoding="utf-8") as f: pipe = json.loads(f.readline())
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\multi-agent.jsonl", encoding="utf-8") as f: multi = json.loads(f.readline())
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\raw_data\react.jsonl", encoding="utf-8") as f: react = json.loads(f.readline())
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\test_data\cleaned_data\reference.jsonl", encoding="utf-8") as f:
    for line in f: ref = json.loads(line); break
reports = {"Pipeline": pipe["article"], "Multi-Agent": multi["article"], "React": react["article"], "黄金报告": ref["article"]}

for name, art in reports.items():
    reports[name] = art.replace("\\n", " ").replace("\\r", "")

# Load criteria
with open(r"C:\Users\23514\code\deepsearch\drb_eval\data\criteria_data\criteria.jsonl", encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        if c["id"] == 43: criteria_data = c; break

# Build criteria text
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

下面是每篇文章：

===== Pipeline =====
{reports["Pipeline"]}

===== Multi-Agent =====
{reports["Multi-Agent"]}

===== React =====
{reports["React"]}

===== 黄金报告 =====
{reports["黄金报告"]}

现在，请根据以下标准，对这四篇文章进行比较。对每条标准，请从"Pipeline", "Multi-Agent", "React", "黄金报告"中选择最符合该标准的一篇，并给出简要理由。

评判标准：
{criteria_text}

请按照以下JSON格式输出，不要有其他内容：
{{
    "results": [
        {{"criterion": "标准原文", "best": "Pipeline/Multi-Agent/React/黄金报告", "reason": "理由"}},
        ...
    ],
    "overall_ranking": ["第一名架构", "第二名架构", "第三名架构", "第四名架构"],
    "overall_reason": "总的评价"
}}

请确保JSON格式正确。"""

data = {"model": "deepseek-v4-pro", "messages": [{"role": "user", "content": prompt}], "max_tokens": 8000}
resp = requests.post("https://api.deepseek.com/v1/chat/completions", 
    headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
    json=data, timeout=180)
result = resp.json()
content = result["choices"][0]["message"]["content"]

# Save raw response
with open(r"C:\Users\23514\code\deepsearch\drb_eval\compare_4_results.json", "w", encoding="utf-8") as f:
    f.write(json.dumps({"raw": content}, ensure_ascii=False, indent=2))

# Print summary
try:
    parsed = json.loads(content)
    print("=== 各标准胜出情况 ===")
    counts = {"Pipeline": 0, "Multi-Agent": 0, "React": 0, "黄金报告": 0}
    for r in parsed["results"]:
        counts[r["best"]] = counts.get(r["best"], 0) + 1
        print(f"  [{r['best']}] {r['criterion'][:30]} - {r['reason'][:60]}")
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
        print(f"\n总体评价: {parsed['overall_reason']}")
except:
    print("Raw response saved. Parse failed, showing raw:")
    print(content[:3000])

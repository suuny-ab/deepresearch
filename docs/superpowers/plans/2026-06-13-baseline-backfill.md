# Phase 2: Baseline 回填实施计划

> 对 v0.3.1 ~ v0.5.2 用同一份 frozen search data 回放，产出标准 RunArtifact，存入 `benchmark/baselines/`。

## 策略

旧版本（v0.4、v0.5.1）没有 RunArtifact 输出，但都有 `--replay-search` 能力。方案：

1. **dump 脚本** — checkout 任意版本后，跑 replay 把完整 `result` state dict 存为 JSON
2. **build 脚本** — 回到 main 分支，读 state dict → 用当前 `metrics.py` + `RunArtifact` 组装标准 artifact
3. **执行** — 4 版本 × 5 query = 20 个 artifact

## Task 1: 创建 `benchmark/scripts/backfill_state.py`（dump 脚本）

在 main 分支创建，兼容旧版本 import 路径。核心逻辑：

```python
"""Dump full state dict from a replay run. Works on v0.4+."""
import json, sys
from deepresearch.cli import _build_app
from deepresearch.config import AppConfig

def main(frozen_path, output_path):
    config = AppConfig.from_env()
    with open(frozen_path) as f:
        saved = json.load(f)
    app = _build_app(config, dry_run=True, replay_search=True)
    result = app.invoke({
        "question": saved["question"],
        "subquestions": saved["subquestions"],
        "search_results": saved["search_results"],
        "errors": [],
    })
    # 序列化 state dict（Pydantic 模型用 model_dump 转 dict）
    dumpable = {}
    for key, value in result.items():
        if hasattr(value, 'model_dump'):
            dumpable[key] = value.model_dump()
        elif isinstance(value, list):
            dumpable[key] = [
                v.model_dump() if hasattr(v, 'model_dump') else v
                for v in value
            ]
        else:
            dumpable[key] = value
    with open(output_path, 'w') as f:
        json.dump(dumpable, f, indent=2, default=str)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

## Task 2: 创建 `benchmark/scripts/build_artifact.py`（build 脚本）

只在 main 分支运行，使用当前 `metrics.py` 和 `RunArtifact`：

```python
"""Build a RunArtifact from a raw state dict JSON. Runs on main (v0.5.2+)."""
import json, sys
from datetime import datetime, timezone
from deepresearch import __version__
from deepresearch.state import RunArtifact, RunMeta
from deepresearch.metrics import compute_standard_metrics

def main(state_path, version, question, output_path):
    with open(state_path) as f:
        state = json.load(f)
    
    meta = RunMeta(
        app_version=version,
        schema_version=1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode="replay",
        config={},
    )
    inputs = {"question": question, "subquestions": state.get("subquestions", [])}
    pipeline = {
        "search_results": state.get("search_results", []),
        "extracted_claims": state.get("extracted_claims", []),
        "evidence_cards": state.get("evidence_cards", []),
        "evidence_metrics": state.get("evidence_metrics", {}),
    }
    standard_metrics = compute_standard_metrics(state)
    output_section = {
        "report_markdown": state.get("report_markdown", ""),
        "report_status": state.get("report_status"),
        "review": state.get("review"),
        "validation_failures": state.get("validation_failures", []),
        "errors": state.get("errors", []),
        "output_path": state.get("output_path"),
    }
    artifact = RunArtifact(meta=meta, inputs=inputs, pipeline=pipeline,
                           standard_metrics=standard_metrics, output=output_section)
    with open(output_path, 'w') as f:
        json.dump(artifact.model_dump(), f, indent=2, default=str)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
```

## Task 3: 执行回填

对每个版本 tag × query frozen file 循环。v0.3.1 使用已有 `replay_v031.py` 适配器。

```bash
VERSIONS="v0.4 v0.5.1 v0.5.2"
QUERIES="q1-langgraph-crewai q2-solid-state-battery q3-ai-search-trends q4-quantum-crypto q5-short-answer"

for version in $VERSIONS; do
    git checkout $version
    for q in $QUERIES; do
        uv run python benchmark/scripts/backfill_state.py \
            benchmark/frozen/$q.json /tmp/$version-$q-state.json
    done
    git checkout main
    for q in $QUERIES; do
        uv run python benchmark/scripts/build_artifact.py \
            /tmp/$version-$q-state.json $version "<question>" \
            benchmark/baselines/$version/$q.json
    done
done
```

v0.3.1 单独处理：使用 `benchmark/scripts/replay_v031.py`。

## Task 4: Commit baselines

```bash
git add benchmark/baselines/
git commit -m "chore: add baseline run artifacts for v0.3.1 ~ v0.5.2"
```

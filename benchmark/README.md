# A/B Benchmarking Framework

用于 Deep Research Agent 版本间 A/B 对比测试的基础设施。

## 快速开始

```bash
# 1. 冻结搜索（用最新版本）
git checkout main
uv run deepresearch "查询文本" --save-search benchmark/frozen/q1.json --max-subquestions 4 --results-per-query 4

# 2. 回放测试（各版本）
git checkout v0.5.2
uv run deepresearch --replay-search benchmark/frozen/q1.json --output benchmark/results/v0.5.2-q1-run1.json

# 3. 对比分析
python benchmark/compare.py benchmark/results/ --config benchmark/queries.json
```

## 目录结构

```
benchmark/
├── queries.json              # 查询配置和测试定义
├── frozen/                   # 冻结的搜索结果
├── results/                  # 各版本运行输出
├── scripts/
│   └── replay_v031.py        # v0.3.1 回放适配器
├── tests/
│   └── test_compare.py       # compare.py 单元测试
├── compare.py                # 对比脚本
└── README.md
```

## 配置

编辑 `queries.json` 添加/修改查询和阈值。

## 版本要求

- v0.4+: 内置 `--save-search` 和 `--replay-search`
- v0.3.1: 使用 `scripts/replay_v031.py` 适配器

## 运行完整 A/B 测试

详见 specification: `docs/superpowers/specs/2026-06-12-ab-benchmarking-framework-design.md`

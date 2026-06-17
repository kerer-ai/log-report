---
name: build-log-normalizer
description: Normalize CI/CD build analysis JSON files from json-org/ to json/ directory. Applies unified bottleneck naming from pre_build actions, fixes unattributed_seconds to non-negative, preserves all original data. Use when processing build analysis data, fixing data format issues, or normalizing new JSON files.
---

# Build Log Normalizer

将 `json-org/` 中的原始构建分析 JSON 归一化为标准格式，输出到 `json/`。

## 工作流程

```
json-org/*.json  →  normalize.py  →  json/*.json  →  generate.py  →  index.html
   (原始数据)        (归一化)        (标准格式)       (构建看板)      (看板页面)
```

1. 将原始 JSON 文件放入 `json-org/` 目录
2. 执行归一化: `python3 .claude/skills/build-log-normalizer/scripts/normalize.py`
3. 归一化后文件输出到 `json/`
4. 重新生成看板: `python3 generate.py`

## 归一化规则

### 规则 1: bottleneck 仅从 pre_build 提取

`summary.key_bottleneck` 取 `pre_build.actions` 中耗时最长的动作的 `name` 字段。
`summary.key_bottleneck_seconds` 同步为对应耗时。

此规则确保:
- bottleneck 只反映环境准备阶段，不包含 build_phases 的 compilation 等
- 命名与看板卡片中展示的动作名一致

### 规则 2: unattributed_seconds 非负

`summary.unattributed_seconds = max(0, total_duration - pre_build_seconds - build_seconds)`

### 规则 3: 数据完整性

所有原始字段原样保留，仅修正 `summary` 中的:
- `key_bottleneck` / `key_bottleneck_seconds` — 按规则1
- `unattributed_seconds` — 按规则2
- `pre_build_seconds` / `build_seconds` — 刷新为 pre_build/build_phases 实际总和

## 执行

```bash
python3 .claude/skills/build-log-normalizer/scripts/normalize.py
```

支持指定目录:
```bash
python3 .claude/skills/build-log-normalizer/scripts/normalize.py <json-org-dir> <json-output-dir>
```

脚本按 mtime 跳过未变化的文件，只处理有更新的。

## 边界情况

- `builds[]._error` 存在的条目跳过，保持原样
- `pre_build.actions` 为空时 bottleneck 设为空字符串
- `time.duration_seconds` 缺失时跳过 unattributed 计算

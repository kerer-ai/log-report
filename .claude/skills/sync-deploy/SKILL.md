---
name: sync-deploy
description: Full pipeline orchestrator for CI/CD build analysis kanban. Reads repos.txt, fetches latest build logs, AI-analyzes pre-build timing, normalizes JSON, regenerates static page, and pushes to GitHub Pages. Use when user wants to update dashboard data, sync all repos, deploy the kanban, or run the full pipeline. Triggers on: sync and deploy, update dashboard, refresh kanban, pull latest and deploy, 同步并发布, 更新看板, 全量刷新.
---

# Sync & Deploy — 全流程编排

串联数据采集 → AI分析 → 归一化 → 渲染 → 发布，一键刷新看板。

## 工作流

```
repos.txt → pipeline.sh (fetch) → AI分析 (Claude) → normalize.py → generate.py → git push → GitHub Pages
```

## 使用方式

```
/sync-deploy                    # 增量模式：只更新有变化的仓库
/sync-deploy --force-fetch      # 强制模式：无论有无变化都重新fetch
/sync-deploy --quick            # 快速模式：只归一化+渲染+推送（跳过fetch+AI分析）
```

## 执行流程

### Phase 1: 拉取数据

读取 `repos.txt`，对每个仓库执行：

1. 检查缓存：对比 `meta.pr` 与最新 merged PR 号
2. 如果 PR 号不变 → 跳过，复用已有 JSON
3. 如果 PR 号变化 → `fetch_build_logs.py` 拉取完整日志
4. 如果最新 PR 无 passed 构建 → 回退扫描最多 20 个 PR

### Phase 2: AI 分析

对每个 fetch 成功或被标记为需要重分析的仓库，启动后台 Agent：

- 读取 `json-org/<repo>_build_analysis.json`
- 逐构建识别 pre_build 动作（R9 无缝衔接）
- 写入完整 JSON

Agent 分组规则：
| 构建数 | 策略 |
|--------|------|
| >4 builds | 独占 1 个 Agent |
| 2-4 builds | 独占 1 个 Agent |
| 1 build | 2 个仓库合并为 1 个 Agent |

### Phase 3: 校验

每个 Agent 完成后运行 `scripts/validate.py`：

- 检查 R1/R5/R6/R7/R8/R9
- Schema 合规性
- 不合格的仓库自动重分析

### Phase 4: 归一化 + 渲染 + 发布

```bash
python3 .claude/skills/build-log-normalizer/scripts/normalize.py
python3 generate.py
git add -A && git commit -m "sync: update build analysis ($(date +%Y-%m-%d))" && git push
```

## repos.txt 格式

```
# 注释行
https://gitcode.com/Ascend/pytorch
https://gitcode.com/Ascend/MindIE-LLM
```

新增仓库时直接添加 URL，运行 `/sync-deploy` 即自动纳入。

## 关键规则

- 如果 `repos.txt` 不存在，提示用户创建
- fetch 缓存默认开启（`--force-fetch` 可强制全量）
- AI 分析后必须通过 Phase 3 校验才能进入 Phase 4
- 推送前确认 `json/` 目录和 `index.html` 已更新

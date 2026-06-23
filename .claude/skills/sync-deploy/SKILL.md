---
name: sync-deploy
description: Full pipeline orchestrator for CI/CD build analysis kanban. Reads repos.txt, fetches latest build logs, AI-analyzes pre-build timing, normalizes JSON, regenerates static page, and pushes to GitHub Pages. Use when user wants to update dashboard data, sync all repos, deploy the kanban, or run the full pipeline. Triggers on: sync and deploy, update dashboard, refresh kanban, pull latest and deploy, 同步并发布, 更新看板, 全量刷新.
---

# Sync & Deploy — 全流程编排

串联数据采集 → AI分析 → 归一化 → 渲染 → 发布，一键刷新看板。

## 工作流

```
repos.txt → pipeline.sh (fetch+PR检测) → AI分析 (并行Agent) → normalize.py → generate.py → git push → GitHub Pages
```

## 使用方式

```
/sync-deploy                    # 增量模式：检测PR变化，只更新有变化的仓库
/sync-deploy --force-fetch      # 强制模式：全量fetch，但PR未变则复用缓存
/sync-deploy --quick            # 快速模式：只归一化+渲染+推送（跳过fetch+AI分析）
```

## 执行流程

### Phase 0: 准备

1. 读取 `repos.txt`，解析仓库列表
2. 如果是新仓库（不在 `json-org/` 中）：标记为需要 fetch
3. 如果 `--quick` 模式：直接跳到 Phase 4

### Phase 1: PR 变化检测 + 拉取

对 `repos.txt` 中的每个仓库：

1. **检测 PR 变化**：对比 `json-org/<name>_build_analysis.json` 中的 `meta.pr` 与 `gc pr list --state merged -L 1` 的最新 PR 号
2. **PR 未变** → 跳过 fetch，复用 `json-org/` 中已有的分析数据
3. **PR 已变** → `fetch_build_logs.py` 拉取完整日志到临时文件
4. **新仓库** → 直接 fetch
5. **Fetch 成功后**：比较新旧 PR 号
   - PR 真的变了 → 覆盖 `json-org/`，标记为需要 AI 分析
   - PR 相同（--force-fetch 但实际未变）→ **恢复缓存数据**，不标记分析
6. **Fetch 失败**：回退扫描最近 20 个 PR 找 passed 构建；仍失败则保留现有数据
7. **所有已分析数据**：确保工作目录有对应的分析后 JSON 文件

**关键原则：fetch 到临时文件 → 比较 PR → 决定覆盖还是恢复缓存。绝不盲目覆盖已有分析数据。**

### Phase 2: 并行 AI 分析

只对 Phase 1 中标记为"需要分析"的仓库启动 Agent：

1. **统计构建数**，按以下规则分组：

| 构建数 | 策略 | 理由 |
|--------|------|------|
| >4 builds | 独占 1 个 Agent | 日志量大，需完整上下文 |
| 2-4 builds | 独占 1 个 Agent | 标准配置 |
| 1 build | 2 个仓库合并为 1 个 Agent | 降低成本，提高效率 |

2. **并行启动 Agent**（所有 Agent 同时 `run_in_background: true`）：

```
Agent("Analyze <repo>", prompt=<标准分析prompt>)
```

3. **标准分析 Prompt 要素**（每个 Agent 必须收到）：
   - Read `<repo>_build_analysis.json`
   - 逐行阅读 `log_sample`，按两阶段模型识别动作
   - 识别编排器类型（Volcano/Argo/Docker）
   - pod_scheduling MUST be >1s（不是只抓 Running 瞬间）
   - 仅包含实际发生的动作（跳过未使用的 key）
   - R1/R5/R6 校验规则
   - 设置 `meta.analyzed_at` 和 `pre_build.orchestrator`
   - Write completed JSON 回**同一文件路径**

4. **等待所有 Agent 完成**（自动通知）

### Phase 3: 校验与补漏

每个 Agent 完成后，用 `validate.py` 快速验证：

```bash
python3 .claude/skills/gitcode-build-time-analyzer/scripts/validate.py <repo>_build_analysis.json
```

校验规则（R1-R9）：

| 规则 | 检查内容 | 阈值 |
|------|---------|------|
| R1 | `unattributed_seconds >= 0` | 不可为负 |
| R5 | 零耗时动作必须有 evidence | duration==0 且无 evidence → FAIL |
| R6 | pre+build+unatt 约等于 total | 差异 < 1.0s |
| R7 | total_seconds >= 各动作时长和 | 允许 1s 误差 |
| R8 | env_setup 不过度膨胀 | >20s 且缺少 Pod 内子动作 |
| R9 | unattributed 不过大 | > max(10s, total*5%) |

校验失败的处理：

| 症状 | 原因 | 处理 |
|------|------|------|
| `empty > 0` 且 `analyzed_at` 有值 | Agent 写了空模板 | **重分析**：重新启动 Agent，prompt 加 "The current data is WRONG" |
| `analyzed_at` 为 null | Agent 未完成/未写入 | 等待或重启 Agent |
| `pod_scheduling < 1s`（非Docker） | 只测了 Running 瞬间 | **重分析**：强调 pod_scheduling 修复 |
| R6 校验失败 | 计算错误 | **重分析**：要求逐项验证 |
| R9 失败（unattributed 过大） | 日志采样不足/动作遗漏 | 检查 significant_gaps，必要时重分析 |

**重分析 Agent prompt 必须包含**：
> "The current file has [具体问题]. This is WRONG and must be fixed. Re-read the log_sample and fill in EVERY action with actual timing data."

### Phase 4: 归一化 + 渲染 + 发布

```bash
python3 .claude/skills/build-log-normalizer/scripts/normalize.py
python3 generate.py
git add -A && git commit -m "sync: update build analysis ($(date +%Y-%m-%d))" && git push
```

推送前确认：
- `json/` 目录中所有文件均已更新
- `index.html` 中包含所有仓库
- DATA_JSON 中的 repo 数量正确

## repos.txt 格式

```
# 注释行
https://gitcode.com/Ascend/pytorch
https://gitcode.com/Ascend/MindIE-LLM
```

新增仓库时直接添加 URL，运行 `/sync-deploy` 即自动纳入（Phase 1 检测到新仓库自动 fetch）。

### CI Backend 指令

对于使用非 openLiBing CI 的仓库，在 URL 前添加 `# CI_BACKEND:<type>` 注释行：

```
# CI_BACKEND:jenkins
https://gitcode.com/openeuler/kernel
```

支持的 backend 类型：`openlibing`（默认）、`jenkins`。指令仅对紧接的下一个 URL 生效，每个 URL 处理完后自动重置为 `openlibing`。

## 缓存策略

| 场景 | 行为 |
|------|------|
| PR 未变 | 跳过 fetch，复用 `json-org/` 分析数据 |
| PR 已变 | fetch + Agent 分析 |
| --force-fetch 但 PR 未变 | fetch 后检测到 PR 相同 → 恢复缓存 |
| 新仓库 | fetch + Agent 分析 |
| fetch 失败 | 保留 `json-org/` 现有数据，标记为不可更新 |

## 新增仓库完整流程

1. 在 `repos.txt` 添加 URL
2. 运行 `/sync-deploy`
3. Phase 1 自动检测新仓库 → fetch → 标记为需要分析
4. Phase 2 启动 Agent 分析
5. Phase 3 校验
6. Phase 4 归一化 + 渲染 + 发布

## 经验教训

- **MindIE-LLM (10 builds)** 是最重的仓库，Agent 需处理 ~4000 行 log_sample × 10 builds。优先启动
- **Agent 偶尔写空模板**：`analyzed_at` 已设置但 actions 全为空。校验必须检测此模式并触发重分析
- **pod_scheduling < 1s bug**：最常见的数据错误。非 Docker 仓库强制检查
- **Docker 原生仓库** 无 pod_scheduling，正常为 0s
- **CANN 项目仓库**（`cann/*`）无法批量分析——API 限制导致所有构建标记 `_error`
- **Post-build teardown**：Docker 仓库通常有 5-8s 的 CI cleanup 时间（JobStatusPlugin → Finished），这是正常的 unattributed 时间
- **Force-fetch 陷阱**：即使 `--force-fetch`，如果 PR 实际未变，应复用缓存而非重新分析

## 脚本路径

所有脚本使用绝对路径（基于 `$SCRIPT_DIR`），不依赖 cwd：

```
.claude/skills/sync-deploy/scripts/pipeline.sh
.claude/skills/gitcode-build-time-analyzer/scripts/fetch_build_logs.py
.claude/skills/gitcode-build-time-analyzer/scripts/validate.py
.claude/skills/build-log-normalizer/scripts/normalize.py
generate.py
```

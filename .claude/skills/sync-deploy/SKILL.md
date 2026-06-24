---
name: sync-deploy
description: Full pipeline orchestrator for CI/CD build analysis kanban. Reads repos.txt, fetches latest build logs, AI-analyzes pre-build timing, normalizes JSON, regenerates static page, and pushes to GitHub Pages. Use when user wants to update dashboard data, sync all repos, deploy the kanban, or run the full pipeline. Triggers on: sync and deploy, update dashboard, refresh kanban, pull latest and deploy, 同步并发布, 更新看板, 全量刷新.
---

# Sync & Deploy — 全流程编排

串联数据采集 → AI分析 → 归一化 → 渲染 → 发布，一键刷新看板。

## 工作流

```
repos.txt → [AI] URL发现 → [Script] 日志下载 → [AI] 耗时分析 → [Script] 渲染发布
              Stage 1        Stage 2           Stage 3          Stage 4
```

## 使用方式

```
/sync-deploy                    # 增量模式：检测PR变化，只更新有变化的仓库
/sync-deploy --quick            # 快速模式：只归一化+渲染+推送（跳过Stage 1-3）
```

## 执行流程

### Stage 1: AI URL 发现

AI 负责从 PR 评论区识别日志下载链接：

1. 读取 `repos.txt`，解析仓库列表和 `# CI_BACKEND:` 指令
2. 对每个仓库，通过 `gc pr list` 检测最新 merged PR
3. 对比 `json-org/<repo>_build_analysis.json` 中 `meta.pr`：
   - PR 未变 → 跳过
   - PR 已变或新仓库 → AI 读取 `gc pr comments` 原始文本
4. AI 从 PR 评论中提取流水线任务信息：
   - **openlibing**: 识别 HTML 流水线表，提取 task_name / status / detail_url
   - **Jenkins**: 识别 openeuler-ci-bot 门禁表，提取架构 / check_build 状态 / console_url
5. AI 输出 manifest 到 `json-org/<repo>_manifest.json`

### Stage 2: Script 日志下载

```bash
python3 scripts/download.py --manifest json-org/<repo>_manifest.json
```

下载脚本按 `detail_url` 下载原始日志：
- **openlibing**: POST REST API，翻页拼接（500行/页，最多60页）
- **Jenkins**: GET `/consoleText` + GET `/api/json`（元数据）

保存到 `logs/<repo>/pr<NNN>/<task>-<timestamp>.log.gz`，
同时生成 `json-org/<repo>_build_analysis.json`（含 `log_file` 路径 + 空模板）。

### Stage 3: AI 耗时分析

AI 读取 `schema/template.json`（了解结构）→ 读取 `json-org/<repo>_build_analysis.json` → 
读取 `logs/<repo>/pr<NNN>/*.log.gz` 原始日志 → 识别动作耗时 → 
按 `action_catalog` 选择 action key → 应用 R9+R1-R8 质量规则 →
写回完成的分析 JSON。

### Stage 4: Script 归一化 + 渲染 + 发布

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

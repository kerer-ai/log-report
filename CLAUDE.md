# CI/CD 构建分析看板项目

基于 GitCode PR 流水线日志，分析多仓库 CI/CD 构建前置环境准备耗时，生成静态看板页面，
通过 GitHub Pages 发布。

## 快速开始

```bash
/sync-deploy               # 增量刷新：只更新有变化的仓库，自动发布
/sync-deploy --force-fetch # 全量刷新：强制重新拉取所有仓库
/sync-deploy --internal-only # 内部刷新：仅刷新 repos.txt 内部仓库，外部归档数据保持不变
```

一条命令串行采集 → AI分析 → 归一化 → 渲染 → 发布全流程。

### 自动化刷新

通过 GitHub Actions `workflow_dispatch` 手动触发，无需本地 Claude Code 会话：

1. 进入仓库 **Actions** → **Data Refresh Pipeline** → **Run workflow**
2. 可选勾选 `Force re-fetch all repos` 强制全量拉取
3. Workflow 仅刷新 `repos.txt` 中的内部仓库，外部归档数据（`jenkins_console_log_parse`）保持不变

#### 所需 GitHub Secrets

在仓库 `Settings → Secrets and variables → Actions` 中配置：

| Secret | 说明 |
|--------|------|
| `ANTHROPIC_AUTH_TOKEN` | Claude API 认证令牌 |
| `ANTHROPIC_BASE_URL` | API 端点 (如 `https://api.deepseek.com/anthropic`) |
| `ANTHROPIC_MODEL` | 默认模型 (如 `deepseek-v4-pro[1m]`) |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Haiku 模型映射 |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Sonnet 模型映射 |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Opus 模型映射 |
| `GITCODE_TOKEN` | GitCode CLI 认证令牌 |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Agent teams 功能开关 (设为 `1`) |

## 数据流水线

```
repos.txt → sync-deploy (全流程编排)
                ├─ gitcode-build-time-analyzer (fetch + AI分析)
                ├─ build-log-normalizer (归一化)
                ├─ generate.py (渲染)
                └─ git push (发布到 GitHub Pages)
                                              kerer-ai.github.io/log-report
```

## 子命令

| 命令 | 说明 |
|------|------|
| `/sync-deploy` | 全流程：读 repos.txt → fetch → AI分析 → 归一化 → 渲染 → 推送 |
| `/gitcode-build-time-analyzer <url>` | 单仓库：拉取日志 + AI 分析 |
| `/build-log-normalizer` | 仅归一化 + 渲染 |
| `python3 generate.py` | 仅渲染 index.html |

## repos.txt

一行一个 GitCode 仓库 URL，`#` 开头为注释。`/sync-deploy` 按顺序读取，PR 号未变则跳过 fetch。

对于使用 Jenkins CI 的仓库（如 openeuler/kernel），在 URL 前加 `# CI_BACKEND:jenkins` 指令：

```
https://gitcode.com/Ascend/pytorch
# CI_BACKEND:jenkins
https://gitcode.com/openeuler/kernel

```
https://gitcode.com/Ascend/pytorch
https://gitcode.com/Ascend/torchair
https://gitcode.com/Ascend/MindIE-LLM
```

新增仓库直接加一行，运行 `/sync-deploy` 自动纳入。

## 项目结构

```
log_analyze/
├── repos.txt                # 仓库列表
├── generate.py              # 构建脚本：嵌入 JSON → 输出 index.html
├── template.html            # HTML 模板：{{DATA_JSON}} + 内联 CSS/JS
├── index.html               # 看板页面（git tracked，供 Pages 部署）
├── .nojekyll                # 跳过 Jekyll 处理
│
├── json-org/                # 原始数据（AI分析产物）
├── json/                    # 归一化数据
│
├── .claude/skills/
│   ├── sync-deploy/                   # 全流程编排
│   ├── gitcode-build-time-analyzer/   # 获取+AI分析构建日志
│   └── build-log-normalizer/          # 归一化 JSON
│
└── docs/superpowers/
    ├── specs/                         # 设计文档
    └── plans/                         # 实现计划
```

## JSON 数据结构

```
{
  meta: { pr, repo, pipeline_state, fetched_at, analyzed_at, analysis_method }
  builds[]: {
    task_name, status, detail_url,
    time: { start, end, duration_seconds },
    pre_build: {
      total_seconds, pct_of_total, orchestrator,
      actions[]: { key, name, start, end, duration_seconds, evidence }
    },
    build_phases: {
      total_seconds, pct_of_total,
      actions[]: { key, name, duration_seconds }
    },
    summary: { pre_build_seconds, build_seconds, unattributed_seconds,
               key_bottleneck, key_bottleneck_seconds }
  }
}
```

## 看板页面

4 层混合视图，深色 Slate 主题，零外部依赖，响应式布局：

1. **全局状态栏** — 仓库统计 + 搜索/编排器筛选/排序
2. **洞察卡片** — 头号瓶颈、最慢 Top 3、ARM vs x86 对比
3. **Pre-Build 热力排行** — 按瓶颈耗时排序，红/黄/绿色标记
4. **仓库详情卡片** — 每构建可展开查看 pre_build 动作时间线

# CI/CD 构建分析看板项目

基于 GitCode PR 流水线日志，分析多仓库 CI/CD 构建前置环境准备耗时，生成静态看板页面，
通过 GitHub Pages 发布。

## 数据流水线

```
gitcode-build-time-analyzer    build-log-normalizer    generate.py
        ↓                            ↓                    ↓
   json-org/*.json      →       json/*.json      →    index.html
   (AI 分析日志)              (归一化标准格式)        (看板页面)
                                                          ↓
                                                   GitHub Pages
                                              kerer-ai.github.io/log-report
```

### 步骤 1: 获取构建数据

使用 `gitcode-build-time-analyzer` skill 从 GitCode PR 拉取日志并由 AI 分析：

```bash
# 单仓库
/gitcode-build-time-analyzer Ascend/pytorch

# 批量多仓库
/gitcode-build-time-analyzer 分析: Ascend/pytorch, Ascend/torchair, Ascend/MindIE-Motor
```

产物：`json-org/<仓库名>_build_analysis.json`

### 步骤 2: 归一化 JSON

使用 `build-log-normalizer` skill 统一数据格式：

```bash
/build-log-normalizer
```

- 统一 bottleneck 命名（从 pre_build 动作提取中文名称）
- 修正 unattributed_seconds（确保非负）
- 不丢失原始数据

产物：`json/<仓库名>_build_analysis.json`

### 步骤 3: 生成看板

```bash
python3 generate.py
```

产物：`index.html`（自包含，浏览器直接打开）

### 步骤 4: 发布

```bash
git add -A && git commit -m "update data" && git push
```

GitHub Pages 自动部署到 `https://kerer-ai.github.io/log-report/`

## 项目结构

```
log_analyze/
├── generate.py              # 构建脚本：嵌入 JSON 数据到模板，输出 index.html
├── template.html            # HTML 模板：{{DATA_JSON}} 占位符 + 内联 CSS/JS
├── index.html               # 生成的看板页面（git tracked，供 Pages 部署）
├── .nojekyll                # 跳过 GitHub Pages 的 Jekyll 处理
│
├── json-org/                # 原始分析结果（gitcode-build-time-analyzer 产物）
│   └── *_build_analysis.json
│
├── json/                    # 归一化后数据（build-log-normalizer 产物）
│   └── *_build_analysis.json
│
├── .claude/
│   └── skills/
│       ├── gitcode-build-time-analyzer/   # 获取+AI分析构建日志
│       └── build-log-normalizer/          # 归一化 JSON 格式
│
└── docs/
    └── superpowers/
        ├── specs/                        # 设计文档
        └── plans/                        # 实现计划
```

## JSON 数据结构

每个文件包含一个 PR 流水线的完整分析：

```
{
  meta: { pr, repo, pipeline_state, fetched_at, analyzed_at, ... }
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

4 层混合视图：

1. **全局状态栏** — 仓库统计 + 搜索/编排器筛选/排序
2. **洞察卡片** — 头号瓶颈、最慢 Top 3、ARM vs x86 对比
3. **Pre-Build 热力排行** — 按瓶颈耗时排序，颜色标记严重程度
4. **仓库详情卡片** — 每构建可展开查看 pre_build 动作时间线

深色主题（Slate 色系），响应式布局，零外部依赖。

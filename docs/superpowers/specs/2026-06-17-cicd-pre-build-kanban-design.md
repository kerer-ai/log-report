# CI/CD 构建前置环境准备看板 — 设计文档

## 背景

`json/` 目录存放多仓库 CI/CD 构建分析 JSON 数据，每个文件包含 PR 流水线的 `pre_build`（环境准备）和 `build_phases`（编译构建）的结构化耗时分析。需要一个**静态 HTML 看板页面**来可视化这些数据，核心关注**构建前置环境准备时长**。

## 目标用户与场景

- **开发人员/PR 提交者**：查看自己仓库的环境准备是否正常，定位慢动作
- **CI/CD 维护者/DevOps**：横向对比仓库间的编排器表现（Volcano/Argo/Docker），发现系统性瓶颈
- **技术管理者**：宏观了解各仓库构建健康度

核心场景：**快速扫一眼 → 发现瓶颈动作（Pod调度慢/镜像拉取慢等）→ 点击跳转原始流水线处理。**

## 数据模型

每个 JSON 文件结构：

```
meta: { pr, repo, pr_url, pipeline_name, pipeline_state, pipeline_url, fetched_at, analyzed_at }
builds[]: {
  task_name, stage, status, detail_url, time: {start, end, duration_seconds},
  pre_build: { total_seconds, pct_of_total, orchestrator, actions: [{key, name, start, end, duration_seconds, evidence}] },
  build_phases: { total_seconds, pct_of_total, actions: [{key, name, duration_seconds}] },
  summary: { pre_build_seconds, build_seconds, unattributed_seconds, key_bottleneck, key_bottleneck_seconds }
}
```

### 边界情况

- `analyzed_at` 可能为 `null` → 展示"未分析"
- `builds[]._error` 存在时 → 整条构建标记为错误状态，跳过常规展示
- `pre_build.actions[]` 可为空 → 只显示 pre_build 总耗时
- `unattributed_seconds` 保证 ≥0（上游已修复负数问题）
- 编排器类型来自 `pre_build.orchestrator`（volcano / argo / docker / 空字符串）

## 架构决策：构建时嵌入

- **Python 脚本 `generate.py`** 读取 `json/*.json`，将数据序列化为 JSON 嵌入 HTML 模板的 `{{DATA_JSON}}` 占位符，输出 `index.html`
- 新增 JSON 文件后执行 `python3 generate.py` 即可重新生成
- 单文件 HTML，无外部依赖，直接用浏览器打开
- 无需本地服务器（避免 `file://` + `fetch()` 的 CORS 问题）

### 文件结构

```
log_analyze/
├── generate.py          # 构建脚本
├── template.html        # HTML 模板（含 {{DATA_JSON}} 占位符）
├── index.html           # 生成的看板页面（gitignore）
└── json/                # 数据目录（持续新增）
```

## 页面设计：4 层混合视图

### 第 1 层：全局状态栏

功能：标题 + 统计摘要 + 筛选控制

- **标题行**：看板名称 + 数据更新时间（取所有 `fetched_at` 最大值格式化）
- **统计行**：仓库数 / 构建任务数 / 通过率，失败数 > 0 时红色高亮
- **筛选栏**：仓库名搜索（文本输入实时过滤） + 编排器下拉（全部/Volcano/Argo/Docker） + 排序下拉（pre_build 耗时降序 / 总耗时降序 / pre_build 占比降序）

### 第 2 层：洞察卡片

功能：4 张自动计算的摘要卡片

| 卡片 | 内容 | 计算方式 |
|------|------|----------|
| 仓库/任务 | 仓库数 / 构建任务数 / 通过状态 | 基础统计 |
| 头号瓶颈 | 瓶颈动作名 + 覆盖仓库数 + 最长耗时 | 统计 `summary.key_bottleneck` 出现频次 |
| 最慢 Pre-Build Top 3 | 仓库名 + 动作名 + 耗时 | 跨仓库按动作耗时降序取前 3 |
| ARM vs x86 对比 | ARM/x86 平均 pre_build 耗时 + 倍数差 | 按任务名含 `arm`/`ARM` vs `x86`/`X86` 分组 |

### 第 3 层：Pre-Build 耗时热力排行

功能：可过滤的横向排行表

- 默认只显示 pre_build 耗时 > 60s 或占比 > 30% 的构建（切换「显示全部」可看全部）
- 列：左侧彩色圆点（红>180s/>50% / 黄 60-180s/30-50% / 绿<60s/<30%）、仓库、任务名、总耗时、pre_build 占比、瓶颈动作（红色>100s）、瓶颈耗时、跳转箭头
- 按瓶颈耗时降序排列，同瓶颈按占比降序
- 仓库名过长截断 + hover 全名
- 底部汇总行：筛选条数 / 总条数、pre_build 合计耗时、瓶颈覆盖仓库数

### 第 4 层：仓库详情卡片流

功能：每仓库一张可折叠卡片，内部每构建一行可展开

- **卡片头部**：仓库名 + PR 号（链接）、构建通过数、pipeline 状态、收起/展开按钮
- **构建摘要行**（默认折叠）：任务名 + 总耗时 + pre/build 占比条（蓝=pre / 绿=build / 灰=unattributed）+ 时间范围
- **展开区域**：pre_build 动作表格（瓶颈动作标 ⚠️ 红色）+ build 阶段简要
- **卡片底部**：该仓库所有构建的 pre/build/unattributed 合计秒数和占比
- 卡片头部滚动时 sticky 吸顶

### 交互行为

- 第 3 层筛选器切换时，仅影响排行表，不影响第 4 层仓库卡片
- 第 1 层筛选器（搜索/编排器/排序）影响第 3 层和第 4 层
- 第 4 层每个构建默认折叠，点击展开；卡片级别「展开全部/收起全部」
- 点击第 3 层跳转箭头或第 4 层构建摘要行中的链接 → 新标签页打开 `detail_url`

## 视觉设计

深色专业主题（Slate 色系），类似 Grafana/Datadog：

- 背景：`#0f172a` (slate-900)
- 卡片背景：`#1e293b` (slate-800)
- 边框：`#334155` (slate-700)
- 主文字：`#f1f5f9` (slate-100)，次要文字：`#94a3b8` (slate-400)
- Pre-Build 蓝色：`#3b82f6`，Build 绿色：`#22c55e`，Unattributed 灰色：`#64748b`
- 瓶颈红色：`#ef4444`（>100s），橙色：`#f59e0b`（30-100s）
- 尖角卡片 + 细圆角按钮，等宽字体用于耗时数字

## 技术实现

- **generate.py**：Python 标准库（`json`, `glob`, `os`, `datetime`），读取 `json/*.json` → 聚合计算 → 替换模板 → 输出 `index.html`
- **template.html**：单文件包含内联 `<style>` + `<script>`，脚本从全局变量 `__EMBEDDED_DATA__` 读取数据后渲染 DOM
- 响应式：CSS Grid `auto-fill, minmax(340px, 1fr)`，移动端单列堆叠
- 无外部依赖，无构建工具

## 验证

1. 运行 `python3 generate.py` 生成 `index.html`
2. 浏览器直接打开 `index.html`，无需服务器
3. 确认 9 仓库、~30 构建任务正确展示
4. 确认第 2 层洞察卡片数据计算正确
5. 确认第 3 层筛选和排序功能正常
6. 确认第 4 层展开/折叠交互正常
7. 确认 `.error` 构建显示错误提示
8. 在 `json/` 新增一个文件后重新运行 generate.py，验证自动纳入
9. 响应式检查：~400px、~768px、~1440px 宽度

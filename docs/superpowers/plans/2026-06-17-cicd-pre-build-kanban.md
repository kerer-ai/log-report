# CI/CD 构建前置环境准备看板 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个静态 HTML 看板页面，可视化多仓库 CI/CD 构建前置环境准备耗时数据。

**Architecture:** Python 脚本 `generate.py` 读取 `json/*.json`，将数据嵌入 `template.html` 的占位符，输出自包含的 `index.html`。HTML 内联 CSS + JS，无外部依赖，浏览器直接打开。

**Tech Stack:** Python 3 (stdlib only: json, glob, os, datetime), HTML5, CSS3 (Grid + Custom Properties), Vanilla JavaScript (ES6+)

## Global Constraints

- 零外部依赖：HTML 不引用任何 CDN 资源，Python 只用标准库
- `index.html` 必须支持 `file://` 协议直接打开
- 新增 JSON 文件后只需运行 `python3 generate.py` 即可重新生成
- 深色主题 Slate 色系，颜色令牌与设计文档一致
- 响应式：~400px 单列 / ~768px 双列 / ~1440px 多列
- 所有交互行为纯 JS 实现，无框架

## File Structure

```
log_analyze/
├── generate.py          # CREATE: 构建脚本
├── template.html        # CREATE: HTML 模板
├── index.html           # GENERATED: 看板页面
└── json/                # EXISTING: 数据目录
```

### 文件职责

| 文件 | 职责 |
|------|------|
| `generate.py` | glob `json/*.json` → 合并数据 → 计算衍生字段 → 替换模板占位符 → 输出 `index.html` |
| `template.html` | 完整 HTML 模板，含 3 段：`<style>`（视觉） + `<body>`（结构） + `<script>`（逻辑） |
| `index.html` | 生成产物，不提交到版本控制 |

---

### Task 1: 创建 `generate.py` 构建脚本

**Files:**
- Create: `generate.py`

**Interfaces:**
- Produces: 执行 `python3 generate.py` 输出 `index.html` 到当前目录
- Consumes: `json/*.json` 数据文件, `template.html` 模板文件

- [ ] **Step 1: 编写数据加载与合并逻辑**

```python
#!/usr/bin/env python3
"""CI/CD Build Analysis Kanban Generator.

Reads all JSON files from json/, embeds data into template.html,
and outputs a self-contained index.html.
"""

import json
import glob
import os
from datetime import datetime


def load_all_data(json_dir="json"):
    """Load and merge all build analysis JSON files.

    Returns:
        list[dict]: Sorted list of repo data, each with:
            - All original meta fields
            - builds: list of build dicts
            - _filename: source filename
            - _has_error: bool, True if any build has _error
    """
    files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    repos = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_filename"] = os.path.basename(fpath)
        data["_has_error"] = any("_error" in b for b in data.get("builds", []))
        repos.append(data)

    # Sort: repos with errors first, then by build count descending
    repos.sort(key=lambda r: (not r["_has_error"], -len(r.get("builds", []))))
    return repos


def compute_derived_fields(repos):
    """Add computed fields to each repo and build for easier frontend rendering.

    Adds to each repo:
        - _repo_short: short repo name (e.g. "MindIE-LLM")
        - _total_builds: total build count
        - _passed_builds: count of passed builds
        - _failed_builds: count of failed builds
        - _max_fetched_at: latest fetched_at across builds

    Adds to each build:
        - _arch: "ARM" | "x86" | "unknown" derived from task_name
        - _pre_build_pct: pre_build.total_seconds / time.duration_seconds * 100
    """
    for repo in repos:
        builds = repo.get("builds", [])
        repo["_repo_short"] = repo["meta"]["repo"].split("/")[-1]
        repo["_total_builds"] = len(builds)
        repo["_passed_builds"] = sum(1 for b in builds if b.get("status") == "passed")
        repo["_failed_builds"] = sum(1 for b in builds if b.get("status") == "failed")
        repo["_max_fetched_at"] = repo["meta"].get("fetched_at", "")

        for build in builds:
            if "_error" in build:
                build["_arch"] = "unknown"
                build["_pre_build_pct"] = 0
                continue

            task_lower = build.get("task_name", "").lower()
            if "arm" in task_lower or "aarch" in task_lower:
                build["_arch"] = "ARM"
            elif "x86" in task_lower:
                build["_arch"] = "x86"
            else:
                build["_arch"] = "unknown"

            dur = build.get("time", {}).get("duration_seconds", 1)
            pre = build.get("pre_build", {}).get("total_seconds", 0)
            build["_pre_build_pct"] = round(pre / dur * 100, 1) if dur > 0 else 0

    return repos


def generate(repos):
    """Generate index.html from template and data."""
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    data_json = json.dumps(repos, ensure_ascii=False)
    html = template.replace("{{DATA_JSON}}", data_json)

    output_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    total_builds = sum(len(r.get("builds", [])) for r in repos)
    print(f"Generated index.html: {len(repos)} repos, {total_builds} builds → {output_path}")


if __name__ == "__main__":
    repos = load_all_data()
    repos = compute_derived_fields(repos)
    generate(repos)
```

- [ ] **Step 2: 验证 generate.py 可运行**

```bash
cd /home/wangsike/workspace/tmp/log_analyze && python3 generate.py
```

Expected: `Generated index.html: X repos, Y builds → .../index.html`

- [ ] **Step 3: 验证 index.html 包含嵌入数据**

```bash
python3 -c "
import json
with open('index.html') as f:
    html = f.read()
# Verify the placeholder was replaced
assert '{{DATA_JSON}}' not in html, 'Template placeholder not replaced'
assert '__EMBEDDED_DATA__' in html, 'No embedded data found'
# Verify valid JSON in the data
import re
match = re.search(r'const __EMBEDDED_DATA__ = (\[.*?\]);', html, re.DOTALL)
assert match, 'Cannot find __EMBEDDED_DATA__ array'
data = json.loads(match.group(1))
print(f'OK: {len(data)} repos embedded')
for r in data:
    builds = len(r.get('builds', []))
    short = r.get('_repo_short', '?')
    print(f'  {short}: {builds} builds')
"
```

- [ ] **Step 4: Commit**

```bash
git add generate.py index.html
git commit -m "feat: add generate.py build script and initial index.html output"
```

---

### Task 2: 创建 `template.html` — HTML 结构与 CSS 样式

**Files:**
- Create: `template.html`

**Interfaces:**
- Produces: 完整 HTML 模板，`<body>` 包含 4 层布局的 DOM 骨架，`<style>` 包含完整视觉系统
- Consumes: 无（独立文件）

- [ ] **Step 1: 编写 HTML 骨架**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CI/CD 构建看板</title>
</head>
<body>

<!-- Layer 1: Header -->
<header class="header">
  <div class="header-top">
    <h1 class="header-title">🔧 CI/CD 环境准备 & 构建分析看板</h1>
    <span class="header-time" id="updateTime">—</span>
  </div>
  <div class="header-stats" id="headerStats"></div>
  <div class="header-controls">
    <input type="text" id="searchInput" class="control-search" placeholder="🔍 搜索仓库...">
    <select id="orchestratorFilter" class="control-select">
      <option value="all">编排器: 全部</option>
    </select>
    <select id="sortSelect" class="control-select">
      <option value="pre_build_desc">排序: pre_build 耗时 ↓</option>
      <option value="total_desc">排序: 总耗时 ↓</option>
      <option value="pre_build_pct_desc">排序: pre_build 占比 ↓</option>
    </select>
  </div>
</header>

<!-- Layer 2: Insight Cards -->
<section class="insights" id="insights"></section>

<!-- Layer 3: Pre-Build Ranking -->
<section class="ranking" id="ranking"></section>

<!-- Layer 4: Repository Detail Cards -->
<section class="repo-cards" id="repoCards"></section>

<!-- Embedded Data -->
<script>
const __EMBEDDED_DATA__ = {{DATA_JSON}};
</script>

</body>
</html>
```

- [ ] **Step 2: 编写 CSS 变量与基础样式**

```css
<style>
:root {
  --bg: #0f172a;
  --card-bg: #1e293b;
  --border: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --blue: #3b82f6;
  --green: #22c55e;
  --red: #ef4444;
  --amber: #f59e0b;
  --pre-build: #3b82f6;
  --build: #22c55e;
  --unattributed: #475569;
  --radius: 8px;
  --radius-sm: 4px;
  --shadow: 0 1px 3px rgba(0,0,0,0.3);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
  background: var(--bg);
  color: var(--text-primary);
  line-height: 1.5;
  padding: 16px 20px 40px;
  max-width: 1600px;
  margin: 0 auto;
}

/* === HEADER === */
.header { margin-bottom: 20px; }
.header-top {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 8px;
}
.header-title { font-size: 1.5rem; font-weight: 700; }
.header-time { color: var(--text-muted); font-size: 0.85rem; }

.header-stats {
  display: flex; gap: 24px; margin-bottom: 12px;
  font-size: 0.95rem; color: var(--text-secondary);
}
.header-stats .stat-value { font-weight: 700; font-size: 1.2rem; }
.header-stats .stat-label { margin-left: 4px; }
.stat-pass { color: var(--green); }
.stat-fail { color: var(--red); }

.header-controls {
  display: flex; gap: 10px; flex-wrap: wrap;
}
.control-search, .control-select {
  background: var(--card-bg); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 6px 12px; font-size: 0.9rem;
}
.control-search { min-width: 180px; }
.control-search::placeholder { color: var(--text-muted); }
.control-select { cursor: pointer; }

/* === INSIGHTS === */
.insights {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px; margin-bottom: 24px;
}
.insight-card {
  background: var(--card-bg); border-radius: var(--radius);
  padding: 16px; border-left: 3px solid var(--border);
  box-shadow: var(--shadow);
}
.insight-card:nth-child(1) { border-left-color: var(--blue); }
.insight-card:nth-child(2) { border-left-color: var(--red); }
.insight-card:nth-child(3) { border-left-color: var(--amber); }
.insight-card:nth-child(4) { border-left-color: #a855f7; }

.insight-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.insight-value { font-size: 2rem; font-weight: 700; margin: 4px 0; }
.insight-sub { font-size: 0.8rem; color: var(--text-secondary); }

/* === RANKING TABLE === */
.ranking { margin-bottom: 24px; }
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.section-title { font-size: 1.1rem; font-weight: 600; }
.section-toggle { font-size: 0.8rem; color: var(--blue); cursor: pointer; background: none; border: none; }

.ranking-table {
  width: 100%; border-collapse: collapse;
  background: var(--card-bg); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
}
.ranking-table th {
  text-align: left; padding: 10px 12px; font-size: 0.8rem;
  color: var(--text-muted); text-transform: uppercase;
  border-bottom: 1px solid var(--border);
}
.ranking-table td {
  padding: 8px 12px; font-size: 0.9rem;
  border-bottom: 1px solid var(--border);
}
.ranking-table tr:last-child td { border-bottom: none; }
.ranking-table tr:hover { background: rgba(255,255,255,0.03); }

.dot-red { color: var(--red); font-size: 1.2rem; }
.dot-yellow { color: var(--amber); font-size: 1.2rem; }
.dot-green { color: var(--green); font-size: 1.2rem; }

.bottleneck-red { color: var(--red); font-weight: 700; }
.bottleneck-amber { color: var(--amber); font-weight: 600; }
.bottleneck-gray { color: var(--text-secondary); }

.repo-link { color: var(--blue); text-decoration: none; }
.repo-link:hover { text-decoration: underline; }
.detail-arrow { color: var(--text-muted); text-decoration: none; font-size: 1.1rem; }
.detail-arrow:hover { color: var(--blue); }

.ranking-summary {
  display: flex; gap: 20px; padding: 10px 12px;
  font-size: 0.8rem; color: var(--text-muted);
  background: rgba(0,0,0,0.2); border-radius: 0 0 var(--radius) var(--radius);
}

/* === REPO CARDS === */
.repo-cards { display: flex; flex-direction: column; gap: 16px; }

.repo-card {
  background: var(--card-bg); border-radius: var(--radius);
  box-shadow: var(--shadow); overflow: hidden;
}
.repo-card-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; position: sticky; top: 0;
  background: var(--card-bg); z-index: 10;
}
.repo-card-header:hover { background: rgba(255,255,255,0.03); }

.repo-name { font-weight: 700; font-size: 1.05rem; }
.repo-meta { font-size: 0.8rem; color: var(--text-secondary); }
.repo-toggle { font-size: 0.8rem; color: var(--blue); background: none; border: none; cursor: pointer; }

.build-item {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: background 0.15s;
}
.build-item:last-child { border-bottom: none; }
.build-item:hover { background: rgba(255,255,255,0.02); }

.build-summary {
  display: flex; align-items: center; gap: 12px;
}
.build-task-name { font-weight: 600; font-size: 0.9rem; min-width: 180px; }
.build-total-time { font-size: 0.85rem; color: var(--text-secondary); min-width: 70px; }

.build-bar-wrapper { flex: 1; display: flex; align-items: center; gap: 6px; }
.build-bar {
  height: 8px; border-radius: 4px; display: flex; overflow: hidden;
  flex: 1; min-width: 100px; background: var(--unattributed);
}
.build-bar-pre { background: var(--pre-build); height: 100%; }
.build-bar-build { background: var(--build); height: 100%; }

.build-bar-label { font-size: 0.7rem; color: var(--text-muted); white-space: nowrap; }

.build-status { font-size: 0.8rem; font-weight: 600; }
.build-status.passed { color: var(--green); }
.build-status.failed { color: var(--red); }

/* Expandable build detail */
.build-detail {
  max-height: 0; overflow: hidden;
  transition: max-height 0.3s ease;
}
.build-detail.open { max-height: 600px; }

.build-detail-inner {
  padding: 12px 0 0 0; margin-top: 10px;
  border-top: 1px solid var(--border);
}

.action-table {
  width: 100%; border-collapse: collapse; font-size: 0.85rem;
}
.action-table th {
  text-align: left; padding: 4px 8px; color: var(--text-muted);
  font-weight: 500; font-size: 0.75rem; border-bottom: 1px solid var(--border);
}
.action-table td { padding: 4px 8px; }
.action-warn { color: var(--red); font-weight: 600; }

.repo-card-footer {
  padding: 10px 16px; font-size: 0.8rem; color: var(--text-muted);
  border-top: 1px solid var(--border); background: rgba(0,0,0,0.15);
}

/* Error state */
.build-error {
  color: var(--red); padding: 8px 16px; font-size: 0.85rem;
}

/* Responsive */
@media (max-width: 768px) {
  body { padding: 10px; }
  .header-title { font-size: 1.2rem; }
  .insights { grid-template-columns: repeat(2, 1fr); }
  .build-summary { flex-wrap: wrap; }
  .build-task-name { min-width: auto; flex: 1; }
  .ranking-table { font-size: 0.8rem; }
  .ranking-table th:nth-child(4),
  .ranking-table td:nth-child(4) { display: none; }
}

@media (max-width: 480px) {
  .insights { grid-template-columns: 1fr; }
  .header-controls { flex-direction: column; }
  .ranking-table th:nth-child(3),
  .ranking-table td:nth-child(3) { display: none; }
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add template.html
git commit -m "feat: add template.html with HTML structure and CSS styling"
```

---

### Task 3: 添加 JavaScript 数据渲染逻辑

**Files:**
- Modify: `template.html` — 在 `</style>` 后、`<script>` 内添加渲染逻辑

**Interfaces:**
- Consumes: `__EMBEDDED_DATA__` 全局变量（由 generate.py 注入）
- Produces: 完整的 DOM 渲染（4 层视图）

- [ ] **Step 1: 添加工具函数与数据准备**

在 `<script>` 标签内，`__EMBEDDED_DATA__` 声明之后添加：

```javascript
// ── Utility Functions ──

function fmtDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const s = Math.round(seconds);
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return sec > 0 ? m + 'm' + sec + 's' : m + 'm';
}

function fmtTime(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  } catch { return '—'; }
}

function fmtDateTimeShort(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit' });
  } catch { return '—'; }
}

function repoShortName(repo) {
  return repo._repo_short || repo.meta.repo.split('/').pop();
}

// Flatten all builds with repo context
function allBuilds(repos) {
  const result = [];
  repos.forEach(repo => {
    (repo.builds || []).forEach(build => {
      result.push({ repo, build });
    });
  });
  return result;
}

// Get valid builds (no _error, has time)
function validBuilds(repos) {
  return allBuilds(repos).filter(({build}) => !build._error && build.time);
}

// ── Render Layer 1: Header ──

function renderHeader(repos) {
  const builds = validBuilds(repos);
  const totalRepos = repos.length;
  const totalBuilds = builds.length;
  const failedCount = builds.filter(({build}) => build.status === 'failed').length;

  // Update time
  const times = repos.map(r => r.meta.fetched_at).filter(Boolean).sort();
  const latest = times.length > 0 ? times[times.length - 1] : null;
  document.getElementById('updateTime').textContent = latest
    ? '更新于 ' + fmtTime(latest)
    : '';

  // Stats line
  const passClass = failedCount === 0 ? 'stat-pass' : 'stat-fail';
  const passText = failedCount === 0 ? '全部通过' : failedCount + ' 失败';
  document.getElementById('headerStats').innerHTML =
    `<span><span class="stat-value">${totalRepos}</span><span class="stat-label">仓库</span></span>` +
    `<span><span class="stat-value">${totalBuilds}</span><span class="stat-label">构建任务</span></span>` +
    `<span class="${passClass}"><span class="stat-value">${passText}</span></span>`;

  // Orchestrator filter options
  const orchestrators = new Set();
  builds.forEach(({build}) => {
    const o = build.pre_build?.orchestrator;
    if (o) orchestrators.add(o);
  });
  const sel = document.getElementById('orchestratorFilter');
  Array.from(orchestrators).sort().forEach(o => {
    const opt = document.createElement('option');
    opt.value = o;
    opt.textContent = '编排器: ' + o;
    sel.appendChild(opt);
  });
}

// ── Render Layer 2: Insight Cards ──

function renderInsights(repos) {
  const builds = validBuilds(repos);
  if (builds.length === 0) return;

  // Card 1: repo/task overview (done in header, skip or show different info)
  // Card 2: top bottleneck
  const bottleneckCounts = {};
  builds.forEach(({build}) => {
    const bn = build.summary?.key_bottleneck;
    if (bn) bottleneckCounts[bn] = (bottleneckCounts[bn] || 0) + 1;
  });
  let topBottleneck = '';
  let topBottleneckCount = 0;
  let topBottleneckRepos = 0;
  let topBottleneckMax = 0;
  let topBottleneckMaxRepo = '';
  for (const [bn, count] of Object.entries(bottleneckCounts)) {
    if (count > topBottleneckCount) {
      topBottleneck = bn;
      topBottleneckCount = count;
    }
  }
  // Count repos affected and find max
  const affectedRepos = new Set();
  builds.forEach(({repo, build}) => {
    if (build.summary?.key_bottleneck === topBottleneck) {
      affectedRepos.add(repo._repo_short);
      const s = build.summary?.key_bottleneck_seconds || 0;
      if (s > topBottleneckMax) {
        topBottleneckMax = s;
        topBottleneckMaxRepo = repo._repo_short;
      }
    }
  });
  topBottleneckRepos = affectedRepos.size;

  const bnDisplay = topBottleneck.replace(/_/g, ' ');

  // Card 3: Top 3 slowest pre-build actions
  const allActions = [];
  builds.forEach(({repo, build}) => {
    const actions = build.pre_build?.actions || [];
    actions.forEach(a => {
      allActions.push({ repo: repo._repo_short, task: build.task_name, action: a.name, seconds: a.duration_seconds });
    });
  });
  allActions.sort((a, b) => b.seconds - a.seconds);
  const top3 = allActions.slice(0, 3);

  // Card 4: ARM vs x86 comparison
  const armBuilds = builds.filter(({build}) => build._arch === 'ARM');
  const x86Builds = builds.filter(({build}) => build._arch === 'x86');
  const armAvg = armBuilds.length > 0
    ? Math.round(armBuilds.reduce((s, {build}) => s + (build.pre_build?.total_seconds || 0), 0) / armBuilds.length)
    : 0;
  const x86Avg = x86Builds.length > 0
    ? Math.round(x86Builds.reduce((s, {build}) => s + (build.pre_build?.total_seconds || 0), 0) / x86Builds.length)
    : 0;
  const ratio = x86Avg > 0 ? (armAvg / x86Avg).toFixed(1) : '—';

  document.getElementById('insights').innerHTML =
    `<div class="insight-card">
      <div class="insight-label">仓库 / 任务</div>
      <div class="insight-value">${repos.length} <span style="font-size:0.7em;color:var(--text-muted)">/</span> ${builds.length}</div>
      <div class="insight-sub">${builds.filter(({build}) => build.status === 'failed').length === 0 ? '🟢 全部通过' : '🔴 存在失败'}</div>
    </div>` +
    `<div class="insight-card">
      <div class="insight-label">头号瓶颈</div>
      <div class="insight-value" style="font-size:1.2rem;">${bnDisplay}</div>
      <div class="insight-sub">覆盖 ${topBottleneckRepos}/${repos.length} 仓库 · 最长 ${fmtDuration(topBottleneckMax)} (${topBottleneckMaxRepo})</div>
    </div>` +
    `<div class="insight-card">
      <div class="insight-label">最慢 Pre-Build Top 3</div>
      <div class="insight-sub" style="margin-top:4px;">
        ${top3.map((a, i) => `<div>${i+1}. ${a.repo} · ${a.action} <b>${fmtDuration(a.seconds)}</b></div>`).join('')}
      </div>
    </div>` +
    `<div class="insight-card">
      <div class="insight-label">ARM vs x86 Pre-Build</div>
      <div class="insight-value" style="font-size:1.1rem;">ARM ${fmtDuration(armAvg)} / x86 ${fmtDuration(x86Avg)}</div>
      <div class="insight-sub">ARM 比 x86 慢 ${ratio}x · ARM ${armBuilds.length}任务 x86 ${x86Builds.length}任务</div>
    </div>`;
}
```

- [ ] **Step 2: 添加第 3 层排行表渲染**

```javascript
// ── Render Layer 3: Pre-Build Ranking Table ──

let rankingShowAll = false;

function dotClass(build) {
  const pre = build.pre_build?.total_seconds || 0;
  const pct = build._pre_build_pct || 0;
  if (pre > 180 || pct > 50) return 'dot-red';
  if (pre > 60 || pct > 30) return 'dot-yellow';
  return 'dot-green';
}

function bottleneckClass(seconds) {
  if (seconds > 100) return 'bottleneck-red';
  if (seconds > 30) return 'bottleneck-amber';
  return 'bottleneck-gray';
}

function renderRanking(repos) {
  let builds = validBuilds(repos);
  if (builds.length === 0) { document.getElementById('ranking').innerHTML = ''; return; }

  // Filter: only slow ones by default
  if (!rankingShowAll) {
    builds = builds.filter(({build}) => {
      const pre = build.pre_build?.total_seconds || 0;
      const pct = build._pre_build_pct || 0;
      return pre > 60 || pct > 30;
    });
  }

  // Sort by bottleneck seconds descending
  builds.sort((a, b) => {
    const sa = a.build.summary?.key_bottleneck_seconds || 0;
    const sb = b.build.summary?.key_bottleneck_seconds || 0;
    if (sb !== sa) return sb - sa;
    return (b.build._pre_build_pct || 0) - (a.build._pre_build_pct || 0);
  });

  const rows = builds.map(({repo, build}) => {
    const dot = dotClass(build);
    const pre = build.pre_build?.total_seconds || 0;
    const pct = build._pre_build_pct || 0;
    const bn = (build.summary?.key_bottleneck || '').replace(/_/g, ' ');
    const bnSec = build.summary?.key_bottleneck_seconds || 0;
    const bnCls = bottleneckClass(bnSec);
    const dur = build.time?.duration_seconds || 0;
    const url = build.detail_url || '';

    return `<tr>
      <td><span class="${dot}">●</span></td>
      <td><span title="${repo.meta.repo}">${repo._repo_short}</span></td>
      <td>${build.task_name}</td>
      <td>${fmtDuration(dur)}</td>
      <td>${pct}%</td>
      <td class="${bnCls}">${bn}</td>
      <td class="${bnCls}">${fmtDuration(bnSec)}</td>
      <td>${url ? '<a href="' + url + '" target="_blank" class="detail-arrow" title="跳转流水线">→</a>' : ''}</td>
    </tr>`;
  }).join('');

  const totalPre = builds.reduce((s, {build}) => s + (build.pre_build?.total_seconds || 0), 0);
  const allCount = validBuilds(repos).length;
  const affectedRepos = new Set(builds.map(({repo}) => repo._repo_short)).size;

  document.getElementById('ranking').innerHTML = `
    <div class="section-header">
      <span class="section-title">⏱️ Pre-Build 环境准备耗时排行</span>
      <button class="section-toggle" onclick="toggleRanking()">${rankingShowAll ? '仅显示慢构建' : '显示全部'}</button>
    </div>
    <table class="ranking-table">
      <thead><tr>
        <th></th><th>仓库</th><th>任务名</th><th>总耗时</th><th>Pre%</th><th>瓶颈动作</th><th>耗时</th><th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="ranking-summary">
      <span>显示 ${builds.length}/${allCount} 条</span>
      <span>Pre-Build 合计: ${fmtDuration(totalPre)}</span>
      <span>瓶颈覆盖: ${affectedRepos}/${repos.length} 仓库</span>
    </div>`;
}

function toggleRanking() {
  rankingShowAll = !rankingShowAll;
  renderRanking(__EMBEDDED_DATA__);
}
```

- [ ] **Step 3: 添加第 4 层仓库详情渲染**

```javascript
// ── Render Layer 4: Repository Detail Cards ──

function renderRepoCards(repos) {
  const cards = repos.map(repo => renderRepoCard(repo)).join('');
  document.getElementById('repoCards').innerHTML = cards;
}

function renderRepoCard(repo) {
  const builds = repo.builds || [];
  const shortName = repo._repo_short;
  const passedCount = repo._passed_builds || 0;
  const totalCount = repo._total_builds || builds.length;
  const state = repo.meta.pipeline_state || '';
  const prUrl = repo.meta.pr_url || '#';
  const pr = repo.meta.pr;

  const buildItems = builds.map(b => renderBuildItem(b, repo)).join('');

  // Footer summary
  const validB = builds.filter(b => !b._error && b.time);
  const totalPre = validB.reduce((s, b) => s + (b.pre_build?.total_seconds || 0), 0);
  const totalBuild = validB.reduce((s, b) => s + (b.build_phases?.total_seconds || 0), 0);
  const totalUnattr = validB.reduce((s, b) => s + (b.summary?.unattributed_seconds || 0), 0);
  const totalAll = totalPre + totalBuild + totalUnattr;
  const prePct = totalAll > 0 ? Math.round(totalPre / totalAll * 100) : 0;
  const buildPct = totalAll > 0 ? Math.round(totalBuild / totalAll * 100) : 0;
  const unattrPct = totalAll > 0 ? Math.round(totalUnattr / totalAll * 100) : 0;

  const repoId = 'repo-' + shortName.replace(/[^a-zA-Z0-9]/g, '_');

  return `<div class="repo-card" id="${repoId}">
    <div class="repo-card-header" onclick="toggleRepoCard('${repoId}')">
      <div>
        <span class="repo-name">
          <a href="${prUrl}" target="_blank" class="repo-link" onclick="event.stopPropagation()">${shortName} #${pr}</a>
        </span>
        <span class="repo-meta"> · ${passedCount}/${totalCount} passed · ${state}</span>
      </div>
      <button class="repo-toggle" id="${repoId}-toggle">收起 ▾</button>
    </div>
    <div class="repo-card-body" id="${repoId}-body">
      ${buildItems}
      ${validB.length > 0 ? `
      <div class="repo-card-footer">
        汇总: Pre-Build ${fmtDuration(totalPre)} (${prePct}%) · 
        Build ${fmtDuration(totalBuild)} (${buildPct}%) · 
        未归类 ${fmtDuration(totalUnattr)} (${unattrPct}%)
      </div>` : ''}
    </div>
  </div>`;
}

function renderBuildItem(build, repo) {
  if (build._error) {
    return `<div class="build-error">⚠️ ${build.task_name}: ${build._error}</div>`;
  }

  const dur = build.time?.duration_seconds || 0;
  const pre = build.pre_build?.total_seconds || 0;
  const bld = build.build_phases?.total_seconds || 0;
  const unattr = Math.max(0, dur - pre - bld);
  const prePct = dur > 0 ? Math.round(pre / dur * 100) : 0;
  const bldPct = dur > 0 ? Math.round(bld / dur * 100) : 0;
  const statusCls = build.status === 'passed' ? 'passed' : 'failed';
  const statusText = build.status === 'passed' ? '通过' : build.status;
  const timeRange = build.time?.start ? fmtTime(build.time.start) + '~' + fmtTime(build.time.end) : '';

  const buildId = 'build-' + (repo._repo_short + '_' + build.task_name).replace(/[^a-zA-Z0-9]/g, '_');

  // Pre-build actions table
  const preActions = (build.pre_build?.actions || []).map(a => {
    const isBottleneck = build.summary?.key_bottleneck === a.key;
    return `<tr>
      <td>${a.name}</td>
      <td>${fmtDateTimeShort(a.start)}</td>
      <td>${fmtDateTimeShort(a.end)}</td>
      <td class="${isBottleneck ? 'action-warn' : ''}">${fmtDuration(a.duration_seconds)}${isBottleneck ? ' ⚠️' : ''}</td>
      <td>${dur > 0 ? Math.round(a.duration_seconds / dur * 100) + '%' : '—'}</td>
    </tr>`;
  }).join('');

  // Build phases
  const buildActions = (build.build_phases?.actions || []).map(a =>
    `<tr><td>${a.name}</td><td>${fmtDuration(a.duration_seconds)}</td><td>${dur > 0 ? Math.round(a.duration_seconds / dur * 100) + '%' : '—'}</td></tr>`
  ).join('');

  return `<div class="build-item" onclick="toggleBuildDetail('${buildId}')">
    <div class="build-summary">
      <span class="build-status ${statusCls}">${statusText}</span>
      <span class="build-task-name">${build.task_name}</span>
      <span class="build-total-time">${fmtDuration(dur)}</span>
      <div class="build-bar-wrapper">
        <div class="build-bar">
          <div class="build-bar-pre" style="width:${prePct}%"></div>
          <div class="build-bar-build" style="width:${bldPct}%"></div>
        </div>
        <span class="build-bar-label">pre ${fmtDuration(pre)} · build ${fmtDuration(bld)}</span>
      </div>
      <span style="font-size:0.75rem;color:var(--text-muted)">${timeRange}</span>
      <span style="color:var(--text-muted)">▸</span>
    </div>
    <div class="build-detail" id="${buildId}-detail">
      <div class="build-detail-inner">
        ${preActions ? '<div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:6px;">Pre-Build 环境准备动作</div><table class="action-table"><thead><tr><th>动作</th><th>开始</th><th>结束</th><th>耗时</th><th>占比</th></tr></thead><tbody>' + preActions + '</tbody></table>' : ''}
        ${buildActions ? '<div style="font-size:0.8rem;color:var(--text-muted);margin:10px 0 6px;">Build 构建阶段</div><table class="action-table"><thead><tr><th>阶段</th><th>耗时</th><th>占比</th></tr></thead><tbody>' + buildActions + '</tbody></table>' : ''}
      </div>
    </div>
  </div>`;
}

// ── Expand/Collapse ──

function toggleBuildDetail(buildId) {
  const detail = document.getElementById(buildId + '-detail');
  detail.classList.toggle('open');
}

function toggleRepoCard(repoId) {
  const body = document.getElementById(repoId + '-body');
  const toggle = document.getElementById(repoId + '-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '收起 ▾';
  } else {
    body.style.display = 'none';
    toggle.textContent = '展开 ▸';
  }
}
```

- [ ] **Step 4: 添加初始化入口**

```javascript
// ── Initialization ──

function init() {
  const repos = __EMBEDDED_DATA__;
  if (!repos || repos.length === 0) {
    document.body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">暂无数据</div>';
    return;
  }
  renderHeader(repos);
  renderInsights(repos);
  renderRanking(repos);
  renderRepoCards(repos);
}

document.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 5: Commit**

```bash
git add template.html
git commit -m "feat: add JavaScript rendering logic for all 4 layers"
```

---

### Task 4: 添加交互功能（搜索、筛选、排序）

**Files:**
- Modify: `template.html` — 在 `<script>` 末尾添加筛选/排序逻辑，修改渲染函数以支持过滤

**Interfaces:**
- Consumes: 第 1 层的搜索框、编排器下拉、排序下拉
- Produces: 重新渲染第 3 层和第 4 层

- [ ] **Step 1: 添加过滤状态与过滤函数**

在 `init()` 函数之前添加：

```javascript
// ── Filter State ──

let filterState = {
  search: '',
  orchestrator: 'all',
  sort: 'pre_build_desc'
};

function getFilteredRepos() {
  let repos = __EMBEDDED_DATA__;

  // Apply orchestrator filter
  if (filterState.orchestrator !== 'all') {
    repos = repos.map(repo => {
      const filteredBuilds = (repo.builds || []).filter(b => {
        if (b._error) return true; // keep error builds
        return (b.pre_build?.orchestrator || '') === filterState.orchestrator;
      });
      if (filteredBuilds.length === 0) return null;
      return { ...repo, builds: filteredBuilds, _total_builds: filteredBuilds.length };
    }).filter(Boolean);
  }

  // Apply search filter
  if (filterState.search.trim()) {
    const q = filterState.search.trim().toLowerCase();
    repos = repos.filter(repo => {
      const short = (repo._repo_short || '').toLowerCase();
      const full = (repo.meta?.repo || '').toLowerCase();
      return short.includes(q) || full.includes(q) || String(repo.meta?.pr || '').includes(q);
    });
  }

  // Apply sort
  repos = [...repos]; // shallow copy
  if (filterState.sort === 'total_desc') {
    repos.sort((a, b) => {
      const maxA = Math.max(...(a.builds || []).filter(b => b.time).map(b => b.time.duration_seconds || 0));
      const maxB = Math.max(...(b.builds || []).filter(b => b.time).map(b => b.time.duration_seconds || 0));
      return maxB - maxA;
    });
  } else if (filterState.sort === 'pre_build_pct_desc') {
    repos.sort((a, b) => {
      const avgA = avgPreBuildPct(a);
      const avgB = avgPreBuildPct(b);
      return avgB - avgA;
    });
  } else {
    // pre_build_desc: sort by max bottleneck seconds
    repos.sort((a, b) => {
      const maxA = maxBottleneck(a);
      const maxB = maxBottleneck(b);
      return maxB - maxA;
    });
  }

  return repos;
}

function avgPreBuildPct(repo) {
  const builds = (repo.builds || []).filter(b => b._pre_build_pct != null);
  if (builds.length === 0) return 0;
  return builds.reduce((s, b) => s + b._pre_build_pct, 0) / builds.length;
}

function maxBottleneck(repo) {
  let max = 0;
  (repo.builds || []).forEach(b => {
    const s = b.summary?.key_bottleneck_seconds || 0;
    if (s > max) max = s;
  });
  return max;
}
```

- [ ] **Step 2: 添加事件绑定并修改渲染函数使用过滤数据**

```javascript
// ── Event Binding ──

function bindControls() {
  document.getElementById('searchInput').addEventListener('input', (e) => {
    filterState.search = e.target.value;
    rerender();
  });

  document.getElementById('orchestratorFilter').addEventListener('change', (e) => {
    filterState.orchestrator = e.target.value;
    rerender();
  });

  document.getElementById('sortSelect').addEventListener('change', (e) => {
    filterState.sort = e.target.value;
    rerender();
  });
}

function rerender() {
  const repos = getFilteredRepos();
  renderInsights(repos);
  renderRanking(repos);
  renderRepoCards(repos);
}

// Update init to call bindControls and use filtered data
function init() {
  if (!__EMBEDDED_DATA__ || __EMBEDDED_DATA__.length === 0) {
    document.body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">暂无数据</div>';
    return;
  }
  const repos = getFilteredRepos();
  renderHeader(__EMBEDDED_DATA__); // header always shows total
  renderInsights(repos);
  renderRanking(repos);
  renderRepoCards(repos);
  bindControls();
}
```

- [ ] **Step 3: Commit**

```bash
git add template.html
git commit -m "feat: add search, orchestrator filter, and sort controls"
```

---

### Task 5: 集成验证与调试

**Files:**
- Run: `generate.py`
- Verify: `index.html` (generated)

- [ ] **Step 1: 重新生成并检查数据完整性**

```bash
cd /home/wangsike/workspace/tmp/log_analyze && python3 generate.py
```

Expected: `Generated index.html: 9 repos, ~30 builds → .../index.html`

- [ ] **Step 2: 验证 index.html 结构完整性**

```bash
python3 -c "
with open('index.html') as f: html = f.read()
checks = [
    ('__EMBEDDED_DATA__', 'Embedded data'),
    ('renderHeader', 'Header render function'),
    ('renderInsights', 'Insights render function'),
    ('renderRanking', 'Ranking render function'),
    ('renderRepoCards', 'Repo cards render function'),
    ('toggleBuildDetail', 'Build detail toggle'),
    ('toggleRepoCard', 'Repo card toggle'),
    ('toggleRanking', 'Ranking toggle'),
    ('bindControls', 'Controls binding'),
    ('getFilteredRepos', 'Filter function'),
    ('fmtDuration', 'Duration formatter'),
]
for term, label in checks:
    if term in html: print(f'  ✅ {label}')
    else: print(f'  ❌ MISSING: {label}')
"
```

- [ ] **Step 3: 验证无 JS 语法错误**

```bash
# Extract JS from HTML and check with Node if available, otherwise basic checks
python3 -c "
import re
with open('index.html') as f: html = f.read()
# Find script content
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
print(f'Found {len(scripts)} script blocks')
for i, s in enumerate(scripts):
    lines = s.strip().split('\n')
    print(f'  Script {i+1}: {len(lines)} lines')
    # Basic check: balanced braces
    open_braces = s.count('{')
    close_braces = s.count('}')
    if open_braces == close_braces:
        print(f'    ✅ Braces balanced ({open_braces})')
    else:
        print(f'    ❌ Brace mismatch: {{ {open_braces} vs }} {close_braces}')
"
```

- [ ] **Step 4: 浏览器检查清单**

手动在浏览器中打开 `index.html`，确认：
1. 标题和更新时间正确显示
2. 统计行数字与数据一致（9 仓库、~30 构建）
3. 4 张洞察卡片数据合理
4. 排行表默认只显示慢构建（pre_build > 60s 或占比 > 30%）
5. "显示全部"按钮可切换
6. 仓库卡片展开/折叠正常
7. 构建详情展开/折叠正常
8. 搜索框输入"pytorch"只显示 pytorch 仓库
9. 编排器过滤只显示匹配的构建
10. 排序切换生效
11. `ops-nn` 构建显示错误提示

- [ ] **Step 5: 模拟新增仓库**

```bash
# Copy an existing JSON as a test
cp json/pytorch_build_analysis.json json/test_new_repo_build_analysis.json
python3 generate.py
# Verify it shows 10 repos
python3 -c "
import json, re
with open('index.html') as f: html = f.read()
match = re.search(r'const __EMBEDDED_DATA__ = (\[.*?\]);', html, re.DOTALL)
data = json.loads(match.group(1))
print(f'Repos embedded: {len(data)}')
for r in data: print(f'  - {r[\"_repo_short\"]}')
"
# Cleanup
rm json/test_new_repo_build_analysis.json
python3 generate.py
```

- [ ] **Step 6: Final commit**

```bash
git add generate.py template.html index.html
git commit -m "feat: complete CI/CD pre-build kanban board

- generate.py: build script that embeds JSON data into HTML
- template.html: full kanban UI with 4-layer layout
- Layer 1: global status bar with search/filter/sort
- Layer 2: auto-computed insight cards (bottleneck, top 3, ARM vs x86)
- Layer 3: pre-build ranking table with color-coded severity
- Layer 4: expandable repository detail cards with action timelines
- Responsive dark theme, zero external dependencies

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verification Summary

```bash
# Full verification script
cd /home/wangsike/workspace/tmp/log_analyze

echo "=== 1. Generate ==="
python3 generate.py

echo ""
echo "=== 2. Data Integrity ==="
python3 -c "
import json, re
with open('index.html') as f: html = f.read()
match = re.search(r'const __EMBEDDED_DATA__ = (\[.*?\]);', html, re.DOTALL)
assert match, 'No embedded data found'
data = json.loads(match.group(1))
print(f'Repos: {len(data)}')
for r in data:
    errs = sum(1 for b in r.get('builds',[]) if b.get('_error'))
    status = ' ⚠️ HAS ERRORS' if errs else ''
    print(f'  {r[\"_repo_short\"]}: {len(r.get(\"builds\",[]))} builds{status}')
total = sum(len(r.get('builds',[])) for r in data)
print(f'Total builds: {total}')
"

echo ""
echo "=== 3. Structure Check ==="
python3 -c "
with open('index.html') as f: html = f.read()
for term in ['renderHeader','renderInsights','renderRanking','renderRepoCards',
             'toggleBuildDetail','toggleRepoCard','bindControls','getFilteredRepos']:
    assert term in html, f'Missing: {term}'
print('All render functions present ✅')
# Check no placeholder left
assert '{{DATA_JSON}}' not in html, 'Placeholder not replaced'
print('No leftover placeholders ✅')
# Check balanced braces in script
import re
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    if s.strip().startswith('const __EMBEDDED_DATA__'): continue  # skip data block
    assert s.count('{') == s.count('}'), f'Script {i+1} brace mismatch'
print('JS braces balanced ✅')
"

echo ""
echo "=== All checks passed ==="
```

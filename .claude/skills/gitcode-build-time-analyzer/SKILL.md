---
name: gitcode-build-time-analyzer
description: "分析 GitCode PR 门禁流水线中构建前置环境准备的耗时。从 openLiBing 拉取完整构建日志，AI 语义识别环境准备动作及其耗时，输出结构化 JSON。聚焦于 slave_create、镜像拉取、代码检出、Pod 调度、依赖安装等构建前动作。触发词：构建耗时分析、门禁构建阶段时间、环境准备耗时、build time profiling。"
---

# GitCode Build Time Analyzer — 构建前置环境准备分析

从 GitCode PR 流水线中拉取完整构建日志，使用 AI 语义分析识别**构建前置环境准备**动作，
提取每个动作的耗时，输出结构化 JSON。

关注点：**构建开始之前**的所有环境准备工作——节点分配、镜像拉取、代码检出、
Pod 调度、依赖安装等。构建本身（cmake/编译/打包）仅做概要统计。

## 架构

4 阶段流水线，AI 与 Script 明确分离：

```
Stage 1 [AI]:   gc pr comments → 语义识别流水线任务 → manifest JSON
Stage 2 [Script]: scripts/download.py → logs/<repo>/pr<NNN>/*.log.gz
Stage 3 [AI]:   读原始日志 + schema/template.json → 填充分析 → json-org/
Stage 4 [Script]: validate.py → normalize.py → generate.py → git push
```

单仓库 AI 分析模式：
```
AI (Claude)
───────────────────────────────────────
1. 读 schema/template.json 了解 JSON 结构
2. 读 json-org/<repo>_build_analysis.json 了解 build 列表 + 时间信息
3. 读 logs/<repo>/pr<NNN>/<task>.log.gz 完整原始日志
4. 语义识别每个环境准备动作及起止时间
5. 按 action_catalog 选择对应的 action key
6. 应用 R9 无缝衔接 + R1-R8 质量规则
7. 填充 pre_build.actions[] + build_phases + summary
8. Write 完成 JSON 回同一 json-org/ 路径
```
    fetch_build_logs.py --repo $repo   Agent("Analyze MindIE-SD")     ─┤ 并行
                                      Agent("Analyze MindIE-LLM")    ─┤
                                      Agent("Analyze torchair")      ─┘
                                      
Phase 3: 校验 + 补漏                    Phase 4: 跨仓库对比报告
──────────────────────                 ──────────────────────
for repo in success:                   汇总所有 JSON → 排名、瓶颈对比、
    verify R1-R7                       编排器影响分析、Pod 调度对比
    if empty/buggy → re-agent
```

## 快速开始

```bash
# 单仓库 — 分析最新 merged PR
python3 scripts/fetch_build_logs.py --repo Ascend/pytorch --latest-merged -o json-org/pytorch_build_analysis.json

# 单仓库 — 分析指定 PR
python3 scripts/fetch_build_logs.py --repo Ascend/MindIE-Motor --pr 204 -o json-org/MindIE-Motor_build_analysis.json

# 单仓库 — 单任务
python3 scripts/fetch_build_logs.py --repo cann/ops-nn --pr 6193 --task Compile_Ascend_X86_ubuntu24 -o json-org/ops-nn_build_analysis.json

# 多 Agent 批量模式（≥3 个仓库）
/gitcode-build-time-analyzer 使用多Agent模式分析 MindIE 系列:
  - Ascend/MindIE-Motor
  - Ascend/MindIE-SD
  - Ascend/MindIE-PyMotor
  - Ascend/MindIE-LLM
```

选项：`--latest-merged` | `--pr <N>` | `--task <name>` | `--max-sample <N>` | `--full-log` | `--ci-backend <openlibing|jenkins>`

### Jenkins CI 后端

对于使用 openEuler Jenkins CI 的仓库（如 `openeuler/kernel`），使用 `--ci-backend jenkins`：

```bash
python3 scripts/fetch_build_logs.py --repo openeuler/kernel --latest-merged --ci-backend jenkins -o json-org/kernel_build_analysis.json
```

Jenkins 后端特点：
- 从 `ci.openeuler.openatom.cn` 的 `/consoleText` 端点获取日志（公开，无需认证）
- 从 `/api/json` 获取构建元数据（timestamp + duration）
- 日志较小（~500 行），一次 HTTP GET 全量获取
- 时间戳格式：`[YYYY-MM-DD HH:MM:SS]`（无亚秒、无时区后缀）

### Fetch 缓存策略（避免重复拉取）

如果 `json-org/<repo>_build_analysis.json` 已存在且 `meta.pr` 与最新 merged PR 相同，**跳过 fetch**，直接进入 AI 分析。判断逻辑：

```bash
# 检查是否需要重新 fetch
latest_pr=$(gc pr list -R "$repo" --state merged -L 1 2>&1 | grep -oP '#\d+' | tr -d '#')
existing_pr=$(python3 -c "import json; print(json.load(open('json-org/${name}_build_analysis.json'))['meta']['pr'])" 2>/dev/null)
if [ "$latest_pr" = "$existing_pr" ] && [ -f "json-org/${name}_build_analysis.json" ]; then
  echo "SKIP fetch: PR #$latest_pr unchanged, reusing existing data"
else
  python3 scripts/fetch_build_logs.py --repo "$repo" --latest-merged -o "json-org/${name}_build_analysis.json"
fi
```

注意：用户明确要求 `--pr <N>` 时忽略缓存，强制重新 fetch。

### PR 回退发现策略（重要）

`--latest-merged` 选取的是**最近合入的 PR**，但该 PR 可能是一个纯文档变更，
其 Build 任务被跳过（🛑）、流水线中根本没有编译构建阶段，或者缺少流水线评论表。
此时不能直接放弃该仓库——需要向后扫描最近的合入 PR，找到**第一个包含 passed 构建**的 PR。

**自动回退流程**（Phase 1.5）：

```bash
# 从最新合入 PR 向后扫描，最多 20 个
for pr_num in $(gc pr list -R "$repo" --state merged -L 20 2>&1 | grep -oP '#\d+' | tr -d '#'); do
  result=$(python3 scripts/fetch_build_logs.py --repo "$repo" --pr "$pr_num" -o "/tmp/test_${name}.json" 2>&1)
  if echo "$result" | grep -q "Template written"; then
    mkdir -p json-org
    cp "/tmp/test_${name}.json" "json-org/${name}_build_analysis.json"
    echo "FOUND: PR #$pr_num has passed builds"
    break
  fi
  rm -f "/tmp/test_${name}.json"
done
```

**回退结果分类**：

| 结果 | 含义 | 处理 |
|------|------|------|
| 找到含 passed 构建的 PR | 最新合入 PR 恰好是 docs-only | 使用该 PR，正常进入 Phase 2 |
| 20 个 PR 全部 `no_pipeline` | 该仓库从未有过构建流水线 | 标记为不可分析 |
| 20 个 PR 全部 `no_passed_builds` | 有流水线但 Build 从未通过 | 标记 `_error: "No passed build in last 20 PRs"` |
| 混合但无 passed（如 MindSpeed-LLM） | 仅有代码检查无 Build 任务 | 标记 `_error: "No Build task in pipeline — code-quality-only repo"` |

**区分两种"失败"**：
- `"No pipeline table found"` → PR 评论中根本没有流水线表格
- `"No passed build tasks found"` → 有流水线表格但 Build 任务状态非 passed（🛑/❌）

## 产物位置

JSON 文件写入 **`json-org/`** 目录（不存在则自动创建），命名规则：`<仓库名>_build_analysis.json`
（仓库名取自 `--repo` 路径最后一段，如 `Ascend/pytorch` → `pytorch`）。

**为何是 `json-org/`**：该目录存放原始分析结果，后续由 `build-log-normalizer` 归一化到 `json/`，再由 `generate.py` 生成看板页面。完整流水线：

```
gitcode-build-time-analyzer → json-org/*.json → build-log-normalizer → json/*.json → generate.py → index.html
```

## AI 分析流程

脚本运行后，读取输出 JSON 文件，其中包含：
- `meta` — PR、仓库、流水线元信息
- `builds[].log_sample` — 采样日志（含间隙标记）
- `builds[].time` — 构建总耗时
- `builds[].significant_gaps` — >5s 的时间间隙（定位阶段切换的线索）

### Step 1 — 扫描 log_sample，定位环境准备动作

逐行阅读 `log_sample`，按时间顺序识别以下动作的**起止时间戳**：

动作分两大类：**外部 CI 调度机** 上的动作（节点分配、前置校验、Pod 提交），以及 **Pod 内部** 的动作（clone、依赖安装、子模块初始化等）。两类动作的时间线是连续的——Pod 内部动作在 `pod_scheduling` 结束之后开始。

| 动作 key | 动作名称 | 阶段 | 日志中典型标志 |
|---|---|---|---|
| `node_assignment` | 执行节点分配 | 外部CI | `[PRE_ENV:slave_create]` 开始→完成，`create execution node` |
| `docker_pull` | Docker 镜像拉取 | 外部CI | `Pulling from *****`, `Pull complete`, `Image is up to date` |
| `cache_check` | 缓存检查 | 外部CI | `[Cache Check:external_cache_check]` 开始→完成 |
| `git_checkout` | 代码检出(CI机) | 外部CI | `[代码检出:external_pre_checkout]` 开始 → `external_post_checkout` 完成，含 git fetch/clone/merge |
| `network_retry` | 网络重试等待 | 外部CI | `fatal: unable to access`, `Failed to connect`, `Retrying in`，两次 clone 尝试之间的等待 |
| `pre_submit_validation` | 前置校验 | 外部CI | `=== Pre-submit validation ===` |
| `image_proxy` | 镜像代理替换 | 外部CI | `[OK] Harbor registry found`, `IMAGE Replaced: swr.` |
| `git_cache_injection` | Git 缓存注入 | 外部CI | `[OK] Git-cache found`, `injecting git proxy` |
| `orchestrator_submit` | 编排器任务提交 | 外部CI | Argo: `Workflow submitted`, `argo submit`；Volcano: `Volcano Job 提交`、`Job ... submitted`；Docker: 无 |
| `pod_scheduling` | Pod调度等待 | 过渡 | **从 `orchestrator_submit` 结束到 `Pod 状态: Running` 的完整等待时间**。Volcano: `等待 Pod ... 开始运行` 起始 → `Pod 状态: Running`；Argo: `等待主 Pod (main-script) 出现` → `找到主 Pod`。⚠️ 关键是测量整个等待区间，不是只抓 Running 出现的那一瞬间 |
| `pod_git_clone` | 代码检出(Pod内) | Pod内 | Pod Running 后的 `git clone`、`git fetch`、`Cloning into '...'`（clone 的是业务仓库 workspace，非 CI 脚本仓库）。如遇网络超时重试，将重试等待独立标记为 `network_retry` |
| `env_setup` | 环境变量+ccache初始化 | Pod内 | `source set_env.sh`、`export`、`setenv_main`、`ccache` 初始化、`git merge`（在业务仓库内执行）、CI 脚本 clone（`git clone ... MindIE-CI.git` 或 `git clone ... cie.git`） |
| `submodule_init` | Git子模块初始化 | Pod内 | `Submodule '...' registered`、`Cloning into '...third_party/...'`、`Submodule path '...' checked out`、git submodule update/init。⚠️ 子模块克隆通常很多（5-20个），需累计所有子模块的总耗时 |
| `pip_install` | Python依赖安装 | Pod内 | `pip install`、`Collecting`、`Successfully installed`、pip wheel 下载 |
| `conda_install` | Conda依赖安装 | Pod内 | `conda install`, `mamba install` |
| `apt_install` | 系统包安装 | Pod内 | `apt-get install`, `apt install` |
| `tool_download` | 构建工具下载 | Pod内 | 下载 cmake/ninja/gcc 的 pip wheel 或 wget |
| `artifact_download` | 制品/OBS下载 | Pod内 | `wget`、`curl`、`obsutil cp` 下载（含 `https://...obs...` 或 `https://...myhuaweicloud.com/...` 的 wget）；第三方库解压 (`unzip opensource_*.zip`) |
| `acl_headers` | ACL头文件准备 | Pod内 | `Copied ... acl headers`、`cp ... acl`、`acl header`、`ACL include` |
| `workspace_prep` | 工作目录准备 | Pod内 | `rm -rf`、`mkdir -p`、`cd` 等目录清理/创建操作（不含 clone，clone 归入 `pod_git_clone` 或 `env_setup`） |
| `codegen` | 代码生成+CMake配置 | Pod内 | `CMake configure`、`Generating build files`、protobuf 代码生成 (`Running protoc`)、`cmake -B build`。注意：cmake configure 发生在 Pod 内编译开始之前，属于前置动作。与 build_phases 中的 `cmake_configure` 区分——`codegen` 是 cmake 之前的代码生成步骤 |
| `cmake_configure` | CMake配置 | Build | `-- The C compiler identification is GNU`、`-- Check for working C compiler`、`-- Configuring done`、`-- Generating done`、`-- Build files have been written to`。属于 build_phases，不归入 pre_build |

### Step 2 — 确定每个动作的起止时间

对于每个识别到的动作：
- `start` — 该动作第一条日志的时间戳
- `end` — 该动作最后一条日志的时间戳
- `duration_seconds` = end - start
- 参考 `significant_gaps` 作为阶段切换线索
- 如果动作未发生（如无 conda 安装），**跳过不填**

**⚠️ Pod 调度耗时 (pod_scheduling) 的正确测量方式：**

`pod_scheduling` 测量的是 **从编排器提交到 Pod 进入 Running 的完整等待时间**，不是 Pod 变为 Running 的瞬间：

| 编排器 | start 标志 | end 标志 |
|---|---|---|
| **Volcano** | `Volcano Job 提交` 或 `Job ... submitted` 之后的第一条日志 | `Pod 状态: Running` |
| **Argo** | `Workflow submitted` 或 `argo submit` 之后的第一条日志 | `找到主 Pod (main-script)` 或 `Pod 状态: Running` |
| **Docker** | 无调度环节，跳过 | — |

典型值：Argo 5-30s，Volcano 5-260s。如果测出来的 `pod_scheduling` < 1s，说明只抓了 Running 出现的瞬间而非完整等待——这是**错误**的。

**⚠️ 两阶段时间线模型：**

构建前环境准备分为两个连续阶段：

```
外部 CI 调度机                      Pod 内部
─────────────────────              ─────────────────────────────
node_assignment                    pod_git_clone
git_checkout                       env_setup (含 CI脚本clone)
pre_submit_validation              submodule_init
image_proxy                        pip_install
git_cache_injection                artifact_download
orchestrator_submit ──┐            acl_headers
pod_scheduling ───────┘            tool_download
                      │            workspace_prep
                   Pod Running     ...
                                      │
                                   CMake 开始 → 进入 build_phases
```

两个阶段之间由 `pod_scheduling` 连接。`pod_scheduling` 的 end 即为 Pod 内阶段的时间起点。

**⚠️ Docker 原生 CI 单阶段模型：**

Docker 仓库（MindSpeed 系列）无 K8s 编排器，所有操作在 CI 执行机上串行完成：

```
CI 执行机（单阶段，无 Pod 调度）
────────────────────────────────────────
node_assignment          (执行节点分配，3-8s)
docker_pull              (Docker 镜像拉取，多层，20-60s) ← 最大开销
cache_check              (缓存检查，<1s)
git_checkout             (代码检出，8-30s)
pre_submit_validation    (前置校验，5-15s)
  ├─ image_proxy         (Harbor 镜像代理替换)
  └─ git_cache_injection (Git 缓存注入)
orchestrator_submit      (跳过 — 无 K8s 编排器)
pod_scheduling           (跳过 — 无 Pod)
pip_install              (Python 依赖安装，15-70s)
workspace_prep           (工作目录准备)
  ↓
setup.py 构建 / CMake 开始 → 进入 build_phases
```

关键差异：
- `orchestrator = "docker"`（不是 argo/volcano）
- 无 `pod_scheduling`、无 `pod_git_clone`（没有 Pod 概念）
- `docker_pull` 是主要环境准备开销（多层镜像拉取，即使命中缓存也需 10-25s 检查）
- Pod 内动作（如 pip_install、workspace_prep）直接在 CI 执行机上运行，归入 pre_build

### Step 3 — 划分"构建前"与"构建中"

**构建开始的标志**（遇到任一个即视为环境准备结束）：
- `cmake` 配置开始（`-- Check for working C compiler`）
- `setup.py build/develop/install` 开始（`running build_ext`）
- `ninja` / `make` 编译开始（`[0%] Building CXX object`）
- pip wheel 构建开始（`Building wheel for <package> (pyproject.toml): started`）
- 纯 Python 项目的 `running build_py`

构建开始之后的动作（cmake configure、编译、wheel 打包、上传）归入 `build_phases` 概要统计，不需要逐个拆解。

### Step 4 — 写入完成的分析

1. 读入模板 JSON
2. 为每个 build 填充 `pre_build.actions[]`
3. 填充 `build_phases.actions[]`（仅概要）
4. 设置 `meta.analyzed_at`
5. **写回同一文件路径**
6. 向用户报告文件路径和关键发现

## 输出 JSON 结构

```json
{
  "meta": {
    "pr": 38696,
    "repo": "Ascend/pytorch",
    "pr_url": "https://gitcode.com/Ascend/pytorch/pull/38696",
    "pipeline_name": "PR-pipeline_pytorch#32911",
    "pipeline_state": "已完成",
    "pipeline_url": "https://www.openlibing.com/...",
    "fetched_at": "2026-06-17T11:00:00+08:00",
    "analyzed_at": "2026-06-17T11:05:00+08:00",
    "analysis_method": "ai_semantic"
  },
  "builds": [
    {
      "task_name": "Build_X86",
      "status": "passed",
      "detail_url": "https://www.openlibing.com/...",
      "time": {
        "start": "2026-06-16T23:55:51.573+08:00",
        "end": "2026-06-17T00:01:11.721+08:00",
        "duration_seconds": 320.1
      },
      "pre_build": {
        "total_seconds": 175.1,
        "pct_of_total": 55.4,
        "orchestrator": "volcano",
        "actions": [
          {
            "key": "node_assignment",
            "name": "执行节点分配",
            "start": "2026-06-16T23:56:30.123+08:00",
            "end": "2026-06-16T23:56:35.456+08:00",
            "duration_seconds": 5.3,
            "evidence": "slave_create: node cce-codeci-137585f332 assigned"
          },
          {
            "key": "git_checkout",
            "name": "代码检出(CI机)",
            "start": "2026-06-16T23:56:35.500+08:00",
            "end": "2026-06-16T23:56:54.789+08:00",
            "duration_seconds": 19.3,
            "evidence": "external_pre_checkout → git fetch PR #38696 → external_post_checkout"
          },
          {
            "key": "pre_submit_validation",
            "name": "前置校验",
            "start": "2026-06-16T23:56:37.000+08:00",
            "end": "2026-06-16T23:56:50.000+08:00",
            "duration_seconds": 13.0,
            "evidence": "=== Pre-submit validation === 23:56:37 → 前置校验完成 23:56:50"
          },
          {
            "key": "orchestrator_submit",
            "name": "Volcano Job 提交",
            "start": "2026-06-16T23:56:52.000+08:00",
            "end": "2026-06-16T23:56:52.500+08:00",
            "duration_seconds": 0.5,
            "evidence": "Volcano Job 提交 23:56:52"
          },
          {
            "key": "pod_scheduling",
            "name": "Pod调度等待(Volcano)",
            "start": "2026-06-16T23:56:52.500+08:00",
            "end": "2026-06-16T23:57:10.000+08:00",
            "duration_seconds": 17.5,
            "evidence": "Volcano Job submitted 23:56:52 → Pod 状态: Running 23:57:10 (等待了17.5s)"
          },
          {
            "key": "pod_git_clone",
            "name": "代码检出(Pod内)",
            "start": "2026-06-16T23:57:10.000+08:00",
            "end": "2026-06-16T23:57:27.100+08:00",
            "duration_seconds": 17.1,
            "evidence": "Pod Running 后 git clone workspace + cie + CODE 三个仓库 (23:57:10 → 23:57:27)"
          },
          {
            "key": "env_setup",
            "name": "环境变量+ccache+merge",
            "start": "2026-06-16T23:57:16.000+08:00",
            "end": "2026-06-16T23:57:32.000+08:00",
            "duration_seconds": 16.0,
            "evidence": "source set_env.sh (23:57:16) → ccache 初始化 → git merge develop (23:57:27) → cd workspace (23:57:32)"
          },
          {
            "key": "artifact_download",
            "name": "OBS制品下载",
            "start": "2026-06-16T23:57:32.000+08:00",
            "end": "2026-06-16T23:57:35.000+08:00",
            "duration_seconds": 3.0,
            "evidence": "wget https://...obs.../torch-2.7.1+cpu-cp310-cp310-linux_x86_64.whl (192MB)"
          },
          {
            "key": "pip_install",
            "name": "Python依赖安装",
            "start": "2026-06-16T23:57:33.000+08:00",
            "end": "2026-06-16T23:57:35.500+08:00",
            "duration_seconds": 2.5,
            "evidence": "pip install torch-2.7.1+cpu-cp310-cp310-linux_x86_64.whl (23:57:33 → 23:57:35)"
          },
          {
            "key": "submodule_init",
            "name": "Git子模块初始化",
            "start": "2026-06-16T23:57:34.000+08:00",
            "end": "2026-06-16T23:58:08.000+08:00",
            "duration_seconds": 34.0,
            "evidence": "Submodule 'third_party/FastFormat' registered → 10个子模块全部检出 (23:57:34 → 23:58:08)"
          },
          {
            "key": "acl_headers",
            "name": "ACL头文件准备",
            "start": "2026-06-16T23:58:05.000+08:00",
            "end": "2026-06-16T23:58:33.000+08:00",
            "duration_seconds": 28.0,
            "evidence": "Copied ... acl headers (23:58:05 → 23:58:33)"
          }
        ]
      },
      "build_phases": {
        "total_seconds": 137.0,
        "pct_of_total": 42.8,
        "actions": [
          {
            "key": "cmake_configure",
            "name": "CMake 配置",
            "duration_seconds": 12.0
          },
          {
            "key": "compilation",
            "name": "编译 (ninja/gcc)",
            "duration_seconds": 95.0
          },
          {
            "key": "packaging",
            "name": "打包与上传",
            "duration_seconds": 30.0
          }
        ]
      },
      "summary": {
        "pre_build_seconds": 175.1,
        "build_seconds": 137.0,
        "unattributed_seconds": 8.0,
        "key_bottleneck": "submodule_init",
        "key_bottleneck_seconds": 34.0
      }
    }
  ]
}
```

## 编排器识别

不同仓库使用不同的容器编排器，影响环境准备流程：

| 编排器 | 日志特征 | 典型 Pod 调度耗时 | 示例仓库 |
|---|---|---|---|
| **Argo Workflow** | `Workflow submitted`, `等待主 Pod (main-script) 出现`, `Argo Workflow YAML` | 5-30s | MindIE-Motor, MindIE-PyMotor |
| **Volcano Job** | `Job xxx 的主 Pod`, `volcano.sh/job-name`, `[日志] 等待 Pod ... 开始运行` | 5-260s | pytorch, MindIE-LLM, MindIE-SD, torchair |
| **Docker 原生** | `Pull complete` (多层), 无 Pod 调度日志 | 0s (无调度) | MindSpeed, MindSpeed-MM |

`pre_build.orchestrator` 字段必须设为 `"argo"`、`"volcano"`、`"docker"` 或 `"jenkins"`。

| **Jenkins (内核构建)** | `***** allmodconfig build *****` 等显式阶段标记, `/api/json` 时间戳 | 0s (无调度) | openeuler/kernel |

### Jenkins 内核构建分析

Jenkins upstream kernel 构建**不是**容器编排模型。它有显式阶段标记和完全不同的动作集。

**构建前 (pre_build)** — 在编译节点上准备环境：
| 动作 key | 名称 | 日志标志 |
|---|---|---|
| `clone_check_scripts` | Clone 检查脚本 | `***** clone check scripts *****` / `***** Get the corresponding check-kabi script *****` |
| `clone_kernel_repo` | Clone 内核仓库 | `***** Start to download kernel of openeuler *****` |
| `install_build_tools` | 安装构建工具 | `***** Start to install build tools *****` |
| `apply_pr_patch` | 应用 PR 补丁 | `***** Download and Apply PR *****` |

**构建中 (build_phases)** — 内核编译 + 检查：
| 动作 key | 名称 | 日志标志 |
|---|---|---|
| `allmodconfig_build` | Allmodconfig 构建 | `***** Build kernel with allmodconfig *****` |
| `defconfig_build` | Defconfig 构建 | `***** Build kernel with openeuler_defconfig *****` |
| `kabi_check` | KABI 兼容性检查 | `***** Check kabi compatibility *****` |
| `defconfig_check` | Defconfig 一致性检查 | `***** Check openeuler_defconfig consistency *****` |

**关键差异**：
- `orchestrator = "jenkins"` — 无容器编排
- **无** `pod_scheduling`、`pod_git_clone`、`submodule_init`、`docker_pull`、`image_proxy`、`git_cache_injection`
- 构建时间占 >95%（内核编译主导），pre_build <5%
- 日志格式：`[YYYY-MM-DD HH:MM:SS] [  INFO ] ...`（无亚秒、无时区后缀）
- 成功标志：`[YYYY-MM-DD HH:MM:SS] [  INFO ] <arch> <phase> pass`
- 最终结果：`Finished: SUCCESS` 或 `Finished: FAILURE`
- API 时间戳来自 `/api/json` 字段 `timestamp`（ms Unix epoch）+ `duration`（ms）
- 多架构并行构建：aarch64, x86_64, ppc, ppc64, loongarch, arm, riscv64 — 每个架构作为独立 build
- 仅分析 `passed` 构建，跳过 `check_package_license` 等非编译任务

## Pod 内环境准备阶段（重点）

Pod 进入 Running 后到 CMake 开始前的这段时间是**最容易被漏分析的区域**。以下动作几乎在每个 Volcano/Argo 构建中都会出现，必须逐项识别：

### 典型 Pod 内动作序列

```
Pod Running
  ├─ git clone <workspace>           → pod_git_clone (5-30s)
  ├─ source env.sh + ccache init     → env_setup (3-10s)
  ├─ git clone <CI脚本> + <CODE>     → env_setup (合并入上一步)
  ├─ git merge + submodule init      → submodule_init (10-60s)  ← 常是最大瓶颈
  ├─ wget <torch wheel 192MB>        → artifact_download (1-5s)
  ├─ pip install torch               → pip_install (1-5s)
  ├─ git submodule clone ×N          → submodule_init (含在上面的累计中)
  └─ cp acl headers                  → acl_headers (5-30s)
CMake 开始
```

### 各动作识别要点

- **pod_git_clone**: 只算业务仓库的 `git clone`（如 `Cloning into 'pytorch'`），不含 CI 脚本仓库（归入 `env_setup`）
- **env_setup**: 合并了 source env.sh + ccache 初始化 + CI 脚本 clone（`git clone ... MindIE-CI.git` / `git clone ... cie.git`）+ `git merge`（在业务仓库内执行）+ `cd` 工作目录
- **submodule_init**: 从第一个 `Submodule '...' registered` 到最后一个 `Submodule path '...' checked out`。子模块克隆通常是**最大的单一瓶颈**（10-60s），绝不能遗漏
- **artifact_download**: 关注 wget 下载大文件（.whl, .tar.gz），尤其是来自 OBS/HuaweiCloud 的 URL
- **acl_headers**: `Copied ... acl headers` 或类似的头文件复制操作，Ascend 构建特有
- **pip_install**: 注意区分 wget 下载 wheel（归入 `artifact_download`）和 pip install 该 wheel（归入 `pip_install`）

## 分析要点

- **从日志语义理解，不依赖关键词匹配**。理解每一段日志在做什么。
- **时间间隙是线索**：`significant_gaps` 指向阶段切换点，但必须结合日志内容确认。
- **动作可能交织**：如 git clone 过程中穿插了网络超时，应将 clone 重试等待独立标记为 `network_retry`。
- **网络问题单独标记**：如果 git clone 耗时异常（>60s），检查日志中是否有 `fatal: unable to access`、`Failed to connect`、`Retrying` 等标志。使用 `network_retry` 动作单独标记重试等待时间。
- **Pod 调度耗时必须测量完整等待**：`pod_scheduling` 从 `orchestrator_submit` 结束开始，到 `Pod 状态: Running` 结束。**绝不能**只测 Running 出现的瞬间（<1s = 错误）。典型值: Volcano 5-260s, Argo 5-30s。如果测出 <1s 的 pod_scheduling，这是 bug——回去找提交时间戳。
- **Pod 调度 vs Pod 内 clone 的划分**：`pod_scheduling.end` = Pod Running 时刻 = Pod 内阶段的起点。Pod Running **之后**的 git clone 归入 `pod_git_clone`（业务仓库）或 `env_setup`（CI 脚本仓库），**不能**混入 `pod_scheduling`。
- **Docker 原生 CI** (MindSpeed 系列) 无 Pod 调度，`docker_pull` 的镜像拉取层就是主要的环境准备开销。
- **提供 `evidence`**：每个动作都要附上起止日志的关键片段，使分析可审计。
- **`env_setup` 不是垃圾桶**：`env_setup` 仅包含 source env.sh + ccache 初始化 + CI 脚本 clone + git merge 这类"设置类"操作。**绝不**把 `pod_git_clone`、`submodule_init`、`pip_install`、`artifact_download`、`acl_headers` 合并进 `env_setup`。如果 `env_setup` 的 evidence 是 "Pod Running → 编译开始" 且 duration > 20s，说明把整个 Pod 内阶段当成了一个动作——这是**严重错误**，必须拆分为独立动作。

## 数据质量规则（MUST）

以下规则在每次分析后必须逐条校验，不满足的要修正后再写入 JSON。

### R1: 负数夹底
```python
unattributed_seconds = max(0, total_duration - pre_build_seconds - build_seconds)
```
`summary.unattributed_seconds` **不得为负数**。若计算值为负，说明 `pre_build` 或 `build_phases` 动作之间有重叠或高估，应缩减对应动作的 duration 直至 unattributed >= 0。

### R2: 错误记录必须标记
遇到无法分析的构建（如 API 参数缺失、日志拉取失败），必须在 JSON 中明确记录：
```json
{
  "task_name": "...",
  "_error": "Cannot extract API params from task link",
  "pre_build": { "total_seconds": 0, "pct_of_total": 0, "orchestrator": "", "actions": [] },
  "build_phases": { "total_seconds": 0, "pct_of_total": 0, "actions": [] },
  "summary": { "pre_build_seconds": 0, "build_seconds": 0, "unattributed_seconds": 0, "key_bottleneck": "", "key_bottleneck_seconds": 0 }
}
```
- 使用 `_error` 字段（下划线前缀）与正常构建区分
- `time` 字段如果不可用，设为 `null`
- 禁止把错误记录静默丢弃

### R3: 去重
如果同一个 `task_name` 出现多条记录（来自不同流水线运行），**只保留最新的**（按 `time.start` 排序）。去重逻辑应写入分析脚本。

### R9: 无缝衔接 — 消除动作间隙（最重要规则）

**目标**：unattributed_seconds 逼近 0。

**问题根因**：动作测量方式为"自己的第一条日志 → 自己的最后一条日志"，动作之间自然存在 CI 系统空闲间隙（通常 1-10s），这些间隙被计入 `unattributed_seconds`。

**解决方案**：改为**无缝衔接**——每个动作的 `end` 时间戳设为下一个动作的 `start` 时间戳。

具体规则：
1. 将 pre_build.actions 按 `start` 时间排序
2. 对于每个动作 `A[i]`，将其 `end` 设为 `A[i+1].start`（即下一个动作的开始时间）
3. 最后一个 pre_build 动作的 `end` 设为 build 阶段的起始时间戳
4. `build_phases.compilation` 的结束时间设为整个构建的结束时间（`time.end`）
5. 重新计算每个动作的 `duration_seconds = end - start`（使用修正后的 end）
6. 修正后 `unattributed_seconds` 应 < 总耗时的 1% 或 < 5s
7. 动作的 `evidence` 字段保留原始日志证据，但 `duration_seconds` 使用修正后的值

**例外**：
- `pod_scheduling` 的 start 必须是 `orchestrator_submit` 的 end（因为 Pod 调度从提交开始）
- 如果两个动作之间有明显的 CI 系统切换（如从外部 CI 到 Pod 内部），间隙保留在 `pod_scheduling` 中
- Docker 原生 CI 的 `docker_pull` end 设为下一个 CI 动作的 start

**修正示例**：
```
修正前：
  节点分配: 16:10:02→16:10:07 (5s)  ← gap 1.7s →
  镜像拉取: 16:10:08→16:10:33 (25s) ← gap 1s →
  代码检出: 16:10:34→16:10:42 (8s)

修正后：
  节点分配: 16:10:02→16:10:08 (6s)  ← end 接到镜像拉取 start
  镜像拉取: 16:10:08→16:10:34 (26s) ← end 接到代码检出 start
  代码检出: 16:10:34→16:10:42 (8s)  ← 最后一个接 build start
```

### R4: 大间隙兜底识别（强制步骤，不可跳过）

**触发条件**：R9 无缝衔接应用后，如果 `unattributed_seconds` 仍 > 5s，运行 R4 作为兜底扫描。

**执行步骤**：
1. 遍历 `significant_gaps` 中所有 >5s 的间隙
2. 对每个间隙，检查 gap 前后的 `sample_before` / `sample_after` 日志内容
3. **累计**同类型的间隙时间到对应动作或延长 build_seconds
4. 重新计算 unattributed_seconds，如果仍 > 15%，继续第二轮分析（阈值降到 >20s 的间隙）
5. 最终 unattributed_seconds 应 **< total * 0.10 且 < 60s**。如果达不到，在 `summary` 中标注 `_unattributed_note: "剩余未归类包含: <说明>"`

**间隙分类规则**（按优先级）：
- 间隙前后有 `Cloning into` / `git clone`（非 third_party 路径） → 添加 `pod_git_clone`
- 间隙前后有 `Submodule` / `Cloning into '...third_party/...'` / `Submodule path` → 添加 `submodule_init`
- 间隙前后有 `fatal: unable` / `Failed to connect` → 添加 `network_retry`
- 间隙前后有 `set_env.sh` / `source ...env` / `ccache` / `export` → 添加 `env_setup`
- 间隙前后有 `wget` / `curl` / `obsutil cp` / `https://...obs...` → 添加 `artifact_download`
- 间隙前后有 `pip install` / `Collecting` → 添加 `pip_install`
- 间隙前后有 `Copied ... acl` / `acl header` / `ACL` → 添加 `acl_headers`
- 间隙前后是 `Building CXX object` / `Built target` → 这是编译阶段，应延长 `build_seconds`
- 间隙前后有 `[0%] Building` / `cmake` / `-- Check for working` → 这是 CMake/编译，应延长 `build_seconds`
- 间隙位于 `Pod 状态: Running` 之后且无 git clone 日志 → 可能是 `env_setup`（source env + ccache），检查间隙后的日志
- 间隙前后有 `unzip` / `tar` / `unzip opensource` → 归入 `artifact_download` 或 `env_setup`（看上下文）
- **编译中采样间隙**：如果间隙的 before/after 都是 `gcc`/`g++`/`Building CXX`/`Built target`/`[N%] Building`/`Compiling`/`Linking CXX`，间隙发生在编译阶段内部，**延长 `build_seconds`**（将 gap_seconds 累加到 build_phases.compilation）
- 无法识别的间隙 → 留在 `unattributed_seconds` 中，并在 evidence 中标注"未识别的大间隙"

### R5: 空模板清理
分析完成后，`pre_build.actions` 中所有 `duration_seconds == 0` 且无 `evidence` 的动作必须移除。禁止输出空动作列表。

### R6: summary 一致性
```python
assert abs((pre_build_seconds + build_seconds + unattributed_seconds) - total_duration) < 1.0
```
三项之和必须约等于总耗时（允许 <1s 的浮点误差）。

### R7: pre_build 总耗时与动作跨度一致性
```python
action_span = last_action_end - first_action_start
assert pre_build.total_seconds >= action_span - 1.0, \
    f"total_seconds ({pre_build.total_seconds}s) < action span ({action_span}s) — missing actions"
```
`pre_build.total_seconds` 必须 **>=** 第一个动作开始到最后一个动作结束的时间跨度（允许 <1s 误差）。如果小于跨度，说明动作之间存在未被识别的耗时（如 docker pull 检查开销、CI 脚本等待间隙），需要检查 `significant_gaps` 中未归类的间隙。

### R8: env_setup 不得作为 Pod 内阶段的垃圾桶
如果 `env_setup` 动作同时满足以下条件，说明整个 Pod 内阶段被错误合并，**必须拆分**：

1. `env_setup.duration_seconds > 20`
2. `env_setup.evidence` 中包含了 `Pod Running` 且跨越到 `编译开始` 或 `CMake` 或 `build_ext`
3. `pre_build.actions` 中缺少以下至少 2 个 Pod 内动作：`pod_git_clone`、`submodule_init`、`pip_install`、`artifact_download`、`acl_headers`

拆分方法：
- 重新阅读 `log_sample` 中 Pod Running 到编译开始之间的所有日志行
- 按动作 key 表（`pod_git_clone`、`submodule_init`、`pip_install` 等）逐一识别并分配时间
- `env_setup` 本身只保留 source env.sh + ccache init + CI 脚本 clone 的时间
- 拆分后，所有 Pod 内动作的 duration 之和必须接近原 `env_setup` 的 duration（允许 <5s 误差）

## 跨仓库对比分析

对多个仓库完成单仓分析后，可产出跨仓库对比洞察。直接从各仓库的 `*_build_analysis.json` 文件中提取数据汇总。

对比维度：
- 各仓库环境准备总耗时排名
- 最耗时的准备动作（`pod_scheduling` / `submodule_init` / `git_checkout` / `pip_install` / `network_retry` / `acl_headers`）
- 编排器对 Pod 调度耗时的影响（Argo vs Volcano vs Docker）
- 网络问题（`network_retry`）影响哪些仓库
- Pod 内阶段占 pre_build 的比例（Pod 内越重说明外部 CI 越轻）

## 多 Agent 批量分析模式

当需要同时分析多个仓库（≥3 个）时，使用多 Agent 并行模式可大幅缩短总耗时。每个仓库分配一个独立 Agent，Agent 之间完全无依赖，可并行执行。

### 模式触发

用户通过 `!` 前缀传递批量 repo 列表时自动进入多 Agent 模式：

```
/gitcode-build-time-analyzer 使用多Agent模式分析以下仓库:
  - Ascend/pytorch
  - Ascend/torchair
  - Ascend/MindIE-Motor
```

或用户明确说"多Agent模式"、"并行分析"、"批量分析"。

### 工作流程

```
Phase 1: 批量拉取（主进程串行，~10s/repo）
─────────────────────────────────────────
  for repo in repos:
      python3 fetch_build_logs.py --repo $repo --latest-merged -o json-org/$name.json
  → 汇总结果: {success: [...], errors: [...]}

Phase 2: 并行 AI 分析（Agent.per repo）
─────────────────────────────────────────
  for repo in success_repos:
      Agent(
          subagent_type="general-purpose",
          run_in_background=true,
          description="Analyze $repo builds",
          prompt=<标准分析 prompt>
      )
  → 等待所有 Agent completion notification

Phase 3: 校验与补漏（主进程）
─────────────────────────────────────────
  for repo in success_repos:
      python3 check_json.py $repo.json  # 验证 R1-R7
      if 数据为空:
          Agent(description="Re-analyze $repo", ...)  # 重分析
  → 重复直至所有 repo 通过校验

Phase 4: 跨仓库对比报告
─────────────────────────────────────────
  python3 cross_repo_report.py  # 汇总所有 JSON
```

### Phase 1 — 批量拉取脚本

```bash
for repo in Ascend/pytorch Ascend/torchair Ascend/MindIE-Motor Ascend/MindIE-SD \
            Ascend/MindIE-LLM Ascend/MindSpeed Ascend/MindSpeed-MM; do
  name=$(echo "$repo" | cut -d/ -f2)
  python3 scripts/fetch_build_logs.py --repo "$repo" --latest-merged \
    -o "json-org/${name}_build_analysis.json" 2>&1 | tail -3
done
```

拉取结果分类：
- **success**: JSON 中 `builds[]` 不含 `_error` 的记录 → 进入 Phase 2
- **no_pipeline**: `"No pipeline table found"` → 执行 Phase 1.5 PR 回退扫描
- **no_passed_builds**: `"No passed build tasks found"` → 执行 Phase 1.5 PR 回退扫描

### Phase 2 Agent 分组限制（重要）

Agent 处理能力有限，必须遵守以下限制避免数据遗漏：

| 仓库规模 | 每 Agent 仓库数 | 说明 |
|----------|----------------|------|
| >4 builds | **1 repo 独占** | 如 MindIE-LLM (10 builds)、op-plugin (12 builds) |
| 2-4 builds | **1 repo 独占** | 如 pytorch (4 builds)、MindIE-Motor (3 builds) |
| 1 build | **最多 2 repos** | 极小仓库可合并，但绝不 >2 |

> ⚠️ 教训：3-repo 合并 Agent 遗漏了 MindIE-PyMotor。2-repo 上限更安全。

### Phase 2 — Agent 标准分析 Prompt 模板

每个 Agent 必须收到包含以下要素的 prompt：

```markdown
Read `json-org/<repo>_build_analysis.json`. For EVERY build, read log_sample,
identify and time ALL pre-build actions, then write back COMPLETED JSON to the same path.

## Two-phase model:
- Phase 1 (External CI): node_assignment, docker_pull, cache_check, git_checkout,
  workspace_prep, pre_submit_validation, image_proxy, git_cache_injection,
  orchestrator_submit
- Phase 2 (Pod internal, AFTER Pod Running): pod_git_clone, env_setup,
  submodule_init, pip_install, artifact_download, acl_headers, tool_download

## Pod scheduling (CRITICAL - most common bug):
- Start: after `Volcano Job submitted` / `Workflow submitted`
- End: `Pod 状态: Running` / `找到主 Pod`
- pod_scheduling MUST be >1s — if <1s you measured WRONG, go back

## Action patterns:
[List all action keys with their log patterns from the action table above]

## Build start (pre_build ends at):
- `[N%] Building CXX object`, `Building C object`
- `-- Check for working C compiler`, `running build_ext`
- `Building wheel for <name> (pyproject.toml): started` — Python wheel builds
- `Successfully built <name>` — wheel build packaging complete

## EXACT JSON SCHEMA (MUST follow — verify before writing):

Required structure for each build in the JSON file:

- `pre_build`: object with `total_seconds` (number), `pct_of_total` (number), `orchestrator` ("volcano"|"argo"|"docker"), `actions[]` (array of action objects)
- Each action: `key`, `name`, `start` (ISO-8601), `end` (ISO-8601), `duration_seconds` (number), `evidence` (string with log excerpts)
- `build_phases`: object with `total_seconds` (number), `pct_of_total` (number), `actions[]` (array with keys: cmake_configure, compilation, packaging)
- `summary`: `pre_build_seconds`, `build_seconds`, `unattributed_seconds` (must be >=0), `key_bottleneck` (string, name of longest pre_build action), `key_bottleneck_seconds` (number)

## SCHEMA VERIFICATION CHECKLIST (verify EVERY build before Write):
□ pre_build uses "total_seconds" NOT "seconds"
□ pre_build has "pct_of_total" field
□ build_phases is an OBJECT with "total_seconds" + "pct_of_total" + "actions[]" (NOT a bare list)
□ Every action has "start"/"end" as REAL ISO-8601 timestamps (NOT "?" or empty string)
□ Every action has "evidence" with actual log line excerpts
□ R9: Applied seamless splicing — each action's end = next action's start. Last pre_build end = build start. Build compilation end = total end. unattributed < 1% or < 5s.
□ R4: Ran gap analysis if unattributed > 5s — compilation gaps → build_seconds, pod gaps → pre_build actions
□ R8: env_setup is NOT a catch-all — if >20s and evidence spans "Pod Running→编译开始", split into pod_git_clone/submodule_init/pip_install/etc
□ summary values match pre_build.total_seconds / build_phases.total_seconds
□ meta.analyzed_at is set to current time
□ orchestrator is one of: "argo", "volcano", "docker"

## Quality rules (execute in this order for EVERY build):

**Step 1 — R9 SEAMLESS SPLICING (ALWAYS do this first):**
Sort pre_build actions by start time. Set each A[i].end = A[i+1].start. Last pre_build end = build start time. Last build_phases action end = time.end. Recalculate all durations. Target: unattributed < 5s and < 1%.

**Step 2 — R4 GAP ANALYSIS (only if R9 left unattributed > 5s):**
Iterate ALL significant_gaps >5s. Compilation gaps (gcc/g++/Building CXX) → add to build_phases.compilation. Missing pod actions (git clone/Submodule/pip/wget) → add as pre_build actions. Recalculate.

**Step 3 — Remaining rules:**
- R1: unattributed = max(0, total - pre_build - build), >= 0
- R5: Remove zero-duration actions without evidence
- R6: abs(pre + build + unattributed - total) < 1.0
- R7: pre_build.total_seconds >= action span
- R8: env_setup NOT catch-all (split if >20s spanning Pod Running→build start)
- Docker repos: NO pod_scheduling, docker_pull covers multi-layer pulls
- Set orchestrator + meta.analyzed_at

Write COMPLETED JSON to `json-org/<repo>_build_analysis.json`.
```

**关键规则**：
- Agent prompt 必须包含完整的 R1-R7 校验指令
- 必须包含 **SCHEMA VERIFICATION CHECKLIST** — Agent 写完 JSON 前必须逐项检查
- 必须包含 `pod_scheduling > 1s` 的强制检查（最常见 bug）
- **`build_phases` 必须是对象不是列表** — 这是最常见的 schema 错误
- **Docker 镜像即使命中缓存也会消耗 10-25s 检查时间** — 不要遗漏 `docker_pull`
- 必须要求 Agent "Write back" 到原文件路径
- `run_in_background: true` 使 Agent 异步执行

### Phase 3 — 校验与补漏

每个 Agent 完成后，运行校验脚本验证数据完整性：

```bash
python3 scripts/validate.py json-org/<repo>_build_analysis.json
```

脚本检查 R1/R5/R6/R7/R8/R9 全部规则，以及 schema 合规性、时间戳有效性、pod_scheduling 最小值。退出码 0 = 全部通过，1 = 发现错误。

校验失败的处理（更新）：

| 症状 | 原因 | 处理 |
|------|------|------|
| `empty > 0` 且 `analyzed_at` 有值 | Agent 写了空模板 | **重分析**：prompt 开头强调 "The current data is WRONG — all actions are empty. You MUST fill in actual timing data" |
| `analyzed_at` 为 null | Agent 未完成 | 等待或重启 Agent |
| `pod_scheduling < 1s`（非 Docker） | 旧 bug 未修复 | **重分析**：prompt 中强调 pod_scheduling 完整等待测量 |
| R6 校验失败 | 计算错误/漏动作 | **重分析**：指出具体 build 和缺少的秒数 |
| **SCHEMA FAIL** | Agent 用了错误 JSON 结构 | **重分析**：prompt 必须包含完整 JSON SCHEMA 示例 |
| **R5 FAIL** | 零时长动作未清理 | 手动清理或重分析 |
| **R7 FAIL** | total_seconds < 动作跨度 | docker_pull 等动作间间隙未被捕获 |
| **R8 FAIL** | env_setup >20s 合并了多个 Pod 内动作 | **重分析**：prompt 强调 "env_setup is NOT a catch-all." |
| **R9 FAIL** | unattributed > 5s 或 > 1% | **重分析**：prompt 强调 "Apply seamless splicing: each action's end = next action's start. Last pre_build end = build start. Compilation end = total end." |
| **R4 WARN** | 有未识别的 >5s 间隙 | **重分析**：检查间隙日志内容并归入对应阶段 |

**重分析 Agent prompt 必须包含**：
> "The current file has [具体校验错误]. This is WRONG and must be fixed. Re-read the log_sample and fill in EVERY action with actual timing data. Follow the EXACT JSON SCHEMA — pre_build.total_seconds (not 'seconds'), build_phases as object with total_seconds, real ISO timestamps."

### Phase 4 — 跨仓库对比报告

所有 Agent 完成后，生成对比报告：

```bash
python3 << 'PYEOF'
import json, os

workdir = '.'
repos_data = {}
files = [f for f in os.listdir('json-org') if f.endswith('_build_analysis.json')]

for fname in files:
    with open(os.path.join('json-org', fname)) as f:
        d = json.load(f)
    name = fname.replace('_build_analysis.json', '')
    builds = [b for b in d.get('builds', []) if not b.get('_error') and b.get('pre_build', {}).get('total_seconds', 0) > 0]
    if not builds:
        continue
    
    pre = [b['pre_build']['total_seconds'] for b in builds]
    bld = [b['build_phases']['total_seconds'] for b in builds]
    orch = builds[0]['pre_build'].get('orchestrator', '?')
    
    # Collect per-action stats
    actions = {}
    for b in builds:
        for a in b['pre_build'].get('actions', []):
            k, dur = a['key'], a.get('duration_seconds', 0)
            if dur > 0:
                actions.setdefault(k, []).append(dur)
    
    repos_data[name] = {
        'n': len(builds), 'orch': orch,
        'pre_avg': sum(pre)/len(pre),
        'pre_pct': sum(pre)/(sum(pre)+sum(bld))*100,
        'top_actions': sorted(actions.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)[:3],
    }

# Print comparison tables
print(f"{'Repo':<20} {'N':>3} {'Orch':>8} {'PreAvg':>8} {'Pre%':>6} {'Top Bottlenecks'}")
print("-" * 80)
for name in sorted(repos_data):
    r = repos_data[name]
    tops = ' | '.join(f'{k}={sum(v)/len(v):.0f}s' for k,v in r['top_actions'])
    print(f"{name:<20} {r['n']:>3} {r['orch']:>8} {r['pre_avg']:>7.1f}s {r['pre_pct']:>5.1f}% {tops}")

# Pod scheduling comparison
print("\nPod调度对比:")
for name in sorted(repos_data):
    ps = repos_data[name].get('actions', {}).get('pod_scheduling', []) if 'actions' in repos_data[name] else []
    if ps:
        print(f"  {name:<20} avg={sum(ps)/len(ps):.0f}s  min={min(ps):.0f}s  max={max(ps):.0f}s")
PYEOF
```

### 批量分析完整示例

用户输入：
```
/gitcode-build-time-analyzer 分析 MindIE 系列: MindIE-Motor, MindIE-SD, MindIE-PyMotor, MindIE-LLM
```

执行过程：
1. 串行 fetch 4 个仓库（~40s）
2. 并行启动 4 个 Agent（每个 ~5-8min，并行总耗时 ~8min）
3. 校验 4 个 JSON，发现 MindIE-LLM 数据为空 → 重分析
4. MindIE-LLM Agent 重跑（~9min）
5. 生成跨仓库对比报告

总耗时：约 15-20 分钟（vs 串行 40+ 分钟）。

### 经验教训

以下从 2026-06-17 的 10 仓库批量分析实战中总结，每次运行后持续更新。

#### Agent Schema 合规性（最常见失败原因）

- **Schema 偏差率 ~50%**：首轮 4 个 Agent 中 2 个写错了 JSON 结构
  - `pre_build.seconds` 代替 `pre_build.total_seconds`
  - `build_phases` 写成裸列表而非 `{total_seconds, pct_of_total, actions:[]}` 对象
  - 所有 `start`/`end` 写为 `"?"` 字符串
  - `summary` 全部字段为零
- **对策**：Agent prompt 必须包含 **SCHEMA VERIFICATION CHECKLIST**，逐项自检后才能 Write
- **R5 常被忽略**：`image_proxy`/`git_cache_injection`/`orchestrator_submit` 常被写为 duration=0 但保留在原位，务必删除

#### R6 失败根因：缺失的 docker_pull

- MindIE-SD 首轮 pre_build 只有 46s，R6 差 17-22s
- 根因：Docker 镜像即使 `Image is up to date`（命中缓存），daemon 检查仍消耗 11-12s
- 3 次镜像检查（shell + karmada + toolchain）分散在 CI 步骤间，容易被遗漏
- **对策**：R7 规则（total_seconds >= action span）+ R4 大间隙兜底可捕获此问题

#### PR 回退必要性

- `--latest-merged` 在 6/10 仓库中选到了 docs-only PR
- MindSpeed-LLM 30 个 PR 全部无 Build 任务——该仓库确实只有代码检查流水线
- **对策**：Phase 1.5 自动回退扫描，最多 20 个 PR

#### Agent 分组上限

- 3-repo 合并 Agent 遗漏了 1 个仓库 (MindIE-PyMotor)
- **对策**：1 build 仓库最多合并 2 个；>4 builds 仓库必须独占 Agent

#### 各仓库特征

- **MindIE-LLM (10 builds)**：最重仓库，~4000 行 log_sample，优先启动 Agent
- **op-plugin (12 builds)**：12 个构建，注意区分 master（仅 artifact download）和 versioned（含 C++ 编译）
- **Docker 原生仓库** (MindSpeed 系列)：无 pod_scheduling，关注 docker_pull 多层镜像拉取
- **MindIE-PyMotor**：Volcano 调度，仅 1 个 ARM 构建任务
- **pytorch**：4 个构建，子模块初始化是最大瓶颈（~32s），包含 LibTorch 独立构建
- **Python wheel-only 构建**（MindIE-LLM linux builds）：注意 `Building wheel for ... (pyproject.toml): started` 作为构建开始标志
- CANN 项目仓库（`cann/*`）：API 限制导致所有构建标记 `_error`，无法批量分析

#### pod_scheduling 极端值

- Volcano 调度波动可达 13 倍（14s ~ 185s）
- MindIE-LLM arm_abi0 构建 Pod 调度 185s，是第二名（op-plugin 62s）的 3 倍
- Argo 调度稳定在 15-17s，波动仅 1.1 倍
- 校验时非 Docker 仓库强制检查 `pod_scheduling > 1s`

## 前置条件

- `gitcode` (或 `gc`) CLI 已登录且可用
- 可访问 `www.openlibing.com` API
- Python 3.9+ (仅标准库)

## 局限

- 仅分析 **passed** 构建任务
- openLiBing API 偶尔对部分 job 返回 500
- 时间戳硬编码为 `GMT+08:00`
- 日志采样限制在 ~400 行；AI 可能看不到完整细节
- 如果 PR 没有流水线评论，无法分析
- `cann/ops-nn` 等仓库的 openLiBing 链接不含 job 级参数，无法拉取日志

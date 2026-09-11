# Aether AGENTS.md — Agent 协作约定

本文件合并了原 `AGENT.md`（Agent Guide）与协作约定，是本仓库面向 Agent 的**唯一**入口文档。
克隆后仓库根在 `GitHub/labs/aether`；文档内路径均相对仓库根，除非另作说明。

## 项目是什么

Aether 是一个 Codex 插件：将参考图、提示词想法与生图结果沉淀为**可复用的视觉记忆**，
支持带记忆的提示词精修、图像生成记账（bookkeeping）、素材归档、视觉一致性评审与
视觉体系演进（记忆/变体/合并候选）。主包 `plugins/aether`，Python 核心
`plugins/aether/src/aether_core`（标准库 unittest）。

## 项目结构（Project Shape）

- 主插件包：`plugins/aether`
- Python 包：`plugins/aether/src/aether_core`
- Codex 插件清单：`plugins/aether/.codex-plugin/plugin.json`
- 技能入口（`plugins/aether/skills/`）：
  - `aether-orchestrator`（总调度）
  - `visual-memory`（视觉记忆查询/浏览）
  - `visual-asset-capture`（沉淀素材）
  - `prompt-refine`（精修提示词）
  - `image-generate`（生图/编辑）
- CLI 入口：`plugins/aether/src/aether_core/cli.py`（`python -m aether_core.cli`）

## 常用命令（仓库根目录）

```bash
make test            # PYTHONPATH=plugins/aether/src uv run --frozen python -m unittest discover -s plugins/aether/tests
make doctor          # 运行 aether CLI doctor，验证本地安装/配置
make schemas         # 校验 plugins/aether/schemas/*.json
make validate        # 载荷校验器冒烟
make verify          # bash scripts/verify_aether_layout.sh：配置/符号链接/数据目录体检
make pack            # npm pack --dry-run，打包前验证
make install-local   # 安装到本地 Codex 插件缓存
make cache-sync      # 源码改动同步进 Codex 插件缓存（见「插件缓存」）
```

`make` 目标与原命令等价（见 `Makefile`）。有用的原生校验：

```bash
python -m json.tool plugins/aether/schemas/visual-asset.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/visual-asset-candidate.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/prompt-record.schema.json >/dev/null
python -m json.tool plugins/aether/schemas/generation-run.schema.json >/dev/null
node scripts/aether-plugin.js doctor
npm pack --dry-run
```

提交前必须：`git diff --check` + `make test`。

## 配置与数据（Configuration And Data）

配置查找顺序在 `aether_core.config` 中实现（`find_config`）：

1. `~/.config/aether/config.json`
2. 最近的 workspace `config.json`
3. 当前目录 `.aether/config.json`

本机活动插件配置通常在 `~/.aether/codex-plugin/config.json`。
**不要假设** repo 内 `plugins/aether/config.json` 就是活动运行时配置，确认用：

```bash
aether config show
```

运行时数据应在插件安装目录之外，典型路径：

- SQLite 数据库：`~/.aether/data/aether.sqlite`
- 参考素材：`~/.aether/data/assets/references`
- 生成素材：`~/.aether/data/assets/generated`
- 缓存：`~/.aether/data/cache`

**不删除、不改写用户数据目录**，除非用户明确要求。

## 核心数据规则（Core Data Rules）

- 视觉素材在 SQLite `visual_assets`
- 待分析图片模块在 SQLite `visual_asset_candidates`
- 提示词记录在 SQLite `prompt_records`
- 生成记录在 SQLite `generation_runs`
- 图像编辑也是 generation 记录（`mode: edit`），保留源生成与源输出血缘
- 参考图与生成图文件均资产化管理
- 成功的生成输出必须先经 `aether_core.output_archiving` 归档，再记 generation run
- 提示词记录应保留 `generation_params`（含 `aspectRatio`）
- 生成记录应保留最终 `skill_params`、已归档 `outputs` 与 `visual_review`

## 技能工作流规则（Skill Workflow Rules）

- `visual-memory` 只用于列出/检视已持久化的视觉素材、视觉体系、recipe、候选、
  生成历史、证据、质量统计与本地素材清单。
- `visual-asset-capture` 用于参考图、截图、源图提示词或可复用视觉素材沉淀。
- 用户给出原始/模糊文本提示词时，生图**前**先 `prompt-refine`。
- `image-generate` 只在用户明确要求生成/创建/渲染/输出新图，或编辑已有生成图时使用。
- 未经用户确认新精修出的提示词，不调用付费/外部生图（除非明确选择了自动生成）。
- 视觉评审是**建议性**的：不自动丢弃/覆盖/合并/重生成，须用户确认。

## 测试期望（Testing Expectations）

改动涉及以下内容时补针对性测试：

- 存储 schema 或迁移行为
- CLI 命令行为
- 内置技能脚本
- 生成素材归档
- 提示词/生成参数透传
- 视觉评审持久化
- 聊天附件提取

优先 `unittest`（仓库当前用标准库 runner）；`pytest` 可能未安装。
提交信息用中文 + `type:` 前缀。

## 插件缓存（Installed Plugin Cache）

已安装的 Codex 插件缓存独立于本仓库，通常在：

`~/.codex/plugins/cache/aether/aether/<version>`

**源码改动不会自动传播到缓存。** 若用户要求行为在当前 Codex 会话立即可用
（通过 `$aether:*`），须把改动同步到缓存并在那边验证；源码仍是权威实现。

## 布局体检（Layout Verification）

任何关于"配置 / 符号链接 / panel / 我的图存在哪"的问题，先跑：

```bash
bash scripts/verify_aether_layout.sh
```

它检查：全局符号链接 `~/.config/aether/config.json` 指向
`~/.aether/codex-plugin/config.json`；全局配置用绝对存储路径（非 dev 模板）；
运行时数据目录与 SQLite 存在；运行中的 panel 读的是全局 DB；没有残留的
`plugins/aether/.aether/`（项目本地数据）。

若再出现"panel 看不到新图"这类 bug，先跑此脚本。最常见根因是全局符号链接被
（重新）指向 `plugins/aether/config.json`（相对路径的 dev 模板），而不是安装改写后的
全局配置。重跑 `plugins/aether/scripts/install-local.sh` 恢复标准布局。

**符号链接安全检查**：`aether_core.config.find_config` 在全局符号链接存在时拒绝
静默使用 dev 模板——解析出的符号链接目标是相对 `storage.databasePath`（dev 模板
特征）会触发；运行时给出明确错误并建议 `install-local.sh`，开发者可用
`AETHER_ALLOW_PROJECT_CONFIG=1` 退出检查。

## 缓存同步提醒（Cache Sync Reminder）

`plugins/aether/src/aether_core/` 的改动不自动传播到
`~/.codex/plugins/cache/aether/aether/<version>/`。编辑源码后 `make cache-sync`
（或手动 cp 对应文件）：

```bash
cp plugins/aether/src/aether_core/config.py \
   ~/.codex/plugins/cache/aether/aether/0.1.0/src/aether_core/config.py
rm -rf ~/.codex/plugins/cache/aether/aether/0.1.0/src/aether_core/__pycache__
```

其余源文件同理。随后从一个**不含自身 `config.json`** 的目录（如 `/tmp`）重启 panel，
确保全局符号链接成为实际使用的发现路径。

## 编辑注意（Editing Notes）

- 生成的运行时数据保持 git 外（.agent/、缓存、数据副本）。
- 当前视觉记忆相关工作不要求兼容旧式工作流，除非用户明确要求。
- 精修提示词保留用户原始意图：不替换核心主体、场景、动作、情绪或显式约束。
- 供应商特定的生图细节留在技能/配置边界之后。
- 避免在做本任务时对技能指令或脚本做大范围无关重构。

## 禁忌（Taboos）

- 不把生成的运行时数据提交进 git。
- 不假设 repo 内 `plugins/aether/config.json` 是活动配置——用 `aether config show`
  或 `make verify` 实求真。
- 不擅自改技能指令/脚本做与本任务无关的大重构。
- 不删除/改写 `~/.aether/data/` 用户数据。
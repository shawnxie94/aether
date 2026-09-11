# Aether AGENTS.md — Agent 协作约定

面向在本仓库工作的 Agent。项目内部机制与数据规则的**细节**见作者维护的
[`AGENT.md`](AGENT.md)（先读它），本文件只放 Agent 高频需要的入口与纪律。

## 项目是什么

Aether 是一个 Codex 插件：将参考图、提示词想法与生图结果沉淀为**可复用的视觉记忆**，
支持带记忆的提示词精修、视觉体系演进（记忆/变体/合并候选）与生成反馈闭环。
主包 `plugins/aether`，Python 核心 `plugins/aether/src/aether_core`（标准库 unittest）。

## 常用命令（仓库根目录）

```bash
make test            # PYTHONPATH=src python -m unittest discover -s plugins/aether/tests
make doctor          # 运行 aether CLI doctor，验证本地安装/配置
make schemas         # 校验 plugins/aether/schemas/*.json
make validate        # 载荷校验器冒烟
make verify          # bash scripts/verify_aether_layout.sh：配置/符号链接/数据目录体检
make pack            # npm pack --dry-run，打包前验证
make install-local   # 安装到本地 Codex 插件缓存
make cache-sync      # 源码改动同步进 Codex 插件缓存（见下）
```

## 入口与结构

- Codex 插件清单：`plugins/aether/.codex-plugin/plugin.json`
- CLI 入口：`plugins/aether/src/aether_core/cli.py`（`python -m aether_core.cli`）
- 技能入口（`plugins/aether/skills/`）：
  - `aether-orchestrator`（总调度）；`visual-memory`（查询/浏览）；
  - `visual-asset-capture`（沉淀素材）；`prompt-refine`（精修提示词）；
  - `image-generate`（生图/编辑）
- 数据：SQLite `visual_assets` / `visual_asset_candidates` / `prompt_records` / `generation_runs`
  在 `~/.aether/data/` 下，素材文件资产化管理；**不在 repo 内的运行时数据目录，不要删除或重写**。

## 工作流规则

- 技能分工严格：`visual-memory` 只做查询；沉淀用 `visual-asset-capture`；
  生图前先 `prompt-refine`；`image-generate` 只在用户明确要生成/编辑时用。
- 未确认精修后的提示词前，不调用付费/外部生图；视觉评审是建议性的，
  不自动丢弃/覆盖/合并/重生成任何东西，须用户确认。
- 生成输出先经 `aether_core.output_archiving` 归档再记 generation run。

## 测试与提交

- 改动涉及存储 schema/迁移、CLI 行为、技能脚本、归档、参数透传、视觉评审持久化、
  附件提取时，补针对性测试。
- 用 `unittest`（仓库当前用标准库 runner）；`pytest` 可能未装。
- 提交前：`git diff --check` + `make test`。提交信息用中文 + type: 前缀。

## 禁忌（Taboos）

- 不把生成的运行时数据提交进 git（.agent/、缓存、数据副本）。
- 不假设 repo 内 `plugins/aether/config.json` 是活动配置——真实验证 `aether config show`
  或 `make verify`（全局符号链接优先）。
- 不擅自改技能指令/脚本做与本任务无关的大重构。
- 精修提示词时保留用户原始意图（主体、场景、动作、情绪、显式约束不被替换）。

## 别忘了：Codex 插件缓存

编辑 `plugins/aether/src/` 不会自动传播到 `~/.codex/plugins/cache/...`。
需要当前 Codex 会话立即可用时，改完执行 `make cache-sync`（或按 AGENT.md 手动 cp），
不要只改源码就宣称已生效。
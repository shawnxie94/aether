---
id: aether-architecture-stabilization-v1
type: execution_plan
status: completed
created_at: 2026-09-11
updated_at: 2026-09-11
sources:
  - docs/plan/project-roadmap.md
  - docs/plan/evolvable-visual-memory-plan.md
  - plugins/aether/AGENTS.md
  - plugins/aether/src/aether_core/storage.py
  - plugins/aether/src/aether_core/migrations.py
related:
  - docs/plan/project-roadmap.md
  - docs/plan/evolvable-visual-memory-plan.md
base_commit: 6d6b9dfb92b51a4f32a5d04432f6e151161cc673
orchestration_mode: batch
execution_target: current_session
execution_backend: pi
---

# Aether 架构收敛批次 V1

## Implementation Goal

在不改变现有 CLI、Skill、Panel API 和数据语义的前提下，完成第一轮低风险架构收敛：统一 Python/测试运行契约；将 generation relation 字段纳入正式 migration；把生图记录 orchestration 从 CLI 抽到应用服务；补齐旧数据库、失败路径和幂等行为保护。

本批次不做数据库整体重写，不引入 ORM、服务端数据库、消息队列或新的外部 provider。

## Execution Decision

- orchestration_mode: `batch`
- execution_target: `current_session`
- execution_backend: `pi`
- parallel_mode: `serial_shared_writer`
- actor: one writer
- rationale: migration、Makefile、generation service、storage 和测试共享公共契约，不适合并行写入。

## Behavior Protection

- 以现有 `PYTHONPATH=plugins/aether/src uv run --frozen python -m unittest discover -s plugins/aether/tests` 作为基线和最终验收。
- 保持所有现有 CLI 子命令和参数不变。
- 保持 generation payload、outputs、selected_assets、review、evidence 的 JSON 结构不变。
- 增加 migration upgrade、generation service delegation、失败记录和重复归档相关测试。
- 使用临时 SQLite 和临时资产目录测试，不接触 `~/.aether/data`。

## Scope

### Included

1. 运行环境契约
   - 统一根项目和插件 Python 最低版本为 3.10。
   - 让 Makefile 测试/CLI 命令使用 lockfile 环境，并对 Python 版本失败给出清晰结果。
   - 增加 GitHub Actions 的最小 CI：依赖安装、unit tests、schemas、validate、npm package doctor。

2. Schema migration
   - 在 `generation_runs` 的初始 DDL 中声明 `recipe_id`、`visual_system_id`、`subject_asset_id`。
   - 新增正式 migration（v8）为旧数据库补齐三列。
   - 删除 `create_generation_run` 写路径中的运行时 schema 修改。
   - 保持旧数据库可升级，且 migration 幂等。

3. Generation application boundary
   - 新增 `aether_core/generation_service.py`，集中封装 generation record 的参数合并、输出归档、relation 补全和 store 写入。
   - CLI 仅负责解析参数和调用 service；现有 `aether generation record` 行为不变。
   - service 显式保留失败路径：失败记录不归档不存在的输出，并继续使用现有 review placeholder 逻辑。

4. Targeted tests and documentation
   - 增加上述新边界的单元测试。
   - 更新 Makefile/安装说明中的实际命令。
   - 在 roadmap 中保留本批次的完成标准，暂不宣称完整 `AetherStore` 拆分完成。

### Excluded

- 全量拆分 `storage.py` 为多个 repository/service。
- 改变 SQLite JSON 字段模型或引入 ORM。
- 改造 Panel 前端、Panel API 或缓存算法。
- 改造 embedding provider、recall 权重或图像指纹算法。
- 用户数据迁移、全局安装、marketplace 注册和发布 npm 包。

## Execution Sequence

1. **基线和契约**
   - 检查工作区与 base commit。
   - 建立/复用锁定环境，运行全量测试基线。
   - 修改 Python 版本、Makefile 和 CI 配置。
   - 验证 Makefile、schemas、validate 和 CI 配置静态有效。

2. **migration v8**
   - 修改 fresh schema DDL。
   - 新增 v8 migration。
   - 修改 generation 写路径，移除运行时加列。
   - 添加旧 schema 升级和新库初始化测试。
   - 运行 migration/storage 相关测试。

3. **提取 generation service**
   - 把 `cmd_generation_record` 的应用编排移动到 service。
   - 保留 CLI 参数和输出格式。
   - 为 service 添加成功、失败、edit lineage、relation injection 测试。
   - 运行 generation、assets、storage、panel 相关测试。

4. **最终验证和文档收敛**
   - 运行全量测试、schema、validate、package doctor、`git diff --check`。
   - 检查变更文件和禁止范围。
   - 更新 roadmap 条目状态/完成说明。

## Write Ownership

- `Makefile`
- `package.json`
- `pyproject.toml`
- `AGENTS.md`
- `plugins/aether/pyproject.toml`
- `plugins/aether/src/aether_core/storage.py`
- `plugins/aether/src/aether_core/migrations.py`
- `plugins/aether/src/aether_core/cli.py`
- `plugins/aether/src/aether_core/generation_service.py`（new）
- `plugins/aether/tests/` 中与本批次直接相关的测试
- `.github/workflows/ci.yml`（new）
- `docs/plan/project-roadmap.md`
- `docs/install.md`（如命令说明需要同步）

## Forbidden Writes

- `~/.aether/data/`
- `~/.codex/plugins/cache/`
- `plugins/aether/skills/`（本批次不改 Skill 协议）
- `plugins/aether/src/aether_core/panel/`
- `package-lock.json`、`uv.lock`（除非依赖解析确实要求；默认不改）
- 不删除、不重写用户已有数据库或图片。

## Final Acceptance

必须全部满足：

1. `PYTHONPATH=plugins/aether/src uv run --frozen python -m unittest discover -s plugins/aether/tests` 通过。
2. `make test` 在锁定环境下可运行并通过。
3. `make schemas`、`make validate`、`node scripts/aether-plugin.js doctor` 通过。
4. 旧版 generation schema 可以升级到 v8，且 migration 重复执行不改变结果。
5. `aether generation record` 的现有调用路径和 payload 输出保持兼容。
6. `git diff --check` 通过。
7. 不产生对 `~/.aether/data`、Codex cache 或用户图片的写入。

## Rollback

- 所有改动保持在当前分支，未执行 commit/push。
- 若 generation service 行为不一致，可恢复 CLI 原调用路径，保留独立 migration 和测试。
- 若 migration 测试失败，停止后续拆分，不触碰用户数据库；只修复 fresh/legacy 临时数据库测试。

## Remote Handoff Inputs

- execution_target: current_session; implementation completed in the current session。
- batch contract: one writer executes the complete scope above and returns one final acceptance result。
- required skills: `refactor-plan`, `implement-plan`, `prepare-commit`。
- acceptance phase: `integration`。
- acceptance barrier: `none`。

# Aether 可演进视觉记忆方案

## 1. 背景与目标

Aether 当前已经能从参考图、生成结果和用户反馈中沉淀 `visual_asset`、`recipe`、`visual_system`。后续核心问题不是“能不能保存”，而是长期使用后如何避免三类对象数量爆炸、语义漂移和重复沉淀。

本方案目标：

- 让 assets、recipes、visual systems 都从静态记录升级为可演进知识对象。
- 由 Codex 智能体基于混合召回结果给出 `新增`、`归属`、`继承`、`合并` 建议。
- 所有召回判断必须走 Aether storage 的 hybrid/embedding 召回，不受模型预填字段或旧 payload 影响。
- 合并和继承不能简单 append，需要基于多个对象重新抽象，控制 prompt 参数和规则数量。
- 改动核心语义时必须有 revision/evidence 记录，避免 silent overwrite。

## 2. 对象分层

### 2.1 Visual Asset

`visual_asset` 是最小可复用视觉原子，也是最容易膨胀的一层。

典型类型包括：

- `style`
- `color_palette`
- `lighting`
- `composition`
- `character`
- `scene`
- `prop_symbol`
- `shape_line`
- `mood`

演进原则：

- 高频产生，必须严格去重。
- 抽象型资产如 `mood`、`composition`、`color_palette` 更容易重复，应提高归属阈值。
- 具体实体型资产如 `character`、`scene`、`prop_symbol` 应避免误合并。
- 候选资产默认先作为 evidence，不应轻易创建新资产或新 variant。

### 2.2 Recipe

`recipe` 是中层组合模式，描述一类图如何组合 assets、构图、主体、用途和比例。

演进原则：

- 比 visual system 更容易产生变体。
- 相似但用途、题材或场景稳定不同，应创建 variant，而不是直接合并。
- 高相似且规则没有稳定差异时，可以更新已有 recipe。
- 合并必须重新抽象 composition rules，不能累加所有规则。

### 2.3 Visual System

`visual_system` 是慢变量，承载世界观、美术方向、系列、类型或稳定 art direction。

演进原则：

- 不应被单张图轻易改写核心定义。
- 可以吸收稳定 evidence、资产关系、来源引用和少量高层规则。
- 当候选与已有 system 同源但出现稳定分支时，应继承为子 system。
- 合并只适用于两个已成形 system 的同层级重复表达。

## 3. 四类动作定义

### 3.1 新增

`新增` 表示没有合适的已有对象承接候选，需要创建新对象。

适用条件：

- hybrid 相似分低。
- 没有明显父对象。
- 候选包含新的稳定视觉语义。
- 新对象不会只是已有对象的同义改写。

执行结果：

- asset: 创建新 `visual_asset`。
- recipe: 创建新 `recipe`。
- visual system: 创建新 `visual_system`。
- 记录来源 candidate 和 evidence。

### 3.2 归属

`归属` 表示候选只是已有对象的一次实例、证据或使用样本，不改变已有对象的核心抽象。

适用条件：

- hybrid 相似分高。
- novelty 低。
- conflict 低。
- 与已有对象同类型、同粒度。

执行结果：

- asset: 不创建新 asset，只把候选挂到目标 asset 的 evidence。
- recipe: 不创建新 recipe，只补充 evidence、使用统计或可选样例。
- visual system: 不创建新 system，只补充 evidence、source refs 和资产关系。

注意：

- 归属不是 append prompt fragments。
- 归属默认不改 `name`、`summary` 和核心 rules。

### 3.3 继承

`继承` 表示候选和已有对象同源，但有稳定差异，适合作为子对象或 variant。

适用条件：

- hybrid 相似分中高。
- 与已有对象共享核心风格或结构。
- 出现稳定的新用途、新场景、新符号系统、新构图目标或新约束。
- 差异不是一次性噪声。

执行结果：

- asset: 创建 `variant_of` / `parent_asset_id` 指向父 asset。
- recipe: 创建 `parent_recipe_id` 指向父 recipe 的 variant。
- visual system: 创建 `parent_system_id` 指向父 system 的子方向。
- 子对象只保存差异化抽象和继承关系，不复制父对象全部规则。

### 3.4 合并

`合并` 表示两个已存在对象本质重复，应归一到 canonical 对象。

适用条件：

- hybrid 相似分很高。
- 两者同类型、同层级、同粒度。
- novelty 低。
- conflict 低或可被归纳为条件规则。
- 智能体判断两者不是父子关系，而是重复表达。

执行结果：

- 选定 canonical 对象。
- 基于两个对象重新抽象 canonical definition。
- 迁移 evidence、关系和引用。
- duplicate 对象标记为 `merged_into` 或 archived，不再参与默认召回。
- 写入 merge revision 和 before/after diff。

注意：

- 合并不是 A + B append。
- 合并产物是 `abstract(A, B)`。
- 合并默认需要用户确认。

## 4. 触发逻辑与评分

动作判断不能只看一个相似分。建议使用以下指标：

```text
hybrid_similarity = hybrid_recall 返回的综合相似分
semantic_score = embedding 语义相似度
lexical_score = 关键词/文本重叠分
relation_score = 资产、system、recipe 关系重叠分
quality_score = 历史质量和使用反馈分
novelty_score = 候选中目标对象没有覆盖的新稳定信息比例
conflict_score = 候选与目标对象规则冲突程度
scope_match = 类型、层级、粒度是否一致
```

### 4.1 Asset 初始阈值

assets 数量最容易爆炸，应最保守。

| 分数区间 | 默认建议 | 智能体判断重点 |
| --- | --- | --- |
| `< 0.55` | 新增 | 是否真有稳定可复用语义 |
| `0.55 - 0.72` | 新增或继承 | 是否是已有 asset 的稳定子类型 |
| `0.72 - 0.88` | 归属或继承 | 差异是否值得成为 variant |
| `>= 0.88` | 归属 | 是否只是已有 asset 的 evidence |

类型修正：

- `mood`: 提高新增门槛，优先归属，避免情绪资产泛滥。
- `color_palette`: 只有主辅色角色和使用语义都不同才继承或新增。
- `composition`: 只有构图骨架和视觉动线稳定不同才继承。
- `style`: 媒介、笔触、渲染、边缘处理一致时优先归属。
- `character` / `scene` / `prop_symbol`: 身份不同通常不合并，优先继承或新增。

### 4.2 Recipe 初始阈值

| 分数区间 | 默认建议 | 智能体判断重点 |
| --- | --- | --- |
| `< 0.58` | 新增 | 是否是全新组合模式 |
| `0.58 - 0.72` | 新增或继承 | 用途/题材差异是否稳定 |
| `0.72 - 0.86` | 归属或继承 | 是否应更新 existing recipe 或创建 variant |
| `>= 0.86` | 归属或合并候选 | 是否同层级重复 |

recipe 中 `继承` 通常比 `合并` 更常见，因为同一风格下会自然产生场景、比例、用途和主体差异。

### 4.3 Visual System 初始阈值

| 分数区间 | 默认建议 | 智能体判断重点 |
| --- | --- | --- |
| `< 0.58` | 新增 | 是否形成独立美术方向 |
| `0.58 - 0.72` | 新增或继承 | 是否是已有 system 的分支 |
| `0.72 - 0.86` | 归属或继承 | 是否只是证据，还是稳定子方向 |
| `>= 0.86` | 归属或合并候选 | 是否同层级重复 |

visual system 中 `合并` 必须特别谨慎，只应用于两个正式 system 的重复治理，不应由单个候选自动触发。

## 5. 智能体判断输出

Codex 智能体不直接决定最终写库动作，而是给出结构化建议和理由。

建议输出格式：

```json
{
  "entity_type": "visual_system",
  "candidate_id": "system_candidate_xxx",
  "recommended_action": "inherit",
  "target_id": "visual_system_art-direction",
  "confidence": 0.74,
  "scores": {
    "hybrid_similarity": 0.7234,
    "semantic_score": 0.7012,
    "lexical_score": 0.318,
    "relation_score": 0.5,
    "novelty_score": 0.42,
    "conflict_score": 0.08,
    "scope_match": true
  },
  "novelty": [
    "festival-prosperity symbol set",
    "ultra-wide event banner composition"
  ],
  "conflicts": [],
  "reason": "Shares the core oriental painterly fantasy language, but introduces a stable festival-prosperity branch rather than a duplicate art direction.",
  "requires_user_confirmation": true
}
```

动作枚举：

- `create_new`
- `attach_evidence`
- `inherit_variant`
- `merge_existing`
- `needs_review`
- `ignore`

中文展示可映射为：

- `新增`
- `归属`
- `继承`
- `合并`
- `待判断`
- `忽略`

## 6. 执行逻辑

### 6.1 Asset 执行

#### 新增

创建新 `visual_asset`，写入：

- `type`
- `name`
- `summary`
- `tags`
- `profile`
- `prompt_fragments`
- `negative_fragments`
- `source_references`
- evidence

#### 归属

不创建新 asset。

写入：

- `visual_asset_evidence`
- source reference
- generation/candidate confirmation 记录
- 使用统计

默认不改：

- `name`
- `summary`
- `profile`
- `prompt_fragments`
- `negative_fragments`

#### 继承

创建 variant asset：

- `parent_asset_id`
- `variant_reason`
- `variant_delta`
- 差异化 `profile`
- 差异化 prompt fragments

父 asset 继续作为更高层抽象参与召回。

#### 合并

执行 `abstract(asset_a, asset_b)`：

- 重新归纳 `profile`
- 压缩 prompt fragments
- 去噪 tags
- 冲突内容转为 conditional notes 或丢弃
- 迁移 recipes/systems/generation evidence
- 被合并 asset 标记 `merged_into_asset_id`

### 6.2 Recipe 执行

#### 新增

创建新 recipe，写入：

- `composition_rules`
- `required_asset_types`
- `recommended_aspect_ratios`
- `use_cases`
- `assets`
- parent system refs
- evidence

#### 归属

不创建新 recipe。

写入：

- recipe evidence
- generation/candidate source
- 使用统计
- 可选 examples

只有在证据足够且用户确认后，才更新 recipe 的规则。

#### 继承

创建 recipe variant：

- `parent_recipe_id`
- `variant_scope`
- `variant_delta`
- 差异化 composition rules
- 差异化 asset role weights

适用于同一父 recipe 下的不同题材、比例、活动类型或主体组合。

#### 合并

执行 `abstract(recipe_a, recipe_b)`：

- 重新抽象 composition rules
- 合并 required asset roles，而不是复制全部 asset 列表
- 保留高置信 use cases
- 删除重复或低价值规则
- 冲突规则变成条件规则
- 迁移 assets、systems、evidence、generation history
- duplicate recipe 标记 `merged_into_recipe_id`

### 6.3 Visual System 执行

#### 新增

创建新 visual system，写入：

- `kind`
- `name`
- `summary`
- `tags`
- `visual_rules`
- `avoid_rules`
- `source_reference_ids`
- assets
- evidence

#### 归属

不创建新 system。

写入：

- system evidence
- source refs
- 资产关系
- 使用统计

默认不改核心：

- `name`
- `summary`
- `visual_rules`
- `avoid_rules`

#### 继承

创建子 system：

- `parent_system_id`
- `inheritance_scope`
- `system_delta`
- 差异化 visual rules
- 差异化 avoid rules
- 差异化 recipe/asset relations

适用于世界观、美术方向或系列下的新分支。

#### 合并

执行 `abstract(system_a, system_b)`：

- 重新抽象 visual rules
- 统一 tags 和 summary
- 冲突规则降级为 conditional rules
- 迁移 assets、recipes、source refs、evidence
- duplicate system 标记 `merged_into_system_id`

visual system merge 默认需要人工确认。

## 7. 重新抽象策略

为了避免参数爆炸，所有 merge 和重要 extend 都应走“重新抽象”，而不是 append。

### 7.1 规则归纳

对 `visual_rules` 和 `composition_rules`：

- 相同 `key` 下的近义规则合并成更高层表达。
- 只保留高频、高置信、可复用规则。
- 一次性画面细节不进入核心规则。
- 冲突规则写成条件表达，例如“在节庆活动图中使用金红灯笼光，在自然秘境图中使用青绿散射光”。

### 7.2 Prompt 片段压缩

对 `prompt_fragments`：

- 去掉重复形容词。
- 合并近义风格词。
- 删除只对单张图有效的物件堆叠。
- 保留对生成稳定有帮助的媒介、光照、构图和材质约束。

### 7.3 Evidence 分离

不稳定信息不要进入核心对象，进入 evidence：

- 单张图特有物件
- 一次性角色姿态
- 临时活动元素
- 用户当次偏好
- 低置信模型判断

核心对象只吸收跨样本稳定出现的信息。

## 8. 数据结构建议

### 8.1 公共字段

为 assets、recipes、visual systems 逐步引入：

```json
{
  "parent_id": null,
  "merged_into_id": null,
  "lineage": {
    "root_id": "xxx",
    "depth": 0,
    "variant_count": 0
  },
  "evolution": {
    "stability": "draft|stable|deprecated|merged",
    "last_action": "create_new|attach_evidence|inherit_variant|merge_existing",
    "last_reason": "..."
  }
}
```

实际表字段可以按实体拆分为：

- `parent_asset_id`
- `merged_into_asset_id`
- `parent_recipe_id`
- `merged_into_recipe_id`
- `parent_system_id`
- `merged_into_system_id`

### 8.2 Revision 表

建议新增：

- `visual_asset_revisions`
- `recipe_revisions`
- `visual_system_revisions`

字段：

```text
id
entity_id
action
source_candidate_id
source_generation_id
target_entity_id
scores_json
before_json
after_json
diff_json
reason
created_at
```

### 8.3 Evidence 表

已有 asset evidence 可扩展到：

- `visual_asset_evidence`
- `recipe_evidence`
- `visual_system_evidence`

字段：

```text
id
entity_id
evidence_type
source_candidate_id
source_generation_id
source_reference_id
payload_json
created_at
```

### 8.4 Merge Preview

合并前先生成 preview：

```json
{
  "action": "merge_existing",
  "canonical_id": "visual_system_a",
  "duplicate_id": "visual_system_b",
  "proposed_after": {},
  "diff": {},
  "migration_plan": {
    "assets": [],
    "recipes": [],
    "evidence": [],
    "source_refs": []
  },
  "risk_notes": [],
  "requires_user_confirmation": true
}
```

## 9. 用户确认策略

建议默认确认规则：

| 动作 | 是否可自动执行 | 原因 |
| --- | --- | --- |
| 归属 evidence | 可以自动或批量确认 | 不改变核心抽象 |
| 新增 asset | 可批量确认，但需展示高相似项 | 低风险但数量易膨胀 |
| 新增 recipe/system | 需要用户确认 | 会增加长期知识对象 |
| 继承 variant | 需要用户确认 | 会增加层级结构 |
| 合并 | 必须用户确认 | 不可逆风险高 |

所有自动动作都必须记录 revision 或 evidence。

## 10. 分阶段落地

### Phase A: 召回与建议统一

- asset、recipe、visual system 的候选入库都强制走 storage hybrid/embedding 召回。
- 模型/skill 不允许预填召回结果作为最终依据。
- 候选列表展示统一显示 `新增 / 归属 / 继承 / 合并 / 待判断`。
- 每条建议展示 similarity、novelty、conflict、target 和 reason。

### Phase B: Evidence 与归属

- 补齐 recipe/system evidence 表。
- `归属` 动作只写 evidence 和关系，不改核心字段。
- 高相似 asset 默认转为 evidence，降低 asset 爆炸。

### Phase C: 继承/Variant

- 为 asset、recipe、system 增加 parent 字段。
- 实现 `inherit_variant` 确认动作。
- prompt compose 支持父对象 + delta 组合。
- 列表展示 lineage。

### Phase D: Merge Preview

- 实现 merge preview。
- 智能体生成 `abstract(A, B)` 提案。
- 用户确认后写 canonical、迁移关系、标记 duplicate。
- 所有 merge 写 revision。

### Phase E: 治理界面

- 展示相似簇。
- 展示 pending merge/variant 建议。
- 支持批量归属和逐条确认。
- 支持按类型查看 asset 膨胀风险。

## 11. 当前实现落地状态

已落地能力：

- visual asset candidate 已基于 hybrid recall 生成 `similar_candidates`。
- recipe/system candidate 已基于 hybrid recall 生成去重建议。
- recipe/system candidate 入库时已经改为不被外部 `related_existing_*` 阻断。
- asset candidate 已确保 `similar_candidates` 由 storage 重算，不被外部 payload 固定。
- candidate payload 已统一写入 `evolution_action` 与 `evolution_suggestion`。
- asset、recipe、visual system 均支持 `attach_evidence`、`inherit_variant`、`create_new` 语义。
- asset、recipe、visual system 均支持 evidence 与 revision 查询。
- asset、recipe、visual system 均支持 `merge-preview` 与重新抽象式 merge。
- `related_existing_*` 可保留为 storage 生成的召回证据，但不应作为模型输入协议或用户手写依据。

仍建议继续优化：

- novelty/conflict 当前先使用 deterministic heuristic，后续可接入智能体二次判断生成更强解释。
- merge preview 当前做结构化重抽象与压缩，后续可增加模型辅助的 canonical definition 草案。
- UI 层需要展示 `evolution_action`、scores、preview diff 和人工确认入口。

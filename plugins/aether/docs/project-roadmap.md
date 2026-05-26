# Aether 项目推进建议

## 1. 项目定位

Aether 当前最适合的定位不是单纯的 Prompt 工具，也不建议一开始就直接定义成完整的 Style OS。更稳妥的阶段性定位是：

> 面向 AI 图像生成的个人风格记忆系统和 Prompt 精修引擎。

它解决的核心问题是：

- 用户看到一张或多张好看的图片后，很难稳定复用其中的共同风格。
- 用户有一个模糊想法后，很难把它转成高质量、风格一致的生图提示词。
- 用户生成图片后，好的结果没有被沉淀成可复用资产。

Aether 的核心闭环应当是：

```text
参考图片和可选原始生图提示词
-> 风格解析
-> 风格去重
-> 沉淀为风格卡
-> 用户输入模糊 prompt
-> 选择或推荐风格
-> 生成精修 prompt
-> 调用配置的图片生成 Skill
-> 保存结果和反馈
-> 反哺风格库
```

因此，一期重点不是做“大而全的审美系统”，而是先把“风格资产可沉淀、可检索、可复用”这个闭环跑通。

## 2. 核心使用场景

### 2.1 沉淀

用户看到一张或多张好看的图片，连同可选的原始生图提示词一起发送给 Aether。

系统需要完成：

- 识别图片中的视觉风格。
- 提取画风、色彩、光影、构图、情绪、镜头语言、材质、时代感等信息。
- 判断该风格是否已经存在。
- 如果已有相似风格，提示归入已有风格或作为分支保存。
- 如果没有相似风格，自动创建新的风格卡。
- 为该风格生成可复用的 prompt 模版。

目标是把“好看的图”变成“可复用的风格资产”。

### 2.2 分析

用户提供一段模糊提示词，例如：

```text
一个孤独的女孩走在未来城市里
```

系统需要完成：

- 解析用户意图。
- 识别主体、场景、情绪、时代、镜头、氛围。
- 推荐适合的风格。
- 将用户原始想法和目标风格结合，生成更完整、更稳定的生图 prompt。
- 输出多个方向的变体，例如电影感、插画感、写实感、梦境感。

目标是把“模糊想法”变成“可执行的高质量生图提示词”。

### 2.3 生成

用户确认风格和 prompt 后，系统调用配置好的 Codex 图片生成 Skill 生成图片。

系统需要完成：

- 根据目标图片生成 Skill 调整 prompt 格式。
- 调用图片生成 Skill。
- 保存生成记录。
- 支持用户反馈生成结果是否符合预期。
- 将优秀结果加入风格参考或生成新的风格分支。

目标是把“风格资产”和“用户想法”落到实际图片产出中。

## 3. 一期目标

一期目标是建立最小可用的 Style Memory 闭环。

### 3.1 一期必须完成的能力

1. 图片风格解析
2. 风格结构化存储
3. 风格相似判断
4. 新风格模版沉淀
5. 基于风格的 Prompt 精修
6. 图片生成 Skill 调用
7. 生成记录保存
8. 用户反馈记录

### 3.2 一期暂不追求的能力

以下能力有价值，但不建议放入一期主线：

- 复杂风格混合
- 风格演化树
- 审美评分体系
- 跨图片生成 Skill Prompt 适配
- 大规模风格 RAG
- 风格人格化
- AI 艺术知识图谱

原因是它们都会依赖稳定的风格卡、风格向量和生成反馈数据。一期应先积累这些底层资产。

## 4. 一期功能清单

### 4.1 风格解析

输入：

- 一张或多张参考图片
- 每张参考图可选对应的原始生图提示词
- 可选的整体用户备注，例如“我喜欢这个色调”或“我想保留这种镜头感”

处理：

- 使用 Codex 当前模型逐张分析图片。
- 如果输入多张图片，先提取每张图片的独立风格特征，再归纳共同风格。
- 如果图片附带原始生图提示词，将其作为风格来源线索，但不直接当作最终风格定义。
- 提取结构化风格维度。
- 生成风格摘要。
- 生成风格关键词。
- 生成可复用 prompt 模版。
- 生成 negative prompt。

输出：

- 结构化风格描述
- 多图输入时的共同风格描述
- 每张参考图的差异点
- 风格名称建议
- 风格标签
- Prompt 模版
- Negative prompt
- 相似风格判断结果

建议解析维度：

```json
{
  "art_style": "cinematic cyberpunk illustration",
  "color_palette": ["deep blue", "magenta neon", "muted amber"],
  "lighting": "low-key lighting, neon rim light, soft bloom",
  "composition": "wide shot, large negative space, centered subject",
  "mood": ["lonely", "nostalgic", "distant"],
  "camera_language": "cinematic wide angle, shallow depth of field",
  "materials": ["wet asphalt", "glass reflection", "metal panels"],
  "era": "retro futuristic",
  "line_and_shape": "clean silhouettes, soft edges, elongated vertical shapes",
  "detail_density": "medium-high detail with restrained background clutter",
  "post_processing": "soft bloom, subtle film grain, low contrast shadows",
  "visual_keywords": ["neon alley", "rain", "urban solitude"],
  "negative_traits": ["overly saturated colors", "crowded scenes", "flat lighting"]
}
```

### 4.2 风格定义边界

风格不是图片内容的全文描述，而是一组可以迁移到其他主题上的视觉规则。

风格应包含：

- 媒介和画法：摄影、插画、动画、像素、3D、拼贴、水彩、油画等。
- 色彩语言：主色、辅助色、饱和度、对比度、冷暖关系。
- 光影语言：高调、低调、逆光、霓虹、柔光、硬光、体积光等。
- 构图规则：居中、留白、对称、广角、近景、俯视、低机位等。
- 镜头语言：焦段感、景深、运动感、电影感、纪实感等。
- 情绪气质：孤独、温暖、疏离、梦境、压迫、克制等。
- 材质和纹理：胶片颗粒、纸张纹理、金属、玻璃、湿润反光等。
- 线条和形状：硬边、软边、几何、流线、粗线条、细线条等。
- 细节密度：极简、复杂、背景信息量、主体细节层级。
- 时代和文化感：复古未来、千禧、昭和、维多利亚、赛博朋克等。
- 后期效果：bloom、film grain、vignette、low contrast、HDR 等。
- 禁止特征：该风格应该避免的视觉倾向。
- Prompt 模版：如何把上述风格稳定表达成可复用提示词。

风格不应包含，或不应作为主要判断依据：

- 单次图片里的具体人物身份。
- 单次图片里的具体物体数量。
- 某个偶然出现的道具。
- 一次性叙事剧情。
- 用户只是临时要求的尺寸、比例、分辨率。
- 与视觉风格无关的业务描述。

例外情况是：如果某类主体反复出现并成为风格的一部分，可以作为弱特征保存。例如“孤独人物背影”“巨大建筑压迫感”“小人物与大场景比例”可以属于构图和情绪风格，但“一个红衣女孩”通常只是内容，不是风格。

### 4.3 风格去重与沉淀

系统需要判断新图片解析出的风格是否已经存在。

一期不建议强依赖向量数据库或单一 embedding 分数。更稳的方式是使用三层判断：

1. 结构化字段归一化
2. 字段权重相似度
3. Codex 语义判断

相似度结果建议分为三类：

- `existing_style`: 明显属于已有风格
- `style_branch`: 与已有风格相似，但有独特方向，适合作为分支
- `new_style`: 与现有风格差异明显，适合创建新风格

字段权重建议放在 `config.json` 中维护：

```json
{
  "artStyle": 0.18,
  "colorPalette": 0.14,
  "lighting": 0.14,
  "mood": 0.12,
  "composition": 0.1,
  "cameraLanguage": 0.1,
  "materials": 0.08,
  "era": 0.06,
  "visualKeywords": 0.05,
  "negativePrompt": 0.03
}
```

推荐判断流程：

```text
新图片
-> Codex 解析为 style_profile
-> 将字段归一化为稳定标签和短描述
-> 与已有风格逐个比较
-> 计算字段权重分
-> 让 Codex 输出语义相似判断和差异解释
-> 结合配置阈值给出 existing_style / style_branch / new_style
-> 用户确认最终动作
```

Codex 语义判断建议输出固定结构：

```json
{
  "similarity_score": 0.81,
  "decision": "style_branch",
  "matched_dimensions": ["lighting", "mood", "camera_language"],
  "different_dimensions": ["color_palette", "materials"],
  "reason": "Both styles rely on cinematic low-key lighting and lonely urban mood, but the new image has warmer colors and softer material texture."
}
```

保存逻辑建议：

```text
相似度 >= 0.86: 归入已有风格
0.72 <= 相似度 < 0.86: 建议作为风格分支
相似度 < 0.72: 建议创建新风格
```

阈值不要一开始写死为最终标准，应当从 `config.json` 读取，并允许后续根据实际效果调整。

需要注意：相似度只是辅助判断，不能直接替用户做不可逆合并。尤其是相似分数落在分支区间时，应默认让用户确认。

### 4.4 风格卡

风格卡是一期最重要的数据资产。

建议字段：

```json
{
  "id": "style_neon_melancholy",
  "name": "Neon Melancholy",
  "summary": "A lonely cinematic cyberpunk style with neon reflections, rain-soaked streets, and restrained emotional distance.",
  "tags": ["cyberpunk", "neon", "lonely", "cinematic", "rain"],
  "source_references": [
    {
      "image_path": "",
      "source_prompt": "",
      "user_note": "",
      "role": "positive_reference"
    }
  ],
  "style_profile": {
    "art_style": "",
    "color_palette": [],
    "lighting": "",
    "composition": "",
    "mood": [],
    "camera_language": "",
    "materials": [],
    "era": "",
    "visual_keywords": []
  },
  "prompt_template": "",
  "negative_prompt": "",
  "embedding": [],
  "parent_style_id": null,
  "created_at": "",
  "updated_at": ""
}
```

### 4.5 Prompt 精修

输入：

- 用户原始 prompt
- 用户选择的风格卡
- 可选目标图片生成 Skill
- 可选约束，例如比例、主体数量、是否写实、是否保留原始构图

处理：

- 使用 Codex 当前模型分析和精修 prompt。
- 分析用户原始 prompt 的主体、场景、动作、情绪和画面目标。
- 从风格卡中读取风格描述、prompt 模版、negative prompt。
- 结合用户目标生成最终 prompt。
- 根据目标图片生成 Skill 进行轻量适配。

输出：

- 精修后的主 prompt
- negative prompt
- 风格应用说明
- 可选 prompt 变体

输出示例：

```json
{
  "refined_prompt": "A solitary young woman walking through a rain-soaked futuristic city at night, surrounded by magenta and cyan neon reflections, cinematic wide shot, large negative space, low-key lighting, soft bloom, wet asphalt, glass reflections, restrained melancholic mood, retro futuristic atmosphere.",
  "negative_prompt": "overly saturated colors, crowded composition, flat lighting, cartoonish proportions, messy background, low detail",
  "style_notes": "The prompt emphasizes loneliness, neon reflections, rain, wide cinematic framing, and restrained cyberpunk atmosphere.",
  "variants": [
    {
      "name": "more cinematic",
      "prompt": "..."
    },
    {
      "name": "more illustration-like",
      "prompt": "..."
    }
  ]
}
```

### 4.6 图片生成

一期图片生成不需要做复杂接口配置，重点是打通最小链路。项目本身不需要维护独立的 LLM 或图片生成接口层，生成动作可以通过可配置的 Codex Skill 完成。

必须能力：

- 使用精修 prompt 调用指定图片生成 Skill。
- 保存原始 prompt、精修 prompt、风格 id、Skill 名称、Skill 参数和输出图片。
- 支持用户标记结果。

建议保存的生成记录：

```json
{
  "id": "generation_xxx",
  "source_prompt": "",
  "refined_prompt": "",
  "style_id": "",
  "generation_skill": "imagegen",
  "skill_params": {
    "aspect_ratio": "1:1",
    "quality": "standard"
  },
  "skill_result_meta": {},
  "outputs": [],
  "feedback": {
    "liked": null,
    "notes": ""
  },
  "created_at": ""
}
```

### 4.7 Codex 插件与 Skills 分工

Aether 的产品形态建议做成 Codex 插件，而不是只做一组松散的 Skills。插件负责统一安装入口、暴露 Skills、约定配置读取路径，并在后续需要时承载本地命令或 MCP 服务。

Codex Skills 适合作为插件内的交互入口、工作流规范和图片生成能力的配置层。Aether 自身重点沉淀风格资产、prompt 配方、生成记录和反馈，不需要单独维护视觉理解模型、文本模型或图片生成模型的接口配置。

推荐插件结构：

```text
.codex-plugin/
  plugin.json

skills/
  style-capture/
  prompt-refine/
  image-generate/

config.json
  项目级配置，不随插件安装覆盖
```

插件和项目配置的关系：

- 插件负责让 Codex 识别和加载 Aether 能力。
- `config.json` 负责当前项目的路径、阈值、Skill 映射和生成参数。
- 插件安装目录不保存项目数据。
- 插件升级不覆盖项目级 `config.json`。

建议拆成三个 skill：

#### style-capture

用途：

- 用户发送一张或多张图片时，解析并沉淀风格。

职责：

- 读取图片及其可选原始生图提示词。
- 调用项目内风格解析能力。
- 展示解析结果。
- 询问或判断是否创建风格卡。
- 将结果写入风格库。

#### prompt-refine

用途：

- 用户输入模糊提示词时，生成更具体的生图 prompt。

职责：

- 分析用户意图。
- 检索或使用指定风格。
- 使用 Codex 当前模型执行 prompt 精修。
- 调用项目内数据读写能力保存精修结果。
- 输出最终 prompt 和变体。

#### image-generate

用途：

- 用户确认 prompt 后生成图片。

职责：

- 接收最终 prompt。
- 根据项目配置选择图片生成 Skill。
- 调用对应 Skill 完成生成。
- 保存生成记录。
- 引导用户反馈。

### 4.8 一期功能细化

一期进入实现前，建议把以下 8 个点明确下来。它们不是额外扩展功能，而是保证一期闭环稳定的实现边界。

#### 4.8.1 三条主流程的输入输出契约

沉淀流程：

```json
{
  "input": {
    "references": [
      {
        "image_path": "",
        "source_prompt": "",
        "user_note": ""
      }
    ],
    "reference_mode": "single-style",
    "user_note": ""
  },
  "output": {
    "per_reference_profiles": [],
    "consensus_style_profile": {},
    "style_profile": {},
    "similarity_results": [],
    "style_card_draft": {}
  }
}
```

分析流程：

```json
{
  "input": {
    "source_prompt": "",
    "style_id": "",
    "target_generation_skill": "",
    "constraints": {}
  },
  "output": {
    "intent_analysis": {},
    "refined_prompt": "",
    "negative_prompt": "",
    "variants": []
  }
}
```

生成流程：

```json
{
  "input": {
    "refined_prompt": "",
    "negative_prompt": "",
    "generation_skill": "",
    "skill_params": {}
  },
  "output": {
    "generation_run": {},
    "asset_paths": [],
    "skill_result_meta": {}
  }
}
```

#### 4.8.2 用户确认点

以下动作不建议自动执行，应由用户确认：

- 合并到已有风格。
- 创建已有风格的分支。
- 创建全新风格。
- 覆盖已有风格卡。
- 将生成结果反哺到风格库。
- 切换图片生成 Skill。
- 使用用户未明确要求的强风格改写。

如果 Codex 判断有较高置信度，也应输出建议和理由，而不是直接做不可逆修改。

#### 4.8.3 风格卡状态

风格卡建议至少支持以下状态：

```text
draft     解析后生成但尚未确认
active    用户确认后可复用
archived  不再主动推荐，但保留历史
merged    已合并到其他风格
```

一期最低要求：

- 新解析结果先进入 `draft`。
- 用户确认后进入 `active`。
- 被合并的风格卡保留记录，不直接删除。

#### 4.8.4 生成记录状态

生成记录建议支持以下状态：

```text
created
prompt_refined
generation_requested
generated
failed
liked
rejected
```

一期最低要求：

- 可以区分生成成功和失败。
- 可以保存失败原因。
- 可以记录用户喜欢或不喜欢。
- 生成记录必须关联 `style_id`、`refined_prompt` 和 `generation_skill`。

#### 4.8.5 Prompt 精修保真规则

Prompt 精修默认使用 Codex 当前模型，但需要遵守保真规则。

必须保留：

- 用户指定的主体。
- 用户指定的场景。
- 用户指定的动作。
- 用户指定的情绪。
- 用户明确给出的限制条件。

允许增强：

- 光影。
- 构图。
- 镜头语言。
- 材质。
- 色彩。
- 氛围。
- 细节密度。

不应擅自替换：

- 主体身份。
- 核心场景。
- 用户明确想要的画风。
- 用户明确不想要的元素。

如果必须补充假设，输出中应包含 `assumptions` 字段：

```json
{
  "assumptions": [
    "The prompt does not specify time of day, so night lighting is inferred from the selected neon style."
  ]
}
```

#### 4.8.6 相似判断解释字段

相似判断不应只保存一个分数。每次判断建议保存：

```json
{
  "candidate_style_id": "",
  "similarity_score": 0.81,
  "decision": "style_branch",
  "matched_dimensions": ["lighting", "mood"],
  "different_dimensions": ["color_palette", "materials"],
  "reason": ""
}
```

这样后续可以回看为什么归并、为什么分支，也方便调整相似度权重和阈值。

#### 4.8.7 本地目录结构

一期建议约定 `.aether/` 作为本地运行数据目录：

```text
.aether/
  aether.sqlite
  assets/
    references/
    generated/
  runs/
  cache/
```

目录含义：

- `aether.sqlite`: 风格卡、生成记录、反馈记录。
- `assets/references`: 用户输入的参考图。
- `assets/generated`: 图片生成结果。
- `runs`: 单次沉淀、分析、生成过程的中间记录。
- `cache`: 可丢弃缓存。

这些路径由根目录 `config.json` 配置，所有相对路径都基于 `config.json` 所在目录解析。

#### 4.8.8 一期验收样例

一期建议准备固定样例集，而不是只靠临时手测。

建议最小样例：

- 2 张明显同风格图片，用来验证 `existing_style`。
- 2 张相似但有差异的图片，用来验证 `style_branch`。
- 2 张完全不同风格图片，用来验证 `new_style`。
- 3 条模糊 prompt，用来验证 Prompt 精修。
- 1 次完整生成链路，用来验证生成记录和资产保存。

验收时应检查：

- 风格解析是否结构化。
- 相似判断是否有解释。
- 用户确认点是否存在。
- Prompt 精修是否保留用户原意。
- 生成结果是否关联到风格卡。
- 失败记录是否可追踪。

## 5. 推荐技术架构

### 5.1 模块划分

建议按以下模块拆分：

```text
styles/
  风格卡存储、风格解析、风格去重、风格检索

prompts/
  用户意图分析、prompt 精修、prompt 模版渲染

generations/
  Skill 调用记录、生成记录、反馈记录

skills/
  Codex Skills 工作流入口

.codex-plugin/
  Codex 插件安装清单和插件元信息

config.json
  项目配置、Skill 映射、默认路径、后端启动参数
```

### 5.2 数据层

一期可以从简单持久化开始：

- 本地 JSON 文件
- SQLite
- PostgreSQL

如果项目还处在早期，建议优先使用 SQLite。它足够支撑本地风格库、生成记录、反馈记录，也方便后续迁移。

风格 embedding 可以先以 JSON 数组保存，后续再迁移到向量数据库或 pgvector。

### 5.3 Codex 能力与 Skill 编排层

Aether 不需要单独抽象 LLM 接口层。推理、结构化分析和视觉理解默认使用 Codex 当前可用的模型能力完成，项目侧只需要定义稳定的输入输出结构和数据落点。

图片生成也不需要在项目里配置独立的 LLM 接口。建议通过 `config.json` 配置可用的图片生成 Skill、默认 Skill 和默认生成参数。

这样用户可以通过配置切换不同图片生成 Skill，而 Aether 的核心数据结构不需要感知具体模型、接口密钥或调用细节。

### 5.4 配置文件与 Codex 读取路径

项目配置统一放在根目录 `config.json`。配置内容包括：

- 产品形态，默认 `codex-plugin`。
- 数据库和本地资产目录。
- 多参考图沉淀策略。
- 风格相似度阈值和字段权重。
- Prompt 精修默认参数。
- Prompt 精修执行方，默认使用 Codex 当前模型。
- 默认图片生成 Skill。
- 可用图片生成 Skill 列表。
- Codex Skill 名称映射。
- 后端按需启动参数。

建议约定所有相对路径都基于 `config.json` 所在目录解析，而不是基于 Skill 安装目录解析。

这是因为 Codex Skills 安装后通常位于：

```text
~/.codex/skills/<skill-name>
```

但 Aether 的项目数据属于当前工作区，不属于 Skill 安装目录。因此 Skill 运行时应该从工作区读取项目配置，而不是从 `~/.codex/skills` 下读取配置。

如果 Aether 以 Codex 插件形式安装，插件清单只负责声明插件能力和 Skills。项目级配置仍然从当前工作区读取，避免插件升级时覆盖用户项目数据。

建议配置查找顺序：

1. 优先读取 `~/.config/aether/config.json`，用于本机 Codex 插件级配置。
2. 否则从当前工作目录开始向上查找 `config.json`。
3. 再读取当前目录下的 `.aether/config.json`。

推荐原则：

- 项目级配置保存在项目根目录 `config.json`。
- Codex Skill 不内置项目配置。
- Codex Skill 可以内置默认读取规则。
- Skill 安装、升级或软链更新不应覆盖项目配置。
- 图片生成 Skill 的具体密钥和外部接口细节仍由对应 Skill 自己管理。

### 5.5 后端职责

在这个架构里，后端不应承担模型网关的角色。它不负责维护 LLM key、视觉模型接口或图片生成接口。后端的核心价值是做状态、资产和确定性业务逻辑管理。

后端建议承担以下职责：

- 风格卡的创建、读取、更新、删除。
- 参考图片和生成图片的本地资产管理。
- 风格相似度结果、风格分支和版本记录管理。
- Prompt 配方、精修记录和生成记录保存。
- 用户反馈保存。
- Skill 配置读取，例如默认图片生成 Skill。
- 为 Codex Skills、CLI 或未来 UI 提供稳定的数据访问入口。
- 执行不依赖模型推理的确定性逻辑，例如字段校验、标签检索、阈值判断、模版渲染、记录归档。

后端不建议承担以下职责：

- 直接调用视觉理解模型。
- 直接调用文本 LLM。
- 直接维护图片生成模型接口。
- 在没有用户动作时自动做复杂推理。

也就是说，Codex 负责理解、分析、推理和调用 Skill；Aether 后端负责把这些结果可靠地保存、检索、复用和串联起来。

### 5.6 后端开启方式

一期不建议一开始就要求用户长期启动一个常驻后端。更推荐分阶段处理。

#### 阶段一：无常驻服务，优先 CLI/本地库

适合一期最小闭环。

Codex Skills 直接调用项目内命令或脚本完成数据读写，例如：

```text
aether style create
aether style list
aether prompt refine
aether generation record
```

优势：

- 简单。
- 依赖少。
- 不需要端口。
- 适合 Codex 驱动的交互。

这一阶段的“后端”本质上是本地数据层和业务函数，不需要单独启动。

#### 阶段二：按需启动本地服务

当需要图形界面、风格库浏览、搜索、生成历史页面时，再提供本地服务。

建议命令形态：

```text
aether serve --db .aether/aether.sqlite --assets .aether/assets --port 3850
```

或在具体技术栈里映射成：

```text
npm run dev
```

本地服务只负责：

- 提供 UI 数据接口。
- 展示风格库。
- 展示生成记录。
- 接收 Codex Skills 写入后的刷新。
- 管理本地图片资产。

#### 阶段三：可选常驻服务

如果后续发展成桌面应用、团队风格库或多人协作，再考虑常驻服务。

这一阶段可以加入：

- 用户账户。
- 多项目空间。
- 后台任务队列。
- 向量索引常驻加载。
- 团队共享风格库。

一期不建议进入这个阶段。

推荐的一期策略是：

```text
默认不启动后端
-> Codex Skills 调用本地 CLI/库完成读写
-> 需要浏览风格库或生成历史时再按需启动本地服务
```

## 6. 一期里程碑

### Milestone 0: 项目骨架

目标：

- 明确数据结构。
- 建立风格卡、生成记录、Skill 配置结构。
- 建立基础 CLI 或最小交互入口。
- 后端先以本地数据层和业务函数形式存在，不要求常驻服务。

验收标准：

- 可以创建、读取、更新风格卡。
- 可以保存生成记录。
- 可以读取默认图片生成 Skill 配置。
- Codex Skills 可以通过本地命令或库读写 Aether 数据。

### Milestone 1: 风格解析

目标：

- 用户输入图片后，系统可以输出结构化风格解析。

验收标准：

- 输出包含画风、色彩、光影、构图、情绪、镜头语言、材质、关键词。
- 可以自动生成风格名称和摘要。
- 可以生成初版 prompt 模版和 negative prompt。

### Milestone 2: 风格沉淀和去重

目标：

- 图片解析结果可以沉淀为风格卡。
- 新风格可以和已有风格做相似判断。

验收标准：

- 相似风格可以被召回。
- 系统能给出已有风格、风格分支、新风格三类判断。
- 用户可以确认保存结果。

### Milestone 3: Prompt 精修

目标：

- 用户输入模糊 prompt，选择风格后，系统输出精修 prompt。

验收标准：

- 精修 prompt 保留用户主体意图。
- 风格描述被稳定融合到 prompt 中。
- 输出 negative prompt。
- 至少支持 2 个变体。

### Milestone 4: 图片生成

目标：

- 使用精修 prompt 调用配置的图片生成 Skill。

验收标准：

- 可以生成图片。
- 可以保存生成记录。
- 可以记录用户反馈。
- 生成结果能关联到使用的风格卡。

### Milestone 5: Codex 插件接入

目标：

- 通过 Codex 插件承接沉淀、分析、生成三类交互。

验收标准：

- 插件清单可以声明 Aether 的能力入口。
- `style-capture` 可以处理图片风格沉淀。
- `prompt-refine` 可以处理模糊 prompt 精修。
- `image-generate` 可以处理图片生成和记录保存。
- 插件安装目录和项目级 `config.json` 解耦。

## 7. 后续演进方向

### 7.1 Phase 2: Style Engine

Phase 2 的目标是让风格资产变得可计算、可检索、可组合。

重点能力：

1. 风格向量化
2. 风格相似搜索
3. 风格推荐
4. 风格分支管理
5. 风格圣经
6. 风格混合

#### 风格向量化

把风格转成可计算的向量和维度评分。

示例：

```json
{
  "loneliness": 0.82,
  "neon": 0.71,
  "cinematic": 0.91,
  "warmth": 0.22,
  "surreal": 0.68
}
```

用途：

- 相似风格检索
- 风格推荐
- 风格聚类
- 风格地图
- 风格混合

#### 风格圣经

自动为每个成熟风格生成一份设计系统文档。

内容包括：

- 色彩规则
- 光影规则
- 构图规则
- 情绪规则
- 镜头语言
- 材质偏好
- 推荐主体
- 禁止元素
- 适配模型
- 示例 prompt

风格圣经可以把项目从 prompt 工具提升为视觉设计系统。

#### 风格混合

允许用户指定多个风格及权重。

示例：

```text
70% Neon Melancholy
30% Retro Futurism
```

输出：

- 融合后的 prompt
- 风格权重说明
- 冲突项处理说明
- 新风格候选卡

一期不建议实现复杂混合，但可以在数据结构中预留 `parent_style_id` 和 `derived_from` 字段。

### 7.2 Phase 3: Visual Intelligence

Phase 3 的目标是从风格复用升级为审美理解和风格推理。

重点能力：

1. 审美评分
2. 反向 Prompt 学习
3. 风格一致性生成
4. 跨图片生成 Skill Prompt 适配
5. 风格人格化
6. 风格知识图谱

#### 审美评分

对图片进行多维评分：

- Aesthetic Score
- Mood Consistency
- Composition Strength
- Style Consistency
- Prompt Alignment

注意：审美评分很容易变成主观打分，一开始不宜做成强判断，更适合做成辅助建议。

#### 反向 Prompt 学习

根据用户喜欢或不喜欢的生成结果，分析哪些关键词有效，哪些描述无效。

长期目标：

- 识别高贡献风格词。
- 降低无效 prompt 词。
- 形成 prompt 强度模型。
- 自动优化风格卡中的 prompt 模版。

#### 风格一致性生成

围绕同一个风格或角色保持稳定输出。

能力包括：

- 固定色彩语言
- 固定镜头语言
- 固定材质描述
- 固定角色或主体描述
- 固定 negative prompt

这是生图工作流中的高价值需求，但依赖足够稳定的风格卡和生成反馈。

#### 跨图片生成 Skill Prompt 适配

不同图片生成 Skill 背后可能调用不同的生成系统，因此会有不同的 prompt 偏好。后续可以支持：

```text
Generic Prompt
-> imagegen Skill Prompt
-> rightcodes-imagegen Skill Prompt
-> custom-generation Skill Prompt
```

该能力适合在用户实际使用多个生成 Skill 后再做，不建议一期先投入过多。

## 8. 风险与边界

### 8.1 风格去重不是绝对判断

风格相似度是辅助判断，不应替用户做强制合并。一期应允许用户确认：

- 合并到已有风格
- 创建风格分支
- 创建全新风格

### 8.2 Prompt 精修不能覆盖用户原始意图

系统应该增强用户的想法，而不是把用户想法替换成系统偏好的风格描述。

需要保留：

- 主体
- 场景
- 动作
- 情绪
- 用户明确表达的限制

### 8.3 不要过早绑定单一图片生成 Skill

图片生成链路变化很快。项目不应把 prompt 结构、参数和存储格式绑定到某一个生成 Skill。更合理的做法是只记录 Skill 名称、输入参数、输出结果和返回元信息。具体生成模型、接口密钥和调用细节由对应的 Codex Skill 管理。

### 8.4 风格命名需要谨慎

如果引用在世艺术家、商业 IP 或明确受版权保护的风格，需要避免直接把它们固化为默认模板名称。可以用描述性风格名代替，例如：

- Neon Melancholy
- Soft Retro Futurism
- Dreamlike Pastel Cinema

## 9. 推荐 Backlog

### P0

- 定义 Style Card 数据结构
- 定义 Generation Run 数据结构
- 图片风格解析
- 风格卡保存
- 风格相似判断
- Prompt 精修
- 图片生成 Skill 最小链路

### P1

- 风格库检索
- Prompt 变体生成
- 用户反馈记录
- 风格分支
- Codex 插件接入
- 风格卡版本记录

### P2

- 风格圣经
- 风格向量维度评分
- 风格混合
- 风格推荐
- 跨图片生成 Skill Prompt 适配

### P3

- 审美评分
- 反向 Prompt 学习
- 风格一致性生成
- 风格演化树
- 风格人格化
- 风格知识图谱

## 10. 一期成功标准

一期成功不应以功能数量衡量，而应以闭环是否成立衡量。

建议用以下标准判断：

- 用户上传一张或多张参考图后，可以得到稳定的风格卡。
- 系统能判断新图和已有风格是否相似。
- 用户输入一句模糊 prompt 后，可以基于指定风格生成明显更好的 prompt。
- 精修 prompt 可以调用配置的图片生成 Skill 生成图片。
- 生成结果可以被保存并关联到风格卡。
- 用户可以通过反馈让风格资产继续演化。

如果以上闭环成立，Aether 就已经从普通 prompt 工具进入了 Style Memory 阶段。后续再扩展 Style Engine 和 Visual Intelligence 会更稳。

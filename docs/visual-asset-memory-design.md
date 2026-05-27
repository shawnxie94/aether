# Visual Asset Memory 改造方案

## 1. 目标

当前 Aether 的核心资产切换为 visual asset。它把一张图拆成多个可复用部分，方便后续自由组合，而不是把整张图沉淀成单一风格包。

目标是：

- 从图片中拆出可复用视觉素材。
- 将素材归入稳定分类。
- 对每个素材做去重、归并、变体或新增判断。
- 由用户确认不可逆或长期沉淀动作。
- 在 Prompt 精修时召回这些素材，组合成更稳定的生成方案。

核心变化：

```text
Reference Image
-> Visual Asset Memory
-> Prompt Composer
```

## 2. 总体模型

一张图片不应被强行拆满所有分类。系统应先判断图中哪些部分有长期复用价值，再归入对应模块。

推荐沉淀模块共 12 类：

1. 画风素材
2. 色彩素材
3. 光影素材
4. 构图素材
5. 镜头语言
6. 情绪素材
7. 场景素材
8. 材质与纹理
9. 角色原型
10. 道具与符号
11. 形状与线条
12. 负向约束

每个模块都应支持：

- 独立保存
- 相似判断
- 作为已有素材的变体
- 参与 Prompt 组合
- 被 review 和用户反馈反向修正

## 3. 12 类建议沉淀模块

### 3.1 画风素材 Style

用途：决定画面的整体视觉体系。

适合沉淀：

- 媒介类型
- 渲染方式
- 美术流派
- 笔触特征
- 整体视觉气质

示例：

```text
hand-drawn oil pastel anime
dreamy cinematic realism
surreal painterly illustration
minimal emotional illustration
nostalgic future
```

建议字段：

```json
{
  "name": "",
  "summary": "",
  "style_tags": [],
  "prompt_fragments": [],
  "negative_fragments": [],
  "reference_images": []
}
```

### 3.2 色彩素材 Color Palette

用途：形成稳定品牌感和情绪记忆点。

适合沉淀：

- 主色
- 辅助色
- 点缀色
- 冷暖关系
- 饱和度
- 对比度
- 禁用色

示例：

```text
blue gray + off-white + subtle warm yellow
black + cold white + small neon accent
lavender + cool blue + silver white
```

建议字段：

```json
{
  "palette_name": "",
  "dominant_colors": [],
  "secondary_colors": [],
  "accent_colors": [],
  "hex_values": [],
  "color_description": "",
  "avoid_colors": []
}
```

### 3.3 光影素材 Lighting

用途：决定质感、空间感和情绪强度。

适合沉淀：

- 光源类型
- 光源方向
- 明暗关系
- 阴影形态
- 反射
- 雾气
- 边缘光

示例：

```text
soft window light
neon rim light
rainy night reflections
golden hour backlight
volumetric fog diffusion
```

建议字段：

```json
{
  "lighting_name": "",
  "light_source": "",
  "direction": "",
  "contrast": "",
  "shadow_style": "",
  "compatible_moods": [],
  "compatible_scenes": [],
  "prompt_fragments": []
}
```

### 3.4 构图素材 Composition

用途：决定画面结构和高级感。

适合沉淀：

- 主体位置
- 留白
- 对称
- 引导线
- 透视关系
- 主体与环境比例
- 画面重心

示例：

```text
centered solitary subject
large negative space
small figure in vast environment
leading lines through corridor
symmetrical ritual composition
```

建议字段：

```json
{
  "composition_name": "",
  "framing": "",
  "subject_position": "",
  "space_usage": "",
  "scale_relationship": "",
  "recommended_aspect_ratios": [],
  "compatible_moods": []
}
```

### 3.5 镜头语言 Camera Language

用途：提升电影感、距离感和叙事视角。

适合沉淀：

- 焦段感
- 景别
- 机位
- 景深
- 运动感
- 摄影质感

示例：

```text
24mm wide angle
85mm portrait compression
low angle shot
top-down view
shallow depth of field
cinematic framing
```

建议字段：

```json
{
  "camera_name": "",
  "shot_type": "",
  "focal_length_feel": "",
  "camera_angle": "",
  "depth_of_field": "",
  "motion_language": "",
  "prompt_fragments": []
}
```

### 3.6 情绪素材 Mood

用途：决定用户为什么记住画面。

适合沉淀：

- 核心情绪
- 情绪强度
- 相近词
- 适配色彩
- 适配光影
- 适配场景

示例：

```text
lonely
nostalgic
dreamlike
digital melancholy
quiet warmth
emotional futurism
```

建议字段：

```json
{
  "mood_name": "",
  "keywords": [],
  "intensity": "",
  "compatible_colors": [],
  "compatible_lighting": [],
  "compatible_scenes": [],
  "prompt_fragments": []
}
```

### 3.7 场景素材 Scene

用途：支撑后续批量生产内容。

适合沉淀：

- 场景类型
- 空间结构
- 时间
- 天气
- 常见主体
- 适配情绪
- 适配镜头

示例：

```text
late-night convenience store
subway platform
rainy urban street
empty classroom
floating city
silent cinema
```

建议字段：

```json
{
  "scene_name": "",
  "scene_type": "",
  "spatial_features": [],
  "time_weather": "",
  "compatible_moods": [],
  "compatible_lighting": [],
  "compatible_characters": [],
  "prompt_fragments": []
}
```

### 3.8 材质与纹理 Texture / Material

用途：决定画面是否像艺术作品。

适合沉淀：

- 纸张
- 胶片颗粒
- 笔触
- 金属
- 玻璃
- 湿润反光
- CRT 扫描线
- 噪点
- 雾
- 粒子

示例：

```text
textured off-white paper
oil pastel pigment
film grain
wet asphalt reflection
CRT scanlines
soft bloom particles
```

建议字段：

```json
{
  "texture_name": "",
  "material_type": "",
  "surface_quality": "",
  "grain_or_noise": "",
  "prompt_fragments": [],
  "negative_fragments": []
}
```

### 3.9 角色原型 Character Archetype

用途：沉淀可长期复用的 IP 或角色方向。

适合沉淀：

- 发型
- 服装
- 色彩
- 年龄感
- 气质
- 固定动作
- 适配场景

示例：

```text
white-haired quiet girl
expressionless AI girl
future traveler in school uniform
red scarf boy
mechanical cat
```

注意：只有反复出现、能形成长期识别的角色才沉淀。一次性人物不要作为角色原型入库。

建议字段：

```json
{
  "character_name": "",
  "appearance": {},
  "outfit": {},
  "personality_mood": [],
  "signature_pose": [],
  "compatible_scenes": [],
  "prompt_fragments": []
}
```

### 3.10 道具与符号 Prop / Symbol

用途：沉淀系列化视觉记忆点。

适合沉淀：

- 高频道具
- 象征物
- 标志性物件
- 可重复出现的视觉符号

示例：

```text
giant moon
red scarf
vending machine
glowing headphones
floating train
mechanical cat
```

建议字段：

```json
{
  "symbol_name": "",
  "visual_form": "",
  "symbolic_meaning": "",
  "compatible_moods": [],
  "compatible_scenes": [],
  "prompt_fragments": []
}
```

### 3.11 形状与线条 Shape / Line

用途：保存轮廓、线条和形体语言。

适合沉淀：

- 粗线条
- 细线条
- 手绘抖线
- 几何形
- 圆润形
- 尖锐形
- 破碎边缘
- 细长垂直形

示例：

```text
rough sketchy dark outlines
soft rounded facial forms
elongated vertical silhouettes
geometric minimal shapes
broken edge strokes
```

建议字段：

```json
{
  "shape_line_name": "",
  "line_quality": "",
  "shape_language": "",
  "edge_style": "",
  "silhouette_rules": [],
  "prompt_fragments": []
}
```

### 3.12 负向约束 Negative Rules

用途：保护组合结果不偏离目标。

适合沉淀：

- 不要的画风
- 不要的材质
- 不要的构图
- 不要的色彩倾向
- 不要的生成缺陷

示例：

```text
avoid photorealism
avoid glossy 3D render
avoid clean vector art
avoid overly saturated colors
avoid crowded background
```

建议字段：

```json
{
  "negative_rule_name": "",
  "avoid_traits": [],
  "failure_modes": [],
  "negative_fragments": [],
  "applies_to": []
}
```

## 4. 统一素材结构

每个素材模块建议都有一套公共字段，方便检索、去重和组合。

```json
{
  "id": "",
  "type": "style | color_palette | lighting | composition | camera | mood | scene | texture | character | prop_symbol | shape_line | negative_rule",
  "name": "",
  "summary": "",
  "tags": [],
  "source_references": [],
  "prompt_fragments": [],
  "negative_fragments": [],
  "compatible_with": [],
  "avoid_with": [],
  "recommended_aspect_ratios": [],
  "status": "draft | active | archived | merged",
  "parent_asset_id": null,
  "merged_into_asset_id": null,
  "created_at": "",
  "updated_at": ""
}
```

类型特有字段放在：

```json
{
  "profile": {}
}
```

例如色彩素材：

```json
{
  "type": "color_palette",
  "name": "Digital Melancholy Blue Gray",
  "profile": {
    "dominant_colors": ["blue gray", "off-white"],
    "accent_colors": ["subtle warm yellow"],
    "hex_values": ["#586477", "#F2EDE2", "#D8B56A"]
  }
}
```

## 5. 图片沉淀流程改造

图片沉淀不再生成整包风格记录，而是生成候选素材模块。

推荐流程：

```text
输入图片
-> 视觉解析
-> 拆出候选素材模块
-> 判断每个模块所属类型
-> 和已有素材做相似判断
-> 输出归并建议
-> 用户确认
-> 入库
```

每个候选模块都应有一个决策：

```text
existing_asset    归入已有素材
asset_variant     作为已有素材变体
new_asset         新增素材
ignore            一次性内容，不沉淀
```

### 5.1 候选素材输出结构

```json
{
  "candidate_assets": [
    {
      "type": "lighting",
      "name": "Rainy Neon Reflection",
      "summary": "Neon light reflected on wet asphalt in a rainy night scene.",
      "prompt_fragments": [
        "rain-soaked asphalt reflections",
        "magenta and cyan neon rim light"
      ],
      "negative_fragments": [
        "flat lighting",
        "dry pavement"
      ],
      "source_reference_ids": [],
      "reuse_score": 0.86,
      "decision": "new_asset",
      "similar_candidates": []
    }
  ]
}
```

### 5.2 用户确认点

以下动作必须让用户确认：

- 新增素材
- 合并到已有素材
- 作为已有素材变体
- 将角色、道具或符号沉淀为长期资产
- 归档或废弃已有素材

系统可以推荐，但不要直接做不可逆归并。

## 6. Prompt 调优流程改造

Prompt 调优从“套用一个整体风格包”升级为“召回素材并组合”。

推荐流程：

```text
用户输入 prompt
-> 解析用户意图
-> 判断需要的素材类型
-> 从 12 类素材库召回候选
-> 检查冲突
-> 组合生成方案
-> 输出 refined prompt、negative prompt、参数建议
-> 用户确认
-> 生图
```

### 6.1 召回优先级

召回时按优先级处理：

1. 用户显式指定的素材
2. 与用户主体和场景最匹配的素材
3. 与目标风格强绑定的素材
4. 历史生成效果好的素材
5. 可选增强素材

不要为了堆细节召回过多素材。一次组合建议控制在：

- 1 个画风
- 1 个色彩方案
- 1 个主光影
- 1 个构图
- 1 个镜头语言
- 1 到 2 个情绪
- 0 到 1 个场景
- 0 到 2 个材质或符号
- 1 组负向约束

### 6.2 冲突检测

组合前需要检查冲突。

常见冲突：

- 极简构图 vs 高细节复杂背景
- 温暖治愈情绪 vs 冷峻压迫光影
- 写实摄影 vs 蜡笔手绘材质
- 大留白构图 vs 多主体群像
- 低饱和色彩 vs 高饱和霓虹

冲突处理方式：

```text
保留用户显式要求
-> 保留核心风格不变量
-> 降级可选增强素材
-> 输出 assumptions
```

### 6.3 组合输出结构

```json
{
  "source_prompt": "",
  "selected_assets": [
    {
      "type": "style",
      "asset_id": "",
      "reason": ""
    }
  ],
  "composition_plan": {
    "subject": "",
    "scene": "",
    "style": "",
    "color": "",
    "lighting": "",
    "composition": "",
    "camera": "",
    "mood": [],
    "texture": [],
    "negative_rules": []
  },
  "refined_prompt": "",
  "negative_prompt": "",
  "generation_params": {
    "aspectRatio": ""
  },
  "assumptions": [],
  "conflicts": []
}
```

## 7. 和现有能力的关系

### 7.1 Visual Asset 的角色

Visual asset 是 Aether 的规范沉淀单元。整体画风也作为 `type: "style"` 的 visual asset 存储，不再额外维护旧风格命令。

```text
visual asset
-> 独立保存参数定义
-> 引用参考图和证据
-> 参与 Prompt 组合
-> 接受 review 和用户反馈
```

常见组合关系直接写在素材字段里：

```json
{
  "id": "visual_asset_style-hand-drawn-oil-pastel-anime",
  "type": "style",
  "compatible_with": [
    "visual_asset_color-muted-warm-pastel",
    "visual_asset_texture-oil-pastel-grain"
  ],
  "avoid_with": [
    "visual_asset_lighting-hard-corporate-flash"
  ]
}
```

### 7.2 Visual Review 的角色

Visual review 可以反向修正素材质量。

例如：

- 某个材质素材经常导致偏差，降低推荐权重。
- 某个色彩素材在某个风格下通过率高，提高组合优先级。
- 某个 negative rule 能显著减少失败，自动加入默认组合。

### 7.3 资产归档的角色

参考图和生成图都可以作为素材模块的 evidence。

后续每个素材模块都应能引用：

- 原始参考图
- 生成成功图
- 生成失败图
- review 证据

## 8. 推荐实施顺序

### Step 1: 数据结构扩展

以 `visual_assets` 作为唯一长期沉淀结构。

最低字段：

- `id`
- `type`
- `name`
- `summary`
- `tags`
- `profile_json`
- `prompt_fragments_json`
- `negative_fragments_json`
- `source_references_json`
- `status`

当前实现还包含：

- `visual_asset_candidates`：保存图片解析出的候选素材、相似建议、用户决策和确认结果。
- `visual_asset_evidence`：保存参考图、生成图、review 和用户反馈证据。
- `prompt_records.selected_assets_json`：保存 Prompt Composer 选中的素材组合。
- `prompt_records.composition_plan_json` 与 `prompt_records.conflicts_json`：保存组合方案和冲突检查结果。
- `generation_runs.selected_assets_json`：把生成结果和所用素材关联起来。

### Step 2: 图片解析输出候选素材

让 `visual-asset-capture` 额外输出 `candidate_assets`。

当前实现支持全部 12 类素材：

- style
- color_palette
- lighting
- composition
- camera
- mood
- scene
- texture
- character
- prop_symbol
- shape_line
- negative_rule

候选批次保存命令：

```bash
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate-id>
```

### Step 3: 素材确认与入库

新增确认流程：

- 新增
- 归入已有
- 作为变体
- 忽略

确认命令：

```bash
aether visual-asset candidates decide <candidate-id> new_asset
aether visual-asset candidates decide <candidate-id> existing_asset --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> asset_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
```

### Step 4: Prompt 精修召回素材

让 `prompt-refine` 读取相关 visual assets，并输出 `selected_assets`。

组合命令：

```bash
aether prompt compose --source-prompt "<prompt>" --query "<keywords>"
aether prompt compose --source-prompt "<prompt>" --asset-id <visual_asset_id> --save
```

### Step 5: 生成后反向更新权重

根据 visual review 和用户反馈调整素材推荐优先级。

生成记录会自动写回素材证据。查看证据与质量分：

```bash
aether visual-asset evidence <visual_asset_id>
aether visual-asset quality <visual_asset_id>
```

## 9. 风险

### 9.1 过度拆分

不是每张图都要拆出 12 类。只沉淀有复用价值的模块。

### 9.2 素材库变脏

一次性角色、偶然道具、临时比例不要直接沉淀为长期素材。

### 9.3 组合过载

召回素材过多会让 prompt 变得混乱。组合时要控制主次。

### 9.4 自动归并风险

相似判断只能辅助，不能替用户自动合并长期资产。

### 9.5 风格和内容混淆

角色、场景、道具可以沉淀，但不要误当成画风本身。

# Aether

![](docs/assets/readme/aether-hero-visual-memory.png)

简体中文 | [English](README.en.md)

Aether 能将参考图片、提示词想法和生图结果整理成可复用的视觉记忆，方便后续持续创作出美学风格一致的图片。

## 核心能力

- **可复用视觉记忆：** 从参考图和生成结果中提炼稳定的视觉语言，并保存成可持续复用的记忆，而不是只保存一次性的提示词。
- **带记忆的提示词精修：** 召回已保存的风格、光影、色彩、构图、氛围、场景、角色和负面规则，并在保留用户原始意图的前提下组合成更稳定的提示词。
- **可演进的视觉体系：** 判断新的参考内容应该新建为记忆、归入已有记忆、保存为变体，还是作为合并候选，让视觉素材库长期增长但不混乱。
- **生成反馈闭环：** 记录生成结果、视觉一致性检查和用户反馈，让后续提示词能复用有效经验，避开已经出现过的偏差。
- **自然语言工作流：** 使用自然语言完成沉淀、精修、生成和复用视觉记忆的整个流程。

## 快速开始

通过 npm 安装：

```bash
npx aether-codex-plugin install
```

验证本地安装：

```bash
aether doctor
```

安装后重启 Codex，或者开启一个新线程让插件技能重新加载。

## 效果示例

> 生图模型使用 gpt-image-2，不同模型效果会有差异。

| 原图 | 生图 |
| --- | --- |
| <img src="docs/assets/readme/example-sketch-reference.png" alt="手绘风格参考图" width="220"> | <img src="docs/assets/readme/example-sketch-output.png" alt="手绘风格生图结果" width="220"> |
| <img src="docs/assets/readme/example-night-city-reference.png" alt="夜色城市参考图" width="220"> | <img src="docs/assets/readme/example-night-city-output.png" alt="夜色城市生图结果" width="220"> |
| <img src="docs/assets/readme/example-soft-portrait-reference.png" alt="柔和人像参考图" width="220"> | <img src="docs/assets/readme/example-soft-portrait-output.png" alt="柔和人像生图结果" width="220"> |

## 使用场景

安装后，可使用插件方式 `@Aether` 或 skill 方式 `$aether-orchestrator` 唤起。会自动根据自然语言请求选择合适的流程。

| 场景 | 示例 |
| --- | --- |
| 沉淀素材 | <img src="docs/assets/readme/workflow-capture-memory.png" alt="沉淀素材工作流截图" width="460"> |
| 浏览素材 | <img src="docs/assets/readme/workflow-browse-memory.png" alt="浏览素材工作流截图" width="460"> |
| 精修提示词 | <img src="docs/assets/readme/workflow-refine-prompt.png" alt="精修提示词工作流截图" width="460"> |
| 图片生成 | <img src="docs/assets/readme/workflow-generate-image.png" alt="图片生成工作流截图" width="460"> |
| 图片调整 | <img src="docs/assets/readme/workflow-edit-image.png" alt="图片调整工作流截图" width="460"> |

## License

MIT. See [LICENSE](LICENSE).

# Prompt Refinement Rules

Use Codex current model to refine prompts. Do not call a separate LLM.

## Preserve

- User subject.
- User scene.
- User action.
- User mood.
- Explicit constraints and exclusions.

## Enhance

- Lighting.
- Composition.
- Camera language.
- Material detail.
- Color palette.
- Atmosphere.
- Detail density.

## Do Not Replace

- The core subject.
- The user's requested setting.
- The user's requested style.
- Elements the user explicitly excludes.

If you infer missing details, add them to `assumptions`.


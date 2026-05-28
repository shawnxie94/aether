---
name: visual-asset-capture
description: Use when the user sends one or more reference images, screenshots, or image files, optionally with the prompts that generated them, and wants Aether to analyze, deduplicate, or persist reusable visual assets. This is the default Aether skill for image plus prompt inputs unless the user explicitly asks to generate a new image.
---

# Aether Visual Asset Capture

Use this skill for Aether visual asset sedimentation.

Default to this skill when the user provides reference image(s) plus prompt text and does not explicitly ask to create a new output image.

Load `references/style-taxonomy.md` when deciding whether an observed trait is reusable visual language or one-off content.

## Workflow

1. Resolve the project config from the current workspace:

```bash
aether config show
```

2. Resolve and ingest reference images.

When local image paths are available, ingest them directly:

```bash
aether asset ingest --path <image-path> --kind reference
```

When the user provides a Codex chat attachment and no normal local image path is exposed, inspect the current Codex session JSONL for the corresponding user message. Chat attachments can appear as message content items shaped like:

```json
{"type": "input_image", "image_url": "data:image/png;base64,..."}
```

For these attachments:

- Prefer the bundled extraction script:

```bash
python skills/visual-asset-capture/scripts/extract_chat_attachment.py --reference-name <stable-reference-name>
```

- Use `--session <rollout-jsonl>` when the current session is not the newest file under `$CODEX_HOME/sessions`.
- The script extracts the `data:image/*;base64,...` payload, decodes it into `cacheDir/chat-attachments/<stable-reference-name>.<ext>`, ingests it as a `reference` asset, and emits a `source_reference` JSON object.
- Store the canonical ingested asset path from that output in `source_references[].image_path`.
- Preserve the original chat reference in `source_references[].original_image_path`, such as `chat_attachment:<stable-reference-name>`.
- Store `asset_id`, `sha256`, `mime_type`, and `size_bytes` on the source reference when available.
- Do not store the full base64 data URL in the visual asset source reference.
- Do not mark a chat attachment as "no local file path available" until this session-data extraction path has been checked.

3. Analyze all provided reference images with Codex vision. If the user also provides source prompts per image, treat them as clues, not ground truth.

4. Produce `candidate_assets` as the primary output. Classify each reusable visual module into one of:

- `style`
- `color_palette`
- `lighting`
- `composition`
- `camera`
- `mood`
- `scene`
- `texture`
- `character`
- `prop_symbol`
- `shape_line`
- `negative_rule`

Do not force all 12 types. Extract only reusable modules that would be useful for future prompt composition.

Each candidate asset should include:

- `type`
- `name`
- `summary`
- `tags`
- `profile`
- `source_references`
- `prompt_fragments`
- `negative_fragments`
- `compatible_with`
- `avoid_with`
- `recommended_aspect_ratios`
- `status`: `draft`

`profile` is a structured reusable parameter object. Use only the keys allowed for the asset `type`:

- `style`: `medium`, `rendering`, `finish`, `edge_treatment`, `detail_density`, `reference_family`
- `color_palette`: `dominant_colors`, `accent_colors`, `saturation`, `contrast`, `temperature`, `color_relationship`
- `lighting`: `light_source`, `direction`, `intensity`, `contrast`, `atmosphere`, `surface_interaction`
- `composition`: `framing`, `subject_scale`, `layout`, `depth`, `negative_space`, `focal_hierarchy`
- `camera`: `shot_type`, `angle`, `lens_feel`, `depth_of_field`, `movement`, `perspective`
- `mood`: `emotional_tone`, `atmosphere`, `pacing`, `tension`, `sensory_cues`
- `scene`: `setting_type`, `environment_elements`, `spatial_layout`, `era_culture`, `weather_atmosphere`, `scale`
- `texture`: `material`, `surface_quality`, `pattern`, `granularity`, `edge_behavior`, `finish`
- `character`: `silhouette`, `anatomy`, `costume`, `expression`, `pose_language`, `identity_markers`
- `prop_symbol`: `object_type`, `symbolic_meaning`, `shape_language`, `material`, `placement`, `recurrence`
- `shape_line`: `line_quality`, `shape_language`, `contour`, `rhythm`, `geometry`, `edge_treatment`
- `negative_rule`: `avoid_subjects`, `avoid_styles`, `avoid_colors_lighting`, `avoid_composition`, `avoid_artifacts`, `reason`

Profile values may be strings, numbers, booleans, or arrays of those scalar values. Do not place free-form notes or unrelated operational metadata in `profile`; use `summary`, `tags`, or candidate `reason` fields instead.

5. When one source image yields multiple complementary candidate assets, also produce `recipe_candidates` as source-derived recommendation drafts. A recipe candidate should reference candidate asset ids, not final visual asset ids, until the user confirms those assets.

Use `recipe_assets` entries shaped like:

```json
{
  "candidate_asset_id": "<candidate-id>",
  "role": "core",
  "weight": 0.8,
  "reason": "same source image and complementary visual role"
}
```

Relation `role` is a strict enum. Use only:

- `core`: essential asset that should define the recipe or system.
- `optional`: supportive, related, or enhancement asset. Use this for natural-language intents such as "support", "related", "secondary", or "companion", and put that nuance in `reason`.
- `reference_only`: context evidence only; do not treat it as a required generation ingredient.
- `avoid`: asset or trait that should be avoided with this recipe or system.

Do not put non-enum descriptors such as `support`, `related`, `auxiliary`, or `companion` in `role`; keep those words in `reason`.

Recipe candidates should include `composition_rules` when the combination has reusable structure beyond co-occurrence. Store these as key/value rule objects:

```json
{"key": "palette_lighting_binding", "value": ["warm dusk palette should share the same rim-light source"], "reason": "stable composition constraint"}
```

Use only these `composition_rules.key` values:

- `asset_roles`: which asset types play which role in the recipe.
- `layering_order`: foreground, midground, background, overlay, or rendering order.
- `subject_scene_binding`: how character, scene, props, or symbols should interact.
- `style_application`: how style, texture, shape, or line assets should be applied.
- `palette_lighting_binding`: how palette and lighting should work together.
- `composition_camera_binding`: how composition and camera constraints should be paired.
- `mood_tone_binding`: mood and tone constraints that should guide the full combination.
- `negative_constraints`: recipe-level avoid constraints. These can become negative prompt material.

Keep source-derived recipe confidence moderate, usually `0.6` to `0.7`. Same-source co-occurrence is useful evidence, but not proof that the combination is always best.

6. When the parsed candidate assets plus recalled existing assets suggest a durable worldview, genre, series, or art direction, produce `visual_system_candidates`. Do not create a visual system automatically for every image.

Use this only when at least one of these is true:

- candidate assets cover several reusable roles, such as scene + style + palette
- related active assets are recalled from the existing library
- the source image also produced one or more recipe candidates
- the user explicitly frames the image as a world, series, IP, art direction, or genre reference

Visual system candidates should include:

- `kind`: `worldview`, `genre`, `series`, or `art_direction`
- `name`
- `summary`
- `visual_rules`
- `avoid_rules`
- `candidate_asset_relations`
- `existing_asset_relations`
- `related_existing_assets`
- `metadata.recommendation`: `suggest_create`

Use the same strict relation `role` enum for `candidate_asset_relations` and `existing_asset_relations`: `core`, `optional`, `reference_only`, or `avoid`.

Store stable visual-system constraints directly in `visual_rules` as key/value rule objects:

```json
{"key": "color_lighting", "value": ["bright", "transparent", "soft haze"], "reason": "stable art-direction constraint"}
```

Use these keys by `kind`:

- `worldview`: `setting_scope`, `environment_logic`, `culture_symbols`, `technology_magic_rules`, `recurring_motifs`, `tone_atmosphere`
- `genre`: `genre_conventions`, `subject_scope`, `palette_lighting`, `composition_pacing`, `rendering_expectations`, `genre_boundaries`
- `series`: `series_identity`, `character_continuity`, `location_continuity`, `recurring_motifs`, `palette_lighting`, `continuity_rules`
- `art_direction`: `medium`, `rendering`, `color_lighting`, `composition_language`, `material_brush_edge`, `subject_aesthetic`

Use the keys with these boundaries:

- `worldview.setting_scope`: stable world scale, locations, era, ecology, or spatial premise.
- `worldview.environment_logic`: how places behave visually, such as weather, terrain, atmosphere, or natural laws.
- `worldview.culture_symbols`: recurring cultural, architectural, costume, emblem, or object symbols.
- `worldview.technology_magic_rules`: stable technology, magic, energy, ritual, or supernatural visual logic.
- `worldview.recurring_motifs`: repeated world motifs that should remain recognizable across outputs.
- `worldview.tone_atmosphere`: persistent emotional tone and environmental atmosphere.
- `genre.genre_conventions`: genre-level visual conventions and recognizable tropes.
- `genre.subject_scope`: typical subjects, scenes, characters, or props allowed by the genre.
- `genre.palette_lighting`: genre-level color and lighting tendencies.
- `genre.composition_pacing`: framing density, rhythm, motion feel, or scene pacing conventions.
- `genre.rendering_expectations`: expected rendering style or finish for the genre.
- `genre.genre_boundaries`: constraints that prevent drift into a different genre.
- `series.series_identity`: signature identity that makes entries feel like the same series.
- `series.character_continuity`: recurring character design, silhouette, costume, or expression rules.
- `series.location_continuity`: recurring locations, spatial anchors, or set-design rules.
- `series.recurring_motifs`: repeated symbols, props, UI marks, creatures, or decorative motifs.
- `series.palette_lighting`: series-specific color and lighting continuity.
- `series.continuity_rules`: rules that keep episodes, scenes, or assets consistent over time.
- `art_direction.medium`: medium or drawing method, such as thick paint, cel shading, watercolor, pastel, 3D, or pixel art.
- `art_direction.rendering`: rendering mode, such as animation background, concept art, illustration, realism, or low-poly.
- `art_direction.color_lighting`: stable color and lighting principles.
- `art_direction.composition_language`: stable framing, depth, negative space, camera, or layout language.
- `art_direction.material_brush_edge`: stable material treatment, brushwork, texture, and edge handling.
- `art_direction.subject_aesthetic`: stable subject-matter aesthetic, such as oriental fantasy, fairy-tale fantasy, sci-fi industrial, or dark gothic.

Use `visual_rules` for positive stable constraints only. Put negative boundaries in `avoid_rules`, and keep operational context such as recommendation source, confidence, merge reason, or generation id in `metadata`. Do not create a separate `metadata.art_direction_profile` unless the user explicitly asks for one.

7. Validate visual asset drafts:

```bash
aether validate visual-asset-candidate --json <candidate-batch.json>
```

8. Persist the candidate batch before asking the user to decide. The storage layer will attach similarity suggestions against active assets of the same type, store recipe candidates, and can auto-suggest visual system candidates when no explicit `visual_system_candidates` are provided:

```bash
aether visual-asset candidates create --json <candidate-batch.json>
aether visual-asset candidates list --status pending --summary
aether visual-asset candidates get <candidate-id>
aether recipe candidates list --batch-id <batch-id>
aether visual-system candidates list --batch-id <batch-id>
```

9. Compare candidates against existing active visual assets by listing or searching matching type/tag/query when more context is needed:

```bash
aether visual-asset list --type <type> --status active --summary
aether visual-asset list --query "<keyword>" --summary
```

10. For each pending candidate, ask the user to confirm one of:

- create new visual asset
- attach as variant of an existing visual asset
- merge into an existing visual asset
- ignore as one-off content

11. If the user confirms the whole candidate batch, use the batch confirmation command. It confirms asset candidates first, then visual system candidates, then recipe candidates, and attaches recipes to newly confirmed systems when the recipe candidate has no explicit parent system:

```bash
aether visual-asset candidates confirm-batch <batch-id>
```

12. Save individual confirmed decisions through the candidate queue when the user wants to handle assets one by one:

```bash
aether visual-asset candidates decide <candidate-id> new_asset
aether visual-asset candidates decide <candidate-id> asset_variant --target-asset-id <parent-asset-id>
aether visual-asset candidates decide <candidate-id> existing_asset --target-asset-id <existing-asset-id>
aether visual-asset candidates decide <candidate-id> ignore
aether visual-asset candidates decide <candidate-id> ignore --cleanup
aether visual-asset candidates cleanup --status ignored
```

13. After all recipe assets have been confirmed or mapped to existing assets, confirm source-derived recipe candidates:

```bash
aether recipe candidates ignore <recipe-candidate-id>
aether recipe candidates ignore <recipe-candidate-id> --cleanup
aether recipe candidates cleanup --status ignored
aether recipe candidates confirm <recipe-candidate-id>
aether recipe candidates confirm <recipe-candidate-id> --system-id <visual-system-id>
```

14. After all visual system candidate assets have been confirmed or mapped to existing assets, confirm visual system candidates only if the user wants to create that higher-level system:

```bash
aether visual-system candidates get <visual-system-candidate-id>
aether visual-system candidates ignore <visual-system-candidate-id>
aether visual-system candidates ignore <visual-system-candidate-id> --cleanup
aether visual-system candidates cleanup --status ignored
aether visual-system candidates confirm <visual-system-candidate-id>
```

Use `ignore` for candidates the user has rejected. Use `ignore --cleanup` when the user explicitly says the candidate is not needed and should be removed immediately. Use `cleanup --status ignored` to physically delete ignored candidate records later. Use `delete <candidate-id>` only when the user explicitly asks to remove a specific unconfirmed candidate. Confirmed candidates are protected because they preserve creation traceability.

15. If the user confirms a direct branch or merge outside the candidate queue, use the explicit state commands:

```bash
aether visual-asset branch <parent-asset-id> --json <visual-asset.json>
aether visual-asset merge <source-asset-id> <target-asset-id>
aether visual-asset activate <visual-asset-id>
```

16. If a semantic similarity judgment was made outside the automatic candidate suggestions, save it:

```bash
aether similarity save --json <similarity-result.json>
```

Use `source_asset_id` and `candidate_asset_id` in the similarity payload.

## Rules

- Do not treat one-off subject matter as style unless it recurs across references.
- For multiple references, separate common reusable visual traits from per-image differences.
- Do not perform irreversible merges without user confirmation.
- Preserve source prompts in `source_references` when provided.
- Preserve chat attachment images as ingested reference assets whenever the session exposes an `input_image` data URL.
- Do not persist candidate visual assets without user confirmation.
- Do not turn one-off subject matter into a long-term character, prop, or scene asset unless the user confirms it should recur.
- Do not call image-generation skills from this workflow unless the user asks to generate an image after visual asset capture is complete.

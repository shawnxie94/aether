# Visual Asset Candidate Schema Cheat Sheet

Load this reference when drafting candidate assets, recipe candidates, or visual system candidates.

## Asset Types

Use only these visual asset types:

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

Do not force all types. Extract only reusable modules that would help future prompt composition.

## Language

Use English for all database-facing semantic fields in candidate payloads: `name`, `summary`, `tags`, `profile`, `prompt_fragments`, `negative_fragments`, `compatible_with`, `avoid_with`, recipe `use_cases`, `composition_rules.value`, `composition_rules.reason`, visual system `visual_rules`, `avoid_rules`, relation `reason`, and metadata notes.

Preserve user-provided source prompts, quoted text, proper nouns, file names, and `source_references.user_note` in their original language when they are evidence rather than reusable labels. User-facing explanations may be in the user's language, but saved visual memory labels and reusable prompt material should be English.

## Candidate Asset Fields

Candidate assets should include:

- `type`
- `name`
- `summary`
- `tags`
- `profile`
- `analysis_observations`
- `excluded_observations`
- `consensus`
- `source_references`
- `source_reference_ids`
- `prompt_fragments`
- `negative_fragments`
- `compatible_with`
- `avoid_with`
- `recommended_aspect_ratios`

Confirmed candidate assets become active visual assets by default. Only include `asset_status: "draft"` when the user explicitly wants a confirmed asset to remain out of active recall.

Do not include storage-owned recall or decision fields in input payloads: `related_existing_*`, `decision`, `reuse_score`, `target_asset_id`, `metadata.target_system_id`, or `metadata.target_recipe_id`.

## Profile Keys

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

Profile values may be strings, numbers, booleans, or arrays of scalar values. Put free-form notes in `summary`, `tags`, or `reason`, not in `profile`.

## Analysis Evidence

Use `analysis_observations` to preserve why a candidate was extracted. Prefer object items:

- `trait`: concise reusable visual trait.
- `evidence`: what is visible in the image that supports the trait.
- `region`: visual location such as `upper background`, `foreground`, `left rim light`, or a structured bounding note when available.
- `source_reference_id`: source reference id when known.
- `source`: `visual_observation`, `source_prompt_hint`, or `inferred`.
- `confidence`: approximate `0.0` to `1.0`.
- `reusable`: `true` unless the item should not influence future memory.

Use `excluded_observations` for one-off content that was visible but should not become reusable memory, such as a temporary object count, accidental text, a single non-recurring prop, or a source-prompt detail not supported by the image.

Use `consensus` when analyzing multiple references:

- `reference_count`: total inspected references.
- `appears_in`: number of references showing the trait.
- `consensus_strength`: approximate `0.0` to `1.0`.
- `common_traits`: traits shared by the reference set.
- `variant_traits`: stable differences that may become variants.
- `outlier_traits`: traits seen only in outlier references.

Do not put unsupported guesses into `analysis_observations` as if they were visual facts. Mark them as `source: "inferred"` or `source: "source_prompt_hint"`, lower confidence, and keep the evidence wording explicit.

## Relation Roles

Use only these relation role enum values in `recipe_assets`, `candidate_asset_relations`, and `existing_asset_relations`:

- `core`: essential asset that defines the recipe or system.
- `optional`: supportive or enhancement asset.
- `reference_only`: context evidence only.
- `avoid`: asset or trait that should be avoided.

Put natural-language role nuance such as "support", "related", "secondary", or "companion" in `reason`.

## Recipe Candidates

Use `recipe_candidates` when one source image yields multiple complementary candidate assets with reusable combination structure.

`recipe_assets` should reference candidate asset ids until the user confirms those assets.

Use only these `composition_rules.key` values:

- `asset_roles`
- `layering_order`
- `subject_scene_binding`
- `style_application`
- `palette_lighting_binding`
- `composition_camera_binding`
- `mood_tone_binding`
- `negative_constraints`

Keep source-derived recipe confidence moderate, usually `0.6` to `0.7`.

## Visual System Candidates

Use `visual_system_candidates` only when at least one is true:

- candidate assets cover several reusable roles
- related active assets are recalled from the existing library
- the source image also produced recipe candidates
- the user explicitly frames the image as a world, series, IP, art direction, or genre reference

Kinds:

- `worldview`
- `genre`
- `series`
- `art_direction`

Use these `visual_rules.key` values by kind:

- `worldview`: `setting_scope`, `environment_logic`, `culture_symbols`, `technology_magic_rules`, `recurring_motifs`, `tone_atmosphere`
- `genre`: `genre_conventions`, `subject_scope`, `palette_lighting`, `composition_pacing`, `rendering_expectations`, `genre_boundaries`
- `series`: `series_identity`, `character_continuity`, `location_continuity`, `recurring_motifs`, `palette_lighting`, `continuity_rules`
- `art_direction`: `medium`, `rendering`, `color_lighting`, `composition_language`, `material_brush_edge`, `subject_aesthetic`

Use `visual_rules` for positive stable constraints only. Put negative boundaries in `avoid_rules`; put recommendation source, confidence, merge reason, or generation id in `metadata`.

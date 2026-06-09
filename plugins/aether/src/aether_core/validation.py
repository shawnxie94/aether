from __future__ import annotations

import re
from typing import Any


class ValidationError(ValueError):
    pass


VISUAL_ASSET_TYPES = {
    "style",
    "color_palette",
    "lighting",
    "composition",
    "camera",
    "mood",
    "scene",
    "texture",
    "character",
    "prop_symbol",
    "shape_line",
    "negative_rule",
}

VISUAL_ASSET_CANDIDATE_DECISIONS = {
    "attach_evidence",
    "create_new",
    "inherit_variant",
    "merge_existing",
    "ignore",
}

OBSERVATION_SOURCES = {
    "visual_observation",
    "source_prompt_hint",
    "inferred",
}

VISUAL_SYSTEM_KINDS = {
    "worldview",
    "genre",
    "series",
    "art_direction",
}

VISUAL_ASSET_PROFILE_KEYS_BY_TYPE = {
    "style": {
        "medium",
        "rendering",
        "finish",
        "edge_treatment",
        "detail_density",
        "reference_family",
    },
    "color_palette": {
        "dominant_colors",
        "accent_colors",
        "saturation",
        "contrast",
        "temperature",
        "color_relationship",
    },
    "lighting": {
        "light_source",
        "direction",
        "intensity",
        "contrast",
        "atmosphere",
        "surface_interaction",
    },
    "composition": {
        "framing",
        "subject_scale",
        "layout",
        "depth",
        "negative_space",
        "focal_hierarchy",
    },
    "camera": {
        "shot_type",
        "angle",
        "lens_feel",
        "depth_of_field",
        "movement",
        "perspective",
    },
    "mood": {
        "emotional_tone",
        "atmosphere",
        "pacing",
        "tension",
        "sensory_cues",
    },
    "scene": {
        "setting_type",
        "environment_elements",
        "spatial_layout",
        "era_culture",
        "weather_atmosphere",
        "scale",
    },
    "texture": {
        "material",
        "surface_quality",
        "pattern",
        "granularity",
        "edge_behavior",
        "finish",
    },
    "character": {
        "silhouette",
        "anatomy",
        "costume",
        "expression",
        "pose_language",
        "identity_markers",
    },
    "prop_symbol": {
        "object_type",
        "symbolic_meaning",
        "shape_language",
        "material",
        "placement",
        "recurrence",
    },
    "shape_line": {
        "line_quality",
        "shape_language",
        "contour",
        "rhythm",
        "geometry",
        "edge_treatment",
    },
    "negative_rule": {
        "avoid_subjects",
        "avoid_styles",
        "avoid_colors_lighting",
        "avoid_composition",
        "avoid_artifacts",
        "reason",
    },
}

VISUAL_RULE_KEYS_BY_KIND = {
    "worldview": {
        "setting_scope",
        "environment_logic",
        "culture_symbols",
        "technology_magic_rules",
        "recurring_motifs",
        "tone_atmosphere",
    },
    "genre": {
        "genre_conventions",
        "subject_scope",
        "palette_lighting",
        "composition_pacing",
        "rendering_expectations",
        "genre_boundaries",
    },
    "series": {
        "series_identity",
        "character_continuity",
        "location_continuity",
        "recurring_motifs",
        "palette_lighting",
        "continuity_rules",
    },
    "art_direction": {
        "medium",
        "rendering",
        "color_lighting",
        "composition_language",
        "material_brush_edge",
        "subject_aesthetic",
    },
}

COMPOSITION_RULE_KEYS = {
    "asset_roles",
    "layering_order",
    "subject_scene_binding",
    "style_application",
    "palette_lighting_binding",
    "composition_camera_binding",
    "mood_tone_binding",
    "negative_constraints",
}

RELATION_ROLES = {
    "core",
    "optional",
    "avoid",
    "reference_only",
}

CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _validate_english_database_text(value: Any, field_path: str) -> None:
    if isinstance(value, str):
        if CJK_RE.search(value):
            raise ValidationError(
                f"Field {field_path} must use English for database-facing semantic text; "
                "preserve non-English source text only in source/reference evidence fields"
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_english_database_text(item, f"{field_path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_english_database_text(item, f"{field_path}.{key}")


def _validate_english_database_fields(payload: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        if field in payload:
            _validate_english_database_text(payload[field], field)


def _require(payload: dict[str, Any], field: str, expected_type: type | tuple[type, ...]) -> None:
    if field not in payload:
        raise ValidationError(f"Missing required field: {field}")
    if not isinstance(payload[field], expected_type):
        raise ValidationError(f"Field {field} must be {expected_type}")


def validate_visual_asset(payload: dict[str, Any]) -> None:
    _require(payload, "type", str)
    _require(payload, "name", str)
    _validate_english_database_fields(
        payload,
        [
            "name",
            "summary",
            "tags",
            "profile",
            "prompt_fragments",
            "negative_fragments",
            "compatible_with",
            "avoid_with",
        ],
    )
    if payload["type"] not in VISUAL_ASSET_TYPES:
        raise ValidationError(f"Field type must be one of: {', '.join(sorted(VISUAL_ASSET_TYPES))}")
    if "tags" in payload and not isinstance(payload["tags"], list):
        raise ValidationError("Field tags must be a list")
    if "profile" in payload and not isinstance(payload["profile"], dict):
        raise ValidationError("Field profile must be a dict")
    validate_visual_asset_profile(payload.get("profile", {}), payload["type"])
    for field in [
        "source_references",
        "prompt_fragments",
        "negative_fragments",
        "compatible_with",
        "avoid_with",
        "recommended_aspect_ratios",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if payload.get("status", "draft") == "active":
        for reference in payload.get("source_references", []):
            if not isinstance(reference, dict):
                continue
            original_path = str(reference.get("original_image_path", ""))
            if original_path.startswith("chat_attachment:") and not (
                reference.get("image_path") and reference.get("asset_id")
            ):
                raise ValidationError(
                    "Active visual assets cannot store unresolved chat_attachment source references; "
                    "run create/branch with --ingest-assets or provide source_references[].image_path."
                )


def validate_visual_asset_candidate(payload: dict[str, Any]) -> None:
    if "candidate_assets" in payload:
        if not isinstance(payload["candidate_assets"], list):
            raise ValidationError("Field candidate_assets must be a list")
        for candidate in payload["candidate_assets"]:
            if not isinstance(candidate, dict):
                raise ValidationError("Each candidate asset must be an object")
            validate_visual_asset_candidate(candidate)
        if "recipe_candidates" in payload:
            if not isinstance(payload["recipe_candidates"], list):
                raise ValidationError("Field recipe_candidates must be a list")
            for recipe in payload["recipe_candidates"]:
                if not isinstance(recipe, dict):
                    raise ValidationError("Each recipe candidate must be an object")
                validate_recipe_candidate(recipe)
        if "visual_system_candidates" in payload:
            if not isinstance(payload["visual_system_candidates"], list):
                raise ValidationError("Field visual_system_candidates must be a list")
            for system in payload["visual_system_candidates"]:
                if not isinstance(system, dict):
                    raise ValidationError("Each visual system candidate must be an object")
                validate_visual_system_candidate(system)
        return
    _require(payload, "type", str)
    _require(payload, "name", str)
    _validate_english_database_fields(
        payload,
        [
            "name",
            "summary",
            "tags",
            "profile",
            "analysis_observations",
            "excluded_observations",
            "consensus",
            "prompt_fragments",
            "negative_fragments",
            "compatible_with",
            "avoid_with",
        ],
    )
    if payload["type"] not in VISUAL_ASSET_TYPES:
        raise ValidationError(f"Field type must be one of: {', '.join(sorted(VISUAL_ASSET_TYPES))}")
    if "reuse_score" in payload and not isinstance(payload["reuse_score"], (int, float)):
        raise ValidationError("Field reuse_score must be a number")
    if "decision" in payload and payload["decision"] not in VISUAL_ASSET_CANDIDATE_DECISIONS:
        raise ValidationError(
            f"Field decision must be one of: {', '.join(sorted(VISUAL_ASSET_CANDIDATE_DECISIONS))}"
        )
    for field in [
        "tags",
        "source_references",
        "source_reference_ids",
        "prompt_fragments",
        "negative_fragments",
        "compatible_with",
        "avoid_with",
        "recommended_aspect_ratios",
        "similar_candidates",
        "analysis_observations",
        "excluded_observations",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "profile" in payload and not isinstance(payload["profile"], dict):
        raise ValidationError("Field profile must be a dict")
    if "consensus" in payload and not isinstance(payload["consensus"], dict):
        raise ValidationError("Field consensus must be a dict")
    validate_analysis_observations(payload.get("analysis_observations", []), "analysis_observations")
    validate_analysis_observations(payload.get("excluded_observations", []), "excluded_observations")
    validate_visual_asset_profile(payload.get("profile", {}), payload["type"])


def validate_analysis_observations(observations: Any, field_name: str) -> None:
    if observations in (None, ""):
        return
    if not isinstance(observations, list):
        raise ValidationError(f"Field {field_name} must be a list")
    for index, observation in enumerate(observations):
        if isinstance(observation, str):
            continue
        if not isinstance(observation, dict):
            raise ValidationError(f"Each {field_name} item must be a string or object")
        if "source" in observation and observation["source"] not in OBSERVATION_SOURCES:
            raise ValidationError(
                f"Field {field_name}[{index}].source must be one of: {', '.join(sorted(OBSERVATION_SOURCES))}"
            )
        if "confidence" in observation and not isinstance(observation["confidence"], (int, float)):
            raise ValidationError(f"Field {field_name}[{index}].confidence must be a number")
        if "reusable" in observation and not isinstance(observation["reusable"], bool):
            raise ValidationError(f"Field {field_name}[{index}].reusable must be a boolean")
        if "region" in observation and not isinstance(observation["region"], (str, dict)):
            raise ValidationError(f"Field {field_name}[{index}].region must be a string or object")


def validate_visual_system(payload: dict[str, Any]) -> None:
    _require(payload, "kind", str)
    _require(payload, "name", str)
    _validate_english_database_fields(
        payload,
        ["name", "summary", "tags", "visual_rules", "avoid_rules", "metadata"],
    )
    if payload["kind"] not in VISUAL_SYSTEM_KINDS:
        raise ValidationError(f"Field kind must be one of: {', '.join(sorted(VISUAL_SYSTEM_KINDS))}")
    for field in ["tags", "visual_rules", "avoid_rules", "source_reference_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    for rule in payload.get("visual_rules", []):
        validate_key_value_rule(
            rule,
            VISUAL_RULE_KEYS_BY_KIND[payload["kind"]],
            f"visual_rules.key for {payload['kind']}",
        )
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise ValidationError("Field metadata must be a dict")
    for field in ["parent_system_id", "merged_into_system_id"]:
        if field in payload and payload[field] is not None and not isinstance(payload[field], str):
            raise ValidationError(f"Field {field} must be a string")


def validate_visual_asset_profile(profile: dict[str, Any], asset_type: str) -> None:
    allowed_keys = VISUAL_ASSET_PROFILE_KEYS_BY_TYPE[asset_type]
    for key, value in profile.items():
        if key not in allowed_keys:
            raise ValidationError(
                f"Field profile key for {asset_type} must be one of: {', '.join(sorted(allowed_keys))}"
            )
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, (str, int, float, bool)):
                    raise ValidationError("Each profile list value must be a string, number, or boolean")
        elif not isinstance(value, (str, int, float, bool)):
            raise ValidationError("Each profile value must be a string, number, boolean, or list")


def validate_key_value_rule(rule: Any, allowed_keys: set[str], field_name: str) -> None:
    if not isinstance(rule, dict):
        raise ValidationError(f"Each {field_name.rsplit('.', 1)[0]} item must be an object with key and value")
    _require(rule, "key", str)
    _require(rule, "value", list)
    if rule["key"] not in allowed_keys:
        raise ValidationError(f"Field {field_name} must be one of: {', '.join(sorted(allowed_keys))}")
    for value in rule["value"]:
        if not isinstance(value, str):
            raise ValidationError(f"Each {field_name.rsplit('.', 1)[0]}.value item must be a string")
    if "reason" in rule and not isinstance(rule["reason"], str):
        raise ValidationError(f"Field {field_name.rsplit('.', 1)[0]}.reason must be a string")


def validate_asset_relation(payload: dict[str, Any]) -> None:
    _require(payload, "asset_id", str)
    _validate_english_database_fields(payload, ["reason"])
    if "role" in payload and payload["role"] not in RELATION_ROLES:
        raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
    if "weight" in payload and not isinstance(payload["weight"], (int, float)):
        raise ValidationError("Field weight must be a number")


def validate_recipe(payload: dict[str, Any]) -> None:
    _require(payload, "name", str)
    _validate_english_database_fields(
        payload,
        ["name", "summary", "use_cases", "composition_rules", "metadata"],
    )
    for field in [
        "parent_system_ids",
        "use_cases",
        "required_asset_types",
        "recommended_aspect_ratios",
        "source_reference_ids",
        "composition_rules",
    ]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "confidence" in payload and not isinstance(payload["confidence"], (int, float)):
        raise ValidationError("Field confidence must be a number")
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise ValidationError("Field metadata must be a dict")
    for field in ["parent_recipe_id", "merged_into_recipe_id"]:
        if field in payload and payload[field] is not None and not isinstance(payload[field], str):
            raise ValidationError(f"Field {field} must be a string")
    if payload.get("status", "draft") == "active":
        for source_reference_id in payload.get("source_reference_ids", []):
            if str(source_reference_id).startswith("chat_attachment:"):
                raise ValidationError(
                    "Active recipes cannot store chat_attachment source_reference_ids; "
                    "ingest the chat attachment as an Aether reference asset and use the asset_id."
                )
    for asset_type in payload.get("required_asset_types", []):
        if asset_type not in VISUAL_ASSET_TYPES:
            raise ValidationError(f"Field required_asset_types contains unsupported type: {asset_type}")
    for rule in payload.get("composition_rules", []):
        validate_key_value_rule(rule, COMPOSITION_RULE_KEYS, "composition_rules.key")


def validate_recipe_asset(payload: dict[str, Any]) -> None:
    validate_asset_relation(payload)


def validate_recipe_candidate(payload: dict[str, Any]) -> None:
    validate_recipe(payload)
    for field in ["candidate_asset_ids", "core_candidate_asset_ids", "optional_candidate_asset_ids", "avoid_candidate_asset_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    if "recipe_assets" in payload:
        if not isinstance(payload["recipe_assets"], list):
            raise ValidationError("Field recipe_assets must be a list")
        for relation in payload["recipe_assets"]:
            if not isinstance(relation, dict):
                raise ValidationError("Each recipe asset relation must be an object")
            if "candidate_asset_id" not in relation and "asset_id" not in relation:
                raise ValidationError("Recipe candidate relation requires candidate_asset_id or asset_id")
            if "role" in relation and relation["role"] not in RELATION_ROLES:
                raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
            if "weight" in relation and not isinstance(relation["weight"], (int, float)):
                raise ValidationError("Field weight must be a number")


def validate_visual_system_candidate(payload: dict[str, Any]) -> None:
    validate_visual_system(payload)
    for field in ["candidate_asset_ids", "core_candidate_asset_ids", "optional_candidate_asset_ids", "avoid_candidate_asset_ids"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    for field in ["candidate_asset_relations", "existing_asset_relations", "related_existing_assets"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValidationError(f"Field {field} must be a list")
    for relation in payload.get("candidate_asset_relations", []):
        if not isinstance(relation, dict):
            raise ValidationError("Each candidate asset relation must be an object")
        if "candidate_asset_id" not in relation:
            raise ValidationError("Candidate asset relation requires candidate_asset_id")
        if "role" in relation and relation["role"] not in RELATION_ROLES:
            raise ValidationError(f"Field role must be one of: {', '.join(sorted(RELATION_ROLES))}")
        if "weight" in relation and not isinstance(relation["weight"], (int, float)):
            raise ValidationError("Field weight must be a number")
    for relation in payload.get("existing_asset_relations", []):
        if not isinstance(relation, dict):
            raise ValidationError("Each existing asset relation must be an object")
        validate_asset_relation(relation)


def validate_prompt_record(payload: dict[str, Any]) -> None:
    _require(payload, "source_prompt", str)
    _require(payload, "refined_prompt", str)
    if "selected_assets" in payload and not isinstance(payload["selected_assets"], list):
        raise ValidationError("Field selected_assets must be a list")
    if "generation_params" in payload and not isinstance(payload["generation_params"], dict):
        raise ValidationError("Field generation_params must be a dict")
    if "composition_plan" in payload and not isinstance(payload["composition_plan"], dict):
        raise ValidationError("Field composition_plan must be a dict")
    if "variants" in payload and not isinstance(payload["variants"], list):
        raise ValidationError("Field variants must be a list")
    if "assumptions" in payload and not isinstance(payload["assumptions"], list):
        raise ValidationError("Field assumptions must be a list")
    if "conflicts" in payload and not isinstance(payload["conflicts"], list):
        raise ValidationError("Field conflicts must be a list")


def validate_generation_run(payload: dict[str, Any]) -> None:
    _require(payload, "refined_prompt", str)
    _require(payload, "generation_skill", str)
    if "mode" in payload and payload["mode"] not in {"generate", "edit"}:
        raise ValidationError("Field mode must be generate or edit")
    if "selected_assets" in payload and not isinstance(payload["selected_assets"], list):
        raise ValidationError("Field selected_assets must be a list")
    if "edit_regions" in payload and not isinstance(payload["edit_regions"], list):
        raise ValidationError("Field edit_regions must be a list")
    if "outputs" in payload and not isinstance(payload["outputs"], list):
        raise ValidationError("Field outputs must be a list")
    if "skill_params" in payload and not isinstance(payload["skill_params"], dict):
        raise ValidationError("Field skill_params must be a dict")
    if "visual_review" in payload and not isinstance(payload["visual_review"], dict):
        raise ValidationError("Field visual_review must be a dict")


def validate_payload(kind: str, payload: dict[str, Any]) -> None:
    if kind in ("visual_asset", "visual-asset"):
        validate_visual_asset(payload)
    elif kind in ("visual_asset_candidate", "visual-asset-candidate"):
        validate_visual_asset_candidate(payload)
    elif kind in ("visual_system", "visual-system"):
        validate_visual_system(payload)
    elif kind in ("recipe",):
        validate_recipe(payload)
    elif kind == "prompt":
        validate_prompt_record(payload)
    elif kind == "generation":
        validate_generation_run(payload)
    else:
        raise ValidationError(f"Unknown validation kind: {kind}")

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ids import new_id, slugify
from .jsonio import json_dumps, json_loads
from .migrations import record_schema_version
from .storage_time import now_iso
from .validation import (
    validate_generation_run,
    validate_prompt_record,
    validate_recipe,
    validate_recipe_asset,
    validate_recipe_candidate,
    validate_style,
    validate_visual_system,
    validate_visual_system_candidate,
    validate_asset_relation,
    validate_visual_asset,
    validate_visual_asset_candidate,
)


class AetherStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists styles (
                  id text primary key,
                  name text not null,
                  summary text not null default '',
                  tags_json text not null default '[]',
                  source_references_json text not null default '[]',
                  style_profile_json text not null default '{}',
                  prompt_template text not null default '',
                  negative_prompt text not null default '',
                  status text not null default 'draft',
                  parent_style_id text,
                  merged_into_style_id text,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists assets (
                  id text primary key,
                  kind text not null,
                  source_path text not null,
                  asset_path text not null,
                  sha256 text not null,
                  mime_type text not null default 'application/octet-stream',
                  size_bytes integer not null default 0,
                  created_at text not null
                );

                create table if not exists similarity_results (
                  id text primary key,
                  source_style_id text,
                  candidate_style_id text not null,
                  similarity_score real not null,
                  decision text not null,
                  matched_dimensions_json text not null default '[]',
                  different_dimensions_json text not null default '[]',
                  reason text not null default '',
                  created_at text not null
                );

                create table if not exists visual_assets (
                  id text primary key,
                  type text not null,
                  name text not null,
                  summary text not null default '',
                  tags_json text not null default '[]',
                  profile_json text not null default '{}',
                  source_references_json text not null default '[]',
                  prompt_fragments_json text not null default '[]',
                  negative_fragments_json text not null default '[]',
                  compatible_with_json text not null default '[]',
                  avoid_with_json text not null default '[]',
                  recommended_aspect_ratios_json text not null default '[]',
                  status text not null default 'draft',
                  parent_asset_id text,
                  merged_into_asset_id text,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists visual_asset_candidates (
                  id text primary key,
                  batch_id text not null,
                  type text not null,
                  name text not null,
                  payload_json text not null default '{}',
                  source_reference_ids_json text not null default '[]',
                  reuse_score real not null default 0,
                  decision text not null default 'new_asset',
                  similar_candidates_json text not null default '[]',
                  status text not null default 'pending',
                  target_asset_id text,
                  confirmed_asset_id text,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists visual_asset_evidence (
                  id text primary key,
                  asset_id text not null,
                  evidence_type text not null,
                  generation_run_id text,
                  payload_json text not null default '{}',
                  created_at text not null
                );

                create table if not exists visual_systems (
                  id text primary key,
                  kind text not null,
                  name text not null,
                  summary text not null default '',
                  tags_json text not null default '[]',
                  visual_rules_json text not null default '[]',
                  avoid_rules_json text not null default '[]',
                  source_reference_ids_json text not null default '[]',
                  metadata_json text not null default '{}',
                  status text not null default 'draft',
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists visual_system_assets (
                  id text primary key,
                  system_id text not null,
                  asset_id text not null,
                  role text not null default 'optional',
                  weight real not null default 0.5,
                  reason text not null default '',
                  created_at text not null,
                  updated_at text not null,
                  unique(system_id, asset_id, role)
                );

                create table if not exists recipes (
                  id text primary key,
                  name text not null,
                  summary text not null default '',
                  parent_system_ids_json text not null default '[]',
                  use_cases_json text not null default '[]',
                  required_asset_types_json text not null default '[]',
                  composition_rules_json text not null default '[]',
                  recommended_aspect_ratios_json text not null default '[]',
                  source_reference_ids_json text not null default '[]',
                  confidence real not null default 0.5,
                  source text not null default '',
                  reason text not null default '',
                  status text not null default 'draft',
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists recipe_assets (
                  id text primary key,
                  recipe_id text not null,
                  asset_id text not null,
                  role text not null default 'optional',
                  weight real not null default 0.5,
                  reason text not null default '',
                  created_at text not null,
                  updated_at text not null,
                  unique(recipe_id, asset_id, role)
                );

                create table if not exists recipe_candidates (
                  id text primary key,
                  batch_id text not null,
                  payload_json text not null default '{}',
                  status text not null default 'pending',
                  confirmed_recipe_id text,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists visual_system_candidates (
                  id text primary key,
                  batch_id text not null,
                  payload_json text not null default '{}',
                  status text not null default 'pending',
                  confirmed_system_id text,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists prompt_records (
                  id text primary key,
                  source_prompt text not null,
                  style_id text,
                  target_generation_skill text,
                  selected_assets_json text not null default '[]',
                  constraints_json text not null default '{}',
                  intent_analysis_json text not null default '{}',
                  composition_plan_json text not null default '{}',
                  refined_prompt text not null,
                  negative_prompt text not null default '',
                  generation_params_json text not null default '{}',
                  variants_json text not null default '[]',
                  assumptions_json text not null default '[]',
                  conflicts_json text not null default '[]',
                  created_at text not null
                );

                create table if not exists generation_runs (
                  id text primary key,
                  mode text not null default 'generate',
                  source_prompt text not null default '',
                  refined_prompt text not null,
                  negative_prompt text not null default '',
                  source_generation_id text,
                  source_output_asset_id text,
                  edit_instruction text not null default '',
                  edit_regions_json text not null default '[]',
                  style_id text,
                  selected_assets_json text not null default '[]',
                  generation_skill text not null,
                  skill_params_json text not null default '{}',
                  skill_result_meta_json text not null default '{}',
                  visual_review_json text not null default '{}',
                  outputs_json text not null default '[]',
                  status text not null default 'created',
                  feedback_json text not null default '{}',
                  error text not null default '',
                  created_at text not null,
                  updated_at text not null
                );
                """
            )
            self._ensure_column(conn, "prompt_records", "generation_params_json", "text not null default '{}'")
            self._ensure_column(conn, "prompt_records", "selected_assets_json", "text not null default '[]'")
            self._ensure_column(conn, "prompt_records", "composition_plan_json", "text not null default '{}'")
            self._ensure_column(conn, "prompt_records", "conflicts_json", "text not null default '[]'")
            self._ensure_column(conn, "generation_runs", "visual_review_json", "text not null default '{}'")
            self._ensure_column(conn, "generation_runs", "selected_assets_json", "text not null default '[]'")
            self._ensure_column(conn, "generation_runs", "mode", "text not null default 'generate'")
            self._ensure_column(conn, "generation_runs", "source_generation_id", "text")
            self._ensure_column(conn, "generation_runs", "source_output_asset_id", "text")
            self._ensure_column(conn, "generation_runs", "edit_instruction", "text not null default ''")
            self._ensure_column(conn, "generation_runs", "edit_regions_json", "text not null default '[]'")
            self._ensure_column(conn, "recipes", "composition_rules_json", "text not null default '[]'")
            record_schema_version(conn)

    def create_style(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_style(payload)
        timestamp = now_iso()
        style_id = payload.get("id") or slugify(payload.get("name", ""), "style")
        record = {
            "id": style_id,
            "name": payload.get("name") or style_id,
            "summary": payload.get("summary", ""),
            "tags": payload.get("tags", []),
            "source_references": payload.get("source_references", payload.get("source_images", [])),
            "style_profile": payload.get("style_profile", {}),
            "prompt_template": payload.get("prompt_template", ""),
            "negative_prompt": payload.get("negative_prompt", ""),
            "status": payload.get("status", "draft"),
            "parent_style_id": payload.get("parent_style_id"),
            "merged_into_style_id": payload.get("merged_into_style_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into styles (
                  id, name, summary, tags_json, source_references_json,
                  style_profile_json, prompt_template, negative_prompt, status,
                  parent_style_id, merged_into_style_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  name=excluded.name,
                  summary=excluded.summary,
                  tags_json=excluded.tags_json,
                  source_references_json=excluded.source_references_json,
                  style_profile_json=excluded.style_profile_json,
                  prompt_template=excluded.prompt_template,
                  negative_prompt=excluded.negative_prompt,
                  status=excluded.status,
                  parent_style_id=excluded.parent_style_id,
                  merged_into_style_id=excluded.merged_into_style_id,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["name"],
                    record["summary"],
                    json_dumps(record["tags"]),
                    json_dumps(record["source_references"]),
                    json_dumps(record["style_profile"]),
                    record["prompt_template"],
                    record["negative_prompt"],
                    record["status"],
                    record["parent_style_id"],
                    record["merged_into_style_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def update_style_status(
        self,
        style_id: str,
        status: str,
        merged_into_style_id: str | None = None,
        parent_style_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("select * from styles where id = ?", (style_id,)).fetchone()
            if not row:
                raise KeyError(f"Style not found: {style_id}")
            conn.execute(
                """
                update styles
                set status = ?,
                    merged_into_style_id = coalesce(?, merged_into_style_id),
                    parent_style_id = coalesce(?, parent_style_id),
                    updated_at = ?
                where id = ?
                """,
                (status, merged_into_style_id, parent_style_id, timestamp, style_id),
            )
        updated = self.get_style(style_id)
        assert updated is not None
        return updated

    def get_style(self, style_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from styles where id = ?", (style_id,)).fetchone()
        return self._style_from_row(row) if row else None

    def list_styles(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "select * from styles"
        params: tuple[Any, ...] = ()
        if status:
            query += " where status = ?"
            params = (status,)
        query += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._style_from_row(row) for row in rows]

    def save_similarity_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_asset_id = payload.get("source_asset_id") or payload.get("source_style_id")
        candidate_asset_id = payload.get("candidate_asset_id") or payload.get("candidate_style_id")
        if not candidate_asset_id:
            raise KeyError("candidate_asset_id is required")
        record = {
            "id": payload.get("id") or new_id("sim"),
            "source_asset_id": source_asset_id,
            "candidate_asset_id": candidate_asset_id,
            "similarity_score": float(payload["similarity_score"]),
            "decision": payload["decision"],
            "matched_dimensions": payload.get("matched_dimensions", []),
            "different_dimensions": payload.get("different_dimensions", []),
            "reason": payload.get("reason", ""),
            "created_at": payload.get("created_at", now_iso()),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into similarity_results (
                  id, source_style_id, candidate_style_id, similarity_score, decision,
                  matched_dimensions_json, different_dimensions_json, reason, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["source_asset_id"],
                    record["candidate_asset_id"],
                    record["similarity_score"],
                    record["decision"],
                    json_dumps(record["matched_dimensions"]),
                    json_dumps(record["different_dimensions"]),
                    record["reason"],
                    record["created_at"],
                ),
            )
        return record

    def create_visual_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_asset(payload)
        timestamp = now_iso()
        asset_id = payload.get("id") or slugify(f"{payload['type']}-{payload['name']}", "visual_asset")
        record = {
            "id": asset_id,
            "type": payload["type"],
            "name": payload["name"],
            "summary": payload.get("summary", ""),
            "tags": payload.get("tags", []),
            "profile": payload.get("profile", {}),
            "source_references": payload.get("source_references", []),
            "prompt_fragments": payload.get("prompt_fragments", []),
            "negative_fragments": payload.get("negative_fragments", []),
            "compatible_with": payload.get("compatible_with", []),
            "avoid_with": payload.get("avoid_with", []),
            "recommended_aspect_ratios": payload.get("recommended_aspect_ratios", []),
            "status": payload.get("status", "draft"),
            "parent_asset_id": payload.get("parent_asset_id"),
            "merged_into_asset_id": payload.get("merged_into_asset_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_assets (
                  id, type, name, summary, tags_json, profile_json, source_references_json,
                  prompt_fragments_json, negative_fragments_json, compatible_with_json,
                  avoid_with_json, recommended_aspect_ratios_json, status, parent_asset_id,
                  merged_into_asset_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  type=excluded.type,
                  name=excluded.name,
                  summary=excluded.summary,
                  tags_json=excluded.tags_json,
                  profile_json=excluded.profile_json,
                  source_references_json=excluded.source_references_json,
                  prompt_fragments_json=excluded.prompt_fragments_json,
                  negative_fragments_json=excluded.negative_fragments_json,
                  compatible_with_json=excluded.compatible_with_json,
                  avoid_with_json=excluded.avoid_with_json,
                  recommended_aspect_ratios_json=excluded.recommended_aspect_ratios_json,
                  status=excluded.status,
                  parent_asset_id=excluded.parent_asset_id,
                  merged_into_asset_id=excluded.merged_into_asset_id,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["type"],
                    record["name"],
                    record["summary"],
                    json_dumps(record["tags"]),
                    json_dumps(record["profile"]),
                    json_dumps(record["source_references"]),
                    json_dumps(record["prompt_fragments"]),
                    json_dumps(record["negative_fragments"]),
                    json_dumps(record["compatible_with"]),
                    json_dumps(record["avoid_with"]),
                    json_dumps(record["recommended_aspect_ratios"]),
                    record["status"],
                    record["parent_asset_id"],
                    record["merged_into_asset_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        for reference in record["source_references"]:
            if isinstance(reference, dict):
                self.create_visual_asset_evidence(
                    record["id"],
                    {
                        "evidence_type": "reference",
                        "payload": reference,
                    },
                )
        return record

    def get_visual_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from visual_assets where id = ?", (asset_id,)).fetchone()
        return self._visual_asset_from_row(row) if row else None

    def list_visual_assets(
        self,
        asset_type: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        query: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_assets"
        clauses: list[str] = []
        params: list[Any] = []
        if asset_type:
            clauses.append("type = ?")
            params.append(asset_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        assets = [self._visual_asset_from_row(row) for row in rows]
        if tag:
            assets = [asset for asset in assets if tag in asset.get("tags", [])]
        if query:
            needle = query.lower()
            assets = [
                asset
                for asset in assets
                if needle in asset["name"].lower()
                or needle in asset.get("summary", "").lower()
                or any(needle in item.lower() for item in asset.get("tags", []) if isinstance(item, str))
                or any(needle in item.lower() for item in asset.get("prompt_fragments", []) if isinstance(item, str))
            ]
        return assets[:limit] if limit is not None and limit >= 0 else assets

    def update_visual_asset_status(
        self,
        asset_id: str,
        status: str,
        merged_into_asset_id: str | None = None,
        parent_asset_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("select * from visual_assets where id = ?", (asset_id,)).fetchone()
            if not row:
                raise KeyError(f"Visual asset not found: {asset_id}")
            conn.execute(
                """
                update visual_assets
                set status = ?,
                    merged_into_asset_id = coalesce(?, merged_into_asset_id),
                    parent_asset_id = coalesce(?, parent_asset_id),
                    updated_at = ?
                where id = ?
                """,
                (status, merged_into_asset_id, parent_asset_id, timestamp, asset_id),
            )
        updated = self.get_visual_asset(asset_id)
        assert updated is not None
        return updated

    def merge_visual_asset(self, source_asset_id: str, target_asset_id: str) -> dict[str, Any]:
        if not self.get_visual_asset(target_asset_id):
            raise KeyError(f"Target visual asset not found: {target_asset_id}")
        return self.update_visual_asset_status(source_asset_id, "merged", merged_into_asset_id=target_asset_id)

    def branch_visual_asset(self, parent_asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_visual_asset(parent_asset_id):
            raise KeyError(f"Parent visual asset not found: {parent_asset_id}")
        payload = {**payload, "parent_asset_id": parent_asset_id}
        payload.setdefault("status", "draft")
        return self.create_visual_asset(payload)

    def create_visual_asset_candidate_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_asset_candidate(payload)
        batch_id = payload.get("batch_id") or new_id("candidate_batch")
        source_references = payload.get("source_references", [])
        candidates = [
            self.create_visual_asset_candidate(
                {
                    **candidate,
                    "batch_id": batch_id,
                    "source_references": candidate.get("source_references", source_references),
                }
            )
            for candidate in payload.get("candidate_assets", [])
        ]
        recipes = [
            self.create_recipe_candidate({**recipe, "batch_id": batch_id})
            for recipe in payload.get("recipe_candidates", [])
        ]
        system_candidate_payloads = payload.get("visual_system_candidates")
        if system_candidate_payloads is None:
            system_candidate_payloads = self._suggest_visual_system_candidates(batch_id, candidates, recipes)
        systems = [
            self.create_visual_system_candidate({**system, "batch_id": batch_id})
            for system in system_candidate_payloads
        ]
        return {
            "batch_id": batch_id,
            "candidate_assets": candidates,
            "recipe_candidates": recipes,
            "visual_system_candidates": systems,
        }

    def _suggest_visual_system_candidates(
        self,
        batch_id: str,
        candidates: list[dict[str, Any]],
        recipes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        payloads = [candidate["payload"] for candidate in candidates]
        asset_types = {payload["type"] for payload in payloads}
        related_assets = self._related_visual_assets_for_candidate_payloads(payloads)
        has_system_shape = len(payloads) >= 3 and len(asset_types) >= 2
        has_existing_context = len(related_assets) >= 2 and len(payloads) >= 2
        has_recipe_context = bool(recipes) and len(payloads) >= 2
        if not (has_system_shape or has_existing_context or has_recipe_context):
            return []

        if "character" in asset_types:
            kind = "series"
        elif "scene" in asset_types or "prop_symbol" in asset_types:
            kind = "worldview"
        elif {"style", "texture", "shape_line"} & asset_types:
            kind = "genre"
        else:
            kind = "art_direction"

        primary = next(
            (
                payload
                for preferred_type in ("scene", "character", "style", "mood")
                for payload in payloads
                if payload["type"] == preferred_type
            ),
            payloads[0],
        )
        candidate_relations = []
        for candidate in candidates:
            payload = candidate["payload"]
            role = "core" if payload["type"] in {"style", "scene", "character", "color_palette", "composition"} else "optional"
            candidate_relations.append(
                {
                    "candidate_asset_id": candidate["id"],
                    "role": role,
                    "weight": 0.85 if role == "core" else 0.6,
                    "reason": "extracted from the same source image and contributes to the suggested visual system",
                }
            )
        existing_relations = [
            {
                "asset_id": asset["asset_id"],
                "role": "optional",
                "weight": min(0.75, max(0.45, asset["similarity_score"] + 0.35)),
                "reason": "related active asset recalled by cross-asset token overlap",
            }
            for asset in related_assets[:6]
        ]
        reason_parts = []
        if has_system_shape:
            reason_parts.append("candidate assets cover multiple reusable visual roles")
        if has_existing_context:
            reason_parts.append("related active assets were recalled from the existing library")
        if has_recipe_context:
            reason_parts.append("the source image also produced recipe candidates")
        return [
            {
                "id": new_id("system_candidate"),
                "batch_id": batch_id,
                "kind": kind,
                "name": f"{primary['name']} Visual System",
                "summary": f"Suggested {kind} from source-derived visual assets and related existing assets.",
                "tags": sorted(asset_types),
                "visual_rules": self._visual_system_rules_from_sources(kind, payloads),
                "avoid_rules": [],
                "source_reference_ids": sorted(
                    {
                        source_id
                        for payload in payloads
                        for source_id in payload.get("source_reference_ids", [])
                        if isinstance(source_id, str) and source_id
                    }
                ),
                "candidate_asset_relations": candidate_relations,
                "existing_asset_relations": existing_relations,
                "related_existing_assets": related_assets[:6],
                "metadata": {
                    "recommendation": "suggest_create",
                    "confidence": 0.6 if has_system_shape else 0.5,
                    "reason": "; ".join(reason_parts),
                },
                "status": "pending",
            }
        ]

    def _related_visual_assets_for_candidate_payloads(
        self,
        payloads: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        def token_set(value: Any) -> set[str]:
            import re

            if isinstance(value, list):
                value = " ".join(str(item) for item in value)
            elif isinstance(value, dict):
                value = " ".join(str(item) for item in value.values())
            else:
                value = str(value or "")
            return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower()) if len(token) >= 2}

        source_tokens: set[str] = set()
        for payload in payloads:
            for key in ("name", "summary", "tags", "prompt_fragments", "negative_fragments", "profile", "compatible_with"):
                source_tokens |= token_set(payload.get(key))
        if not source_tokens:
            return []
        suggestions: list[dict[str, Any]] = []
        for asset in self.list_visual_assets(status="active", limit=None):
            asset_tokens: set[str] = set()
            for key in ("name", "summary", "tags", "prompt_fragments", "negative_fragments", "profile", "compatible_with"):
                asset_tokens |= token_set(asset.get(key))
            if not asset_tokens:
                continue
            score = len(source_tokens & asset_tokens) / len(source_tokens | asset_tokens)
            if score <= 0:
                continue
            suggestions.append(
                {
                    "asset_id": asset["id"],
                    "type": asset["type"],
                    "name": asset["name"],
                    "similarity_score": round(score, 4),
                    "matched_terms": sorted(source_tokens & asset_tokens)[:10],
                }
            )
        suggestions.sort(key=lambda item: item["similarity_score"], reverse=True)
        return suggestions[:limit]

    def create_visual_asset_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_asset_candidate(payload)
        timestamp = now_iso()
        candidate_id = payload.get("id") or new_id("asset_candidate")
        similar_candidates = payload.get("similar_candidates")
        if similar_candidates is None:
            similar_candidates = self._suggest_similar_visual_assets(payload)
        reuse_score = float(payload.get("reuse_score", similar_candidates[0]["similarity_score"] if similar_candidates else 0))
        decision = payload.get("decision")
        if decision is None:
            if similar_candidates and similar_candidates[0]["similarity_score"] >= 0.8:
                decision = "existing_asset"
            elif similar_candidates and similar_candidates[0]["similarity_score"] >= 0.45:
                decision = "asset_variant"
            else:
                decision = "new_asset"
        payload = {
            **payload,
            "reuse_score": reuse_score,
            "decision": decision,
            "similar_candidates": similar_candidates,
        }
        record = {
            "id": candidate_id,
            "batch_id": payload.get("batch_id") or new_id("candidate_batch"),
            "type": payload["type"],
            "name": payload["name"],
            "payload": payload,
            "source_reference_ids": payload.get("source_reference_ids", []),
            "reuse_score": reuse_score,
            "decision": decision,
            "similar_candidates": similar_candidates,
            "status": payload.get("status", "pending"),
            "target_asset_id": payload.get("target_asset_id"),
            "confirmed_asset_id": payload.get("confirmed_asset_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_asset_candidates (
                  id, batch_id, type, name, payload_json, source_reference_ids_json,
                  reuse_score, decision, similar_candidates_json, status, target_asset_id,
                  confirmed_asset_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  batch_id=excluded.batch_id,
                  type=excluded.type,
                  name=excluded.name,
                  payload_json=excluded.payload_json,
                  source_reference_ids_json=excluded.source_reference_ids_json,
                  reuse_score=excluded.reuse_score,
                  decision=excluded.decision,
                  similar_candidates_json=excluded.similar_candidates_json,
                  status=excluded.status,
                  target_asset_id=excluded.target_asset_id,
                  confirmed_asset_id=excluded.confirmed_asset_id,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["batch_id"],
                    record["type"],
                    record["name"],
                    json_dumps(record["payload"]),
                    json_dumps(record["source_reference_ids"]),
                    record["reuse_score"],
                    record["decision"],
                    json_dumps(record["similar_candidates"]),
                    record["status"],
                    record["target_asset_id"],
                    record["confirmed_asset_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def _suggest_similar_visual_assets(self, payload: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        def token_set(value: Any) -> set[str]:
            import re

            if isinstance(value, list):
                value = " ".join(str(item) for item in value)
            elif isinstance(value, dict):
                value = " ".join(str(item) for item in value.values())
            else:
                value = str(value or "")
            return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower()) if len(token) >= 2}

        source_tokens = set()
        for key in ("name", "summary", "tags", "prompt_fragments", "negative_fragments", "profile"):
            source_tokens |= token_set(payload.get(key))

        suggestions: list[dict[str, Any]] = []
        for asset in self.list_visual_assets(asset_type=payload["type"], status="active", limit=None):
            asset_tokens = set()
            for key in ("name", "summary", "tags", "prompt_fragments", "negative_fragments", "profile"):
                asset_tokens |= token_set(asset.get(key))
            if not source_tokens or not asset_tokens:
                score = 0.0
            else:
                score = len(source_tokens & asset_tokens) / len(source_tokens | asset_tokens)
            if score > 0:
                suggestions.append(
                    {
                        "asset_id": asset["id"],
                        "name": asset["name"],
                        "similarity_score": round(score, 4),
                        "matched_terms": sorted(source_tokens & asset_tokens)[:10],
                    }
                )
        suggestions.sort(key=lambda item: item["similarity_score"], reverse=True)
        return suggestions[:limit]

    def get_visual_asset_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from visual_asset_candidates where id = ?", (candidate_id,)).fetchone()
        return self._visual_asset_candidate_from_row(row) if row else None

    def list_visual_asset_candidates(
        self,
        status: str | None = None,
        batch_id: str | None = None,
        asset_type: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_asset_candidates"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if asset_type:
            clauses.append("type = ?")
            params.append(asset_type)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        candidates = [self._visual_asset_candidate_from_row(row) for row in rows]
        return candidates[:limit] if limit is not None and limit >= 0 else candidates

    def decide_visual_asset_candidate(
        self,
        candidate_id: str,
        decision: str,
        target_asset_id: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.get_visual_asset_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual asset candidate not found: {candidate_id}")
        payload = dict(candidate["payload"])
        payload["decision"] = decision
        validate_visual_asset_candidate(payload)

        confirmed_asset_id: str | None = None
        status = "confirmed"
        if decision == "new_asset":
            asset_payload = self._candidate_to_visual_asset_payload(candidate)
            confirmed_asset_id = self.create_visual_asset(asset_payload)["id"]
        elif decision == "asset_variant":
            if not target_asset_id:
                raise KeyError("target_asset_id is required for asset_variant")
            asset_payload = self._candidate_to_visual_asset_payload(candidate)
            confirmed_asset_id = self.branch_visual_asset(target_asset_id, asset_payload)["id"]
        elif decision == "existing_asset":
            if not target_asset_id:
                raise KeyError("target_asset_id is required for existing_asset")
            if not self.get_visual_asset(target_asset_id):
                raise KeyError(f"Target visual asset not found: {target_asset_id}")
            confirmed_asset_id = target_asset_id
        elif decision == "ignore":
            status = "ignored"
        else:
            raise ValueError(f"Unsupported decision: {decision}")

        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                update visual_asset_candidates
                set decision = ?,
                    status = ?,
                    target_asset_id = ?,
                    confirmed_asset_id = ?,
                    updated_at = ?
                where id = ?
                """,
                (decision, status, target_asset_id, confirmed_asset_id, timestamp, candidate_id),
            )
        updated = self.get_visual_asset_candidate(candidate_id)
        assert updated is not None
        if confirmed_asset_id:
            self.create_visual_asset_evidence(
                confirmed_asset_id,
                {
                    "evidence_type": "candidate_confirmation",
                    "payload": {
                        "candidate_id": candidate_id,
                        "decision": decision,
                        "candidate": candidate["payload"],
                    },
                },
            )
        return updated

    def ignore_visual_asset_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_visual_asset_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual asset candidate not found: {candidate_id}")
        if candidate.get("confirmed_asset_id"):
            raise ValueError(f"Confirmed visual asset candidate cannot be ignored: {candidate_id}")
        return self.decide_visual_asset_candidate(candidate_id, "ignore")

    def delete_visual_asset_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_visual_asset_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual asset candidate not found: {candidate_id}")
        if candidate.get("confirmed_asset_id") or candidate.get("status") == "confirmed":
            raise ValueError(f"Confirmed visual asset candidate cannot be deleted: {candidate_id}")
        with self.connect() as conn:
            conn.execute("delete from visual_asset_candidates where id = ?", (candidate_id,))
        return candidate

    def cleanup_visual_asset_candidates(
        self,
        status: str = "ignored",
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        return self._cleanup_candidates(
            "visual_asset",
            self.list_visual_asset_candidates(status=status, batch_id=batch_id, limit=None),
        )

    def confirm_visual_asset_candidate_batch(self, batch_id: str) -> dict[str, Any]:
        asset_results = []
        for candidate in self.list_visual_asset_candidates(batch_id=batch_id, limit=None):
            if candidate["status"] != "pending":
                asset_results.append(candidate)
                continue
            decision = candidate.get("decision") or "new_asset"
            target_asset_id = candidate.get("target_asset_id")
            if decision in {"existing_asset", "asset_variant"} and not target_asset_id:
                similar = candidate.get("similar_candidates", [])
                if similar:
                    target_asset_id = similar[0].get("asset_id")
            asset_results.append(self.decide_visual_asset_candidate(candidate["id"], decision, target_asset_id))

        system_results = []
        for candidate in self.list_visual_system_candidates(batch_id=batch_id, status="pending", limit=None):
            system_results.append(self.confirm_visual_system_candidate(candidate["id"]))

        confirmed_system_ids = [
            item.get("confirmed_system_id")
            for item in system_results
            if item.get("confirmed_system_id")
        ]
        recipe_results = []
        for candidate in self.list_recipe_candidates(batch_id=batch_id, status="pending", limit=None):
            payload = candidate.get("payload", {})
            parent_system_ids = None
            if confirmed_system_ids and not payload.get("parent_system_ids"):
                parent_system_ids = confirmed_system_ids
            recipe_results.append(self.confirm_recipe_candidate(candidate["id"], parent_system_ids=parent_system_ids))

        return {
            "batch_id": batch_id,
            "candidate_assets": asset_results,
            "visual_system_candidates": system_results,
            "recipe_candidates": recipe_results,
        }

    def _candidate_to_visual_asset_payload(self, candidate: dict[str, Any]) -> dict[str, Any]:
        payload = dict(candidate["payload"])
        return {
            "id": payload.get("asset_id") or new_id("visual_asset"),
            "type": payload["type"],
            "name": payload["name"],
            "summary": payload.get("summary", ""),
            "tags": payload.get("tags", []),
            "profile": payload.get("profile", {}),
            "source_references": payload.get("source_references", []),
            "prompt_fragments": payload.get("prompt_fragments", []),
            "negative_fragments": payload.get("negative_fragments", []),
            "compatible_with": payload.get("compatible_with", []),
            "avoid_with": payload.get("avoid_with", []),
            "recommended_aspect_ratios": payload.get("recommended_aspect_ratios", []),
            "status": payload.get("asset_status", "draft"),
        }

    def create_visual_asset_evidence(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("asset_evidence"),
            "asset_id": asset_id,
            "evidence_type": payload["evidence_type"],
            "generation_run_id": payload.get("generation_run_id"),
            "payload": payload.get("payload", {}),
            "created_at": payload.get("created_at", timestamp),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_asset_evidence (
                  id, asset_id, evidence_type, generation_run_id, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["asset_id"],
                    record["evidence_type"],
                    record["generation_run_id"],
                    json_dumps(record["payload"]),
                    record["created_at"],
                ),
            )
        return record

    def list_visual_asset_evidence(
        self,
        asset_id: str | None = None,
        evidence_type: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_asset_evidence"
        clauses: list[str] = []
        params: list[Any] = []
        if asset_id:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if evidence_type:
            clauses.append("evidence_type = ?")
            params.append(evidence_type)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        evidence = [self._visual_asset_evidence_from_row(row) for row in rows]
        return evidence[:limit] if limit is not None and limit >= 0 else evidence

    def visual_asset_quality(self, asset_id: str) -> dict[str, Any]:
        runs = self.list_generation_runs(asset_id=asset_id, limit=None)
        total = len(runs)
        pass_count = 0
        minor_count = 0
        major_count = 0
        liked = 0
        rejected = 0
        deviations: dict[str, int] = {}
        for run in runs:
            review = run.get("visual_review", {}).get("style_consistency")
            if review == "pass":
                pass_count += 1
            elif review == "minor_deviation":
                minor_count += 1
            elif review == "major_deviation":
                major_count += 1
            feedback_liked = run.get("feedback", {}).get("liked")
            if feedback_liked is True or run.get("status") == "liked":
                liked += 1
            elif feedback_liked is False or run.get("status") == "rejected":
                rejected += 1
            review_payload = run.get("visual_review", {})
            for deviation in [
                *review_payload.get("deviations", []),
                *review_payload.get("localized_deviations", []),
            ]:
                if isinstance(deviation, str) and deviation:
                    deviations[deviation] = deviations.get(deviation, 0) + 1

        score = 0.5
        if total:
            score += 0.25 * (pass_count / total)
            score += 0.1 * (minor_count / total)
            score -= 0.25 * (major_count / total)
        feedback_total = liked + rejected
        if feedback_total:
            score += 0.2 * ((liked - rejected) / feedback_total)
        score = max(0.0, min(1.0, round(score, 4)))
        return {
            "asset_id": asset_id,
            "score": score,
            "total_generations": total,
            "pass": pass_count,
            "minor_deviation": minor_count,
            "major_deviation": major_count,
            "liked": liked,
            "rejected": rejected,
            "common_deviations": [
                {"deviation": key, "count": count}
                for key, count in sorted(deviations.items(), key=lambda item: item[1], reverse=True)
            ],
        }

    def create_visual_system(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_system(payload)
        timestamp = now_iso()
        system_id = payload.get("id") or slugify(f"{payload['kind']}-{payload['name']}", "visual_system")
        record = {
            "id": system_id,
            "kind": payload["kind"],
            "name": payload["name"],
            "summary": payload.get("summary", ""),
            "tags": payload.get("tags", []),
            "visual_rules": payload.get("visual_rules", []),
            "avoid_rules": payload.get("avoid_rules", []),
            "source_reference_ids": payload.get("source_reference_ids", []),
            "metadata": payload.get("metadata", {}),
            "status": payload.get("status", "draft"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_systems (
                  id, kind, name, summary, tags_json, visual_rules_json, avoid_rules_json,
                  source_reference_ids_json, metadata_json, status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  kind=excluded.kind,
                  name=excluded.name,
                  summary=excluded.summary,
                  tags_json=excluded.tags_json,
                  visual_rules_json=excluded.visual_rules_json,
                  avoid_rules_json=excluded.avoid_rules_json,
                  source_reference_ids_json=excluded.source_reference_ids_json,
                  metadata_json=excluded.metadata_json,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["kind"],
                    record["name"],
                    record["summary"],
                    json_dumps(record["tags"]),
                    json_dumps(record["visual_rules"]),
                    json_dumps(record["avoid_rules"]),
                    json_dumps(record["source_reference_ids"]),
                    json_dumps(record["metadata"]),
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        for relation in payload.get("assets", []):
            self.set_visual_system_asset(system_id, relation)
        created = self.get_visual_system(system_id)
        assert created is not None
        return created

    def get_visual_system(self, system_id: str, include_assets: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from visual_systems where id = ?", (system_id,)).fetchone()
        if not row:
            return None
        system = self._visual_system_from_row(row)
        if include_assets:
            system["assets"] = self.list_visual_system_assets(system_id=system_id)
        return system

    def list_visual_systems(
        self,
        kind: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_systems"
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        systems = [self._visual_system_from_row(row) for row in rows]
        if query:
            needle = query.lower()
            systems = [
                system
                for system in systems
                if needle in system["name"].lower()
                or needle in system.get("summary", "").lower()
                or any(needle in item.lower() for item in system.get("tags", []) if isinstance(item, str))
            ]
        return systems[:limit] if limit is not None and limit >= 0 else systems

    def set_visual_system_asset(self, system_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_visual_system(system_id, include_assets=False):
            raise KeyError(f"Visual system not found: {system_id}")
        validate_asset_relation(payload)
        if not self.get_visual_asset(payload["asset_id"]):
            raise KeyError(f"Visual asset not found: {payload['asset_id']}")
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("system_asset"),
            "system_id": system_id,
            "asset_id": payload["asset_id"],
            "role": payload.get("role", "optional"),
            "weight": float(payload.get("weight", 0.5)),
            "reason": payload.get("reason", ""),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_system_assets (
                  id, system_id, asset_id, role, weight, reason, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(system_id, asset_id, role) do update set
                  weight=excluded.weight,
                  reason=excluded.reason,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["system_id"],
                    record["asset_id"],
                    record["role"],
                    record["weight"],
                    record["reason"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return self.get_visual_system_asset(system_id, payload["asset_id"], record["role"]) or record

    def get_visual_system_asset(self, system_id: str, asset_id: str, role: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from visual_system_assets where system_id = ? and asset_id = ? and role = ?",
                (system_id, asset_id, role),
            ).fetchone()
        return self._visual_system_asset_from_row(row) if row else None

    def list_visual_system_assets(
        self,
        system_id: str | None = None,
        role: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_system_assets"
        clauses: list[str] = []
        params: list[Any] = []
        if system_id:
            clauses.append("system_id = ?")
            params.append(system_id)
        if role:
            clauses.append("role = ?")
            params.append(role)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by weight desc, updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        relations = [self._visual_system_asset_from_row(row) for row in rows]
        return relations[:limit] if limit is not None and limit >= 0 else relations

    def create_visual_system_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_system_candidate(payload)
        timestamp = now_iso()
        candidate_id = payload.get("id") or new_id("system_candidate")
        record = {
            "id": candidate_id,
            "batch_id": payload.get("batch_id") or new_id("candidate_batch"),
            "payload": payload,
            "status": payload.get("status", "pending"),
            "confirmed_system_id": payload.get("confirmed_system_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_system_candidates (
                  id, batch_id, payload_json, status, confirmed_system_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  batch_id=excluded.batch_id,
                  payload_json=excluded.payload_json,
                  status=excluded.status,
                  confirmed_system_id=excluded.confirmed_system_id,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["batch_id"],
                    json_dumps(record["payload"]),
                    record["status"],
                    record["confirmed_system_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def get_visual_system_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from visual_system_candidates where id = ?", (candidate_id,)).fetchone()
        return self._visual_system_candidate_from_row(row) if row else None

    def list_visual_system_candidates(
        self,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_system_candidates"
        clauses: list[str] = []
        params: list[Any] = []
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        candidates = [self._visual_system_candidate_from_row(row) for row in rows]
        return candidates[:limit] if limit is not None and limit >= 0 else candidates

    def ignore_visual_system_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_visual_system_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual system candidate not found: {candidate_id}")
        if candidate.get("confirmed_system_id"):
            raise ValueError(f"Confirmed visual system candidate cannot be ignored: {candidate_id}")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                update visual_system_candidates
                set status = ?, updated_at = ?
                where id = ?
                """,
                ("ignored", timestamp, candidate_id),
            )
        updated = self.get_visual_system_candidate(candidate_id)
        assert updated is not None
        return updated

    def delete_visual_system_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_visual_system_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual system candidate not found: {candidate_id}")
        if candidate.get("confirmed_system_id") or candidate.get("status") == "confirmed":
            raise ValueError(f"Confirmed visual system candidate cannot be deleted: {candidate_id}")
        with self.connect() as conn:
            conn.execute("delete from visual_system_candidates where id = ?", (candidate_id,))
        return candidate

    def cleanup_visual_system_candidates(
        self,
        status: str = "ignored",
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        return self._cleanup_candidates(
            "visual_system",
            self.list_visual_system_candidates(status=status, batch_id=batch_id, limit=None),
        )

    def confirm_visual_system_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_visual_system_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Visual system candidate not found: {candidate_id}")
        payload = dict(candidate["payload"])
        confirmed_by_candidate = {
            item["id"]: item["confirmed_asset_id"]
            for item in self.list_visual_asset_candidates(batch_id=candidate["batch_id"], limit=None)
            if item.get("confirmed_asset_id")
        }
        assets = []
        for relation in payload.get("candidate_asset_relations", []):
            candidate_asset_id = relation.get("candidate_asset_id")
            asset_id = confirmed_by_candidate.get(candidate_asset_id)
            if not asset_id:
                raise KeyError(f"Visual system candidate asset is not confirmed: {candidate_asset_id}")
            assets.append(
                {
                    "asset_id": asset_id,
                    "role": relation.get("role", "optional"),
                    "weight": relation.get("weight", 0.5),
                    "reason": relation.get("reason", ""),
                }
            )
        if not assets:
            for field, role in [
                ("core_candidate_asset_ids", "core"),
                ("optional_candidate_asset_ids", "optional"),
                ("avoid_candidate_asset_ids", "avoid"),
            ]:
                for candidate_asset_id in payload.get(field, []):
                    asset_id = confirmed_by_candidate.get(candidate_asset_id)
                    if not asset_id:
                        raise KeyError(f"Visual system candidate asset is not confirmed: {candidate_asset_id}")
                    assets.append({"asset_id": asset_id, "role": role})
        for relation in payload.get("existing_asset_relations", []):
            assets.append(
                {
                    "asset_id": relation["asset_id"],
                    "role": relation.get("role", "optional"),
                    "weight": relation.get("weight", 0.5),
                    "reason": relation.get("reason", ""),
                }
            )
        system_payload = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "candidate_asset_ids",
                "core_candidate_asset_ids",
                "optional_candidate_asset_ids",
                "avoid_candidate_asset_ids",
                "candidate_asset_relations",
                "existing_asset_relations",
                "related_existing_assets",
                "batch_id",
            }
        }
        system_payload["assets"] = assets
        system = self.create_visual_system(system_payload)
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                update visual_system_candidates
                set status = ?, confirmed_system_id = ?, updated_at = ?
                where id = ?
                """,
                ("confirmed", system["id"], timestamp, candidate_id),
            )
        updated = self.get_visual_system_candidate(candidate_id)
        assert updated is not None
        updated["visual_system"] = system
        return updated

    def create_recipe(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_recipe(payload)
        for system_id in payload.get("parent_system_ids", []):
            if not self.get_visual_system(system_id, include_assets=False):
                raise KeyError(f"Parent visual system not found: {system_id}")
        timestamp = now_iso()
        recipe_id = payload.get("id") or self._unique_slug_id("recipes", slugify(payload["name"], "recipe"))
        record = {
            "id": recipe_id,
            "name": payload["name"],
            "summary": payload.get("summary", ""),
            "parent_system_ids": payload.get("parent_system_ids", []),
            "use_cases": payload.get("use_cases", []),
            "required_asset_types": payload.get("required_asset_types", []),
            "composition_rules": payload.get("composition_rules", []),
            "recommended_aspect_ratios": payload.get("recommended_aspect_ratios", []),
            "source_reference_ids": payload.get("source_reference_ids", []),
            "confidence": float(payload.get("confidence", 0.5)),
            "source": payload.get("source", ""),
            "reason": payload.get("reason", ""),
            "status": payload.get("status", "draft"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into recipes (
                  id, name, summary, parent_system_ids_json, use_cases_json,
                  required_asset_types_json, composition_rules_json, recommended_aspect_ratios_json,
                  source_reference_ids_json, confidence, source, reason, status,
                  created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  name=excluded.name,
                  summary=excluded.summary,
                  parent_system_ids_json=excluded.parent_system_ids_json,
                  use_cases_json=excluded.use_cases_json,
                  required_asset_types_json=excluded.required_asset_types_json,
                  composition_rules_json=excluded.composition_rules_json,
                  recommended_aspect_ratios_json=excluded.recommended_aspect_ratios_json,
                  source_reference_ids_json=excluded.source_reference_ids_json,
                  confidence=excluded.confidence,
                  source=excluded.source,
                  reason=excluded.reason,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["name"],
                    record["summary"],
                    json_dumps(record["parent_system_ids"]),
                    json_dumps(record["use_cases"]),
                    json_dumps(record["required_asset_types"]),
                    json_dumps(record["composition_rules"]),
                    json_dumps(record["recommended_aspect_ratios"]),
                    json_dumps(record["source_reference_ids"]),
                    record["confidence"],
                    record["source"],
                    record["reason"],
                    record["status"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        for relation in payload.get("assets", payload.get("recipe_assets", [])):
            self.set_recipe_asset(recipe_id, relation)
        created = self.get_recipe(recipe_id)
        assert created is not None
        return created

    def _unique_slug_id(self, table: str, base_id: str) -> str:
        if table not in {"recipes"}:
            raise ValueError(f"Unsupported table for unique slug id: {table}")
        candidate = base_id
        suffix = 2
        with self.connect() as conn:
            while conn.execute(f"select 1 from {table} where id = ?", (candidate,)).fetchone():
                candidate = f"{base_id}-{suffix}"
                suffix += 1
        return candidate

    def _cleanup_candidates(self, kind: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if kind == "visual_asset":
            delete = self.delete_visual_asset_candidate
        elif kind == "visual_system":
            delete = self.delete_visual_system_candidate
        elif kind == "recipe":
            delete = self.delete_recipe_candidate
        else:
            raise ValueError(f"Unsupported candidate kind: {kind}")
        deleted = []
        skipped = []
        for candidate in candidates:
            try:
                deleted.append(delete(candidate["id"]))
            except ValueError as exc:
                skipped.append({"id": candidate["id"], "reason": str(exc)})
        return {
            "kind": kind,
            "deleted_count": len(deleted),
            "skipped_count": len(skipped),
            "deleted": deleted,
            "skipped": skipped,
        }

    def get_recipe(self, recipe_id: str, include_assets: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from recipes where id = ?", (recipe_id,)).fetchone()
        if not row:
            return None
        recipe = self._recipe_from_row(row)
        if include_assets:
            recipe["assets"] = self.list_recipe_assets(recipe_id=recipe_id)
        return recipe

    def list_recipes(
        self,
        system_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from recipes"
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        recipes = [self._recipe_from_row(row) for row in rows]
        if system_id:
            recipes = [recipe for recipe in recipes if system_id in recipe.get("parent_system_ids", [])]
        if query:
            needle = query.lower()
            recipes = [
                recipe
                for recipe in recipes
                if needle in recipe["name"].lower()
                or needle in recipe.get("summary", "").lower()
                or any(needle in item.lower() for item in recipe.get("use_cases", []) if isinstance(item, str))
            ]
        return recipes[:limit] if limit is not None and limit >= 0 else recipes

    def set_recipe_asset(self, recipe_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_recipe(recipe_id, include_assets=False):
            raise KeyError(f"Recipe not found: {recipe_id}")
        validate_recipe_asset(payload)
        if not self.get_visual_asset(payload["asset_id"]):
            raise KeyError(f"Visual asset not found: {payload['asset_id']}")
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("recipe_asset"),
            "recipe_id": recipe_id,
            "asset_id": payload["asset_id"],
            "role": payload.get("role", "optional"),
            "weight": float(payload.get("weight", 0.5)),
            "reason": payload.get("reason", ""),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into recipe_assets (
                  id, recipe_id, asset_id, role, weight, reason, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(recipe_id, asset_id, role) do update set
                  weight=excluded.weight,
                  reason=excluded.reason,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["recipe_id"],
                    record["asset_id"],
                    record["role"],
                    record["weight"],
                    record["reason"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return self.get_recipe_asset(recipe_id, payload["asset_id"], record["role"]) or record

    def get_recipe_asset(self, recipe_id: str, asset_id: str, role: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from recipe_assets where recipe_id = ? and asset_id = ? and role = ?",
                (recipe_id, asset_id, role),
            ).fetchone()
        return self._recipe_asset_from_row(row) if row else None

    def list_recipe_assets(
        self,
        recipe_id: str | None = None,
        role: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select * from recipe_assets"
        clauses: list[str] = []
        params: list[Any] = []
        if recipe_id:
            clauses.append("recipe_id = ?")
            params.append(recipe_id)
        if role:
            clauses.append("role = ?")
            params.append(role)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by weight desc, updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        relations = [self._recipe_asset_from_row(row) for row in rows]
        return relations[:limit] if limit is not None and limit >= 0 else relations

    def create_recipe_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_recipe_candidate(payload)
        timestamp = now_iso()
        candidate_id = payload.get("id") or new_id("recipe_candidate")
        record = {
            "id": candidate_id,
            "batch_id": payload.get("batch_id") or new_id("candidate_batch"),
            "payload": payload,
            "status": payload.get("status", "pending"),
            "confirmed_recipe_id": payload.get("confirmed_recipe_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into recipe_candidates (
                  id, batch_id, payload_json, status, confirmed_recipe_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  batch_id=excluded.batch_id,
                  payload_json=excluded.payload_json,
                  status=excluded.status,
                  confirmed_recipe_id=excluded.confirmed_recipe_id,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["batch_id"],
                    json_dumps(record["payload"]),
                    record["status"],
                    record["confirmed_recipe_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def get_recipe_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from recipe_candidates where id = ?", (candidate_id,)).fetchone()
        return self._recipe_candidate_from_row(row) if row else None

    def list_recipe_candidates(
        self,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from recipe_candidates"
        clauses: list[str] = []
        params: list[Any] = []
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        candidates = [self._recipe_candidate_from_row(row) for row in rows]
        return candidates[:limit] if limit is not None and limit >= 0 else candidates

    def ignore_recipe_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_recipe_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Recipe candidate not found: {candidate_id}")
        if candidate.get("confirmed_recipe_id"):
            raise ValueError(f"Confirmed recipe candidate cannot be ignored: {candidate_id}")
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                update recipe_candidates
                set status = ?, updated_at = ?
                where id = ?
                """,
                ("ignored", timestamp, candidate_id),
            )
        updated = self.get_recipe_candidate(candidate_id)
        assert updated is not None
        return updated

    def delete_recipe_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_recipe_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Recipe candidate not found: {candidate_id}")
        if candidate.get("confirmed_recipe_id") or candidate.get("status") == "confirmed":
            raise ValueError(f"Confirmed recipe candidate cannot be deleted: {candidate_id}")
        with self.connect() as conn:
            conn.execute("delete from recipe_candidates where id = ?", (candidate_id,))
        return candidate

    def cleanup_recipe_candidates(
        self,
        status: str = "ignored",
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        return self._cleanup_candidates(
            "recipe",
            self.list_recipe_candidates(status=status, batch_id=batch_id, limit=None),
        )

    def confirm_recipe_candidate(self, candidate_id: str, parent_system_ids: list[str] | None = None) -> dict[str, Any]:
        candidate = self.get_recipe_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Recipe candidate not found: {candidate_id}")
        payload = dict(candidate["payload"])
        confirmed_by_candidate = {
            item["id"]: item["confirmed_asset_id"]
            for item in self.list_visual_asset_candidates(batch_id=candidate["batch_id"], limit=None)
            if item.get("confirmed_asset_id")
        }
        recipe_assets = []
        for relation in payload.get("recipe_assets", []):
            asset_id = relation.get("asset_id")
            candidate_asset_id = relation.get("candidate_asset_id")
            if not asset_id and candidate_asset_id:
                asset_id = confirmed_by_candidate.get(candidate_asset_id)
            if not asset_id:
                raise KeyError(f"Recipe candidate asset is not confirmed: {candidate_asset_id}")
            recipe_assets.append(
                {
                    "asset_id": asset_id,
                    "role": relation.get("role", "optional"),
                    "weight": relation.get("weight", 0.5),
                    "reason": relation.get("reason", ""),
                }
            )
        if not recipe_assets:
            for field, role in [
                ("core_candidate_asset_ids", "core"),
                ("optional_candidate_asset_ids", "optional"),
                ("avoid_candidate_asset_ids", "avoid"),
            ]:
                for candidate_asset_id in payload.get(field, []):
                    asset_id = confirmed_by_candidate.get(candidate_asset_id)
                    if not asset_id:
                        raise KeyError(f"Recipe candidate asset is not confirmed: {candidate_asset_id}")
                    recipe_assets.append({"asset_id": asset_id, "role": role})
        recipe_payload = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "candidate_asset_ids",
                "core_candidate_asset_ids",
                "optional_candidate_asset_ids",
                "avoid_candidate_asset_ids",
                "recipe_assets",
                "batch_id",
            }
        }
        if parent_system_ids is not None:
            recipe_payload["parent_system_ids"] = parent_system_ids
        recipe_payload["assets"] = recipe_assets
        recipe = self.create_recipe(recipe_payload)
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                update recipe_candidates
                set status = ?, confirmed_recipe_id = ?, updated_at = ?
                where id = ?
                """,
                ("confirmed", recipe["id"], timestamp, candidate_id),
            )
        updated = self.get_recipe_candidate(candidate_id)
        assert updated is not None
        updated["recipe"] = recipe
        return updated

    def create_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": payload.get("id") or new_id("asset"),
            "kind": payload["kind"],
            "source_path": payload["source_path"],
            "asset_path": payload["asset_path"],
            "sha256": payload["sha256"],
            "mime_type": payload.get("mime_type", "application/octet-stream"),
            "size_bytes": int(payload.get("size_bytes", 0)),
            "created_at": payload.get("created_at", now_iso()),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into assets (
                  id, kind, source_path, asset_path, sha256, mime_type, size_bytes, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["kind"],
                    record["source_path"],
                    record["asset_path"],
                    record["sha256"],
                    record["mime_type"],
                    record["size_bytes"],
                    record["created_at"],
                ),
            )
        return record

    def list_assets(self, kind: str | None = None, limit: int | None = 50) -> list[dict[str, Any]]:
        query = "select * from assets"
        params: tuple[Any, ...] = ()
        if kind:
            query += " where kind = ?"
            params = (kind,)
        query += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        assets = [self._asset_from_row(row) for row in rows]
        return assets[:limit] if limit is not None and limit >= 0 else assets

    def asset_stats(self) -> dict[str, Any]:
        assets = self.list_assets(limit=None)
        by_kind: dict[str, dict[str, int]] = {}
        missing_files = 0
        total_size = 0
        for asset in assets:
            kind = asset["kind"]
            kind_stats = by_kind.setdefault(kind, {"count": 0, "size_bytes": 0, "missing_files": 0})
            kind_stats["count"] += 1
            kind_stats["size_bytes"] += asset["size_bytes"]
            total_size += asset["size_bytes"]
            if not Path(asset["asset_path"]).exists():
                kind_stats["missing_files"] += 1
                missing_files += 1
        return {
            "total": len(assets),
            "size_bytes": total_size,
            "missing_files": missing_files,
            "by_kind": by_kind,
        }

    def duplicate_assets(self, kind: str | None = None) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for asset in self.list_assets(kind=kind, limit=None):
            groups.setdefault(asset["sha256"], []).append(asset)
        return [
            {
                "sha256": sha256,
                "count": len(assets),
                "size_bytes": sum(asset["size_bytes"] for asset in assets),
                "assets": assets,
            }
            for sha256, assets in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
            if len(assets) > 1
        ]

    def unreferenced_assets(self, kind: str | None = None) -> list[dict[str, Any]]:
        referenced_ids, referenced_paths = self._referenced_asset_keys()
        assets = self.list_assets(kind=kind, limit=None)
        return [
            asset
            for asset in assets
            if asset["id"] not in referenced_ids and asset["asset_path"] not in referenced_paths
        ]

    def _referenced_asset_keys(self) -> tuple[set[str], set[str]]:
        referenced_ids: set[str] = set()
        referenced_paths: set[str] = set()

        for style in self.list_styles():
            for reference in style.get("source_references", []):
                if isinstance(reference, dict):
                    asset_id = reference.get("asset_id")
                    if isinstance(asset_id, str) and asset_id:
                        referenced_ids.add(asset_id)
                    for key in ("asset_path", "image_path"):
                        value = reference.get(key)
                        if isinstance(value, str) and value:
                            referenced_paths.add(value)

        for visual_asset in self.list_visual_assets(limit=None):
            for reference in visual_asset.get("source_references", []):
                if isinstance(reference, dict):
                    asset_id = reference.get("asset_id")
                    if isinstance(asset_id, str) and asset_id:
                        referenced_ids.add(asset_id)
                    for key in ("asset_path", "image_path"):
                        value = reference.get(key)
                        if isinstance(value, str) and value:
                            referenced_paths.add(value)

        for system in self.list_visual_systems(limit=None):
            for asset_id in system.get("source_reference_ids", []):
                if isinstance(asset_id, str) and asset_id:
                    referenced_ids.add(asset_id)

        for recipe in self.list_recipes(limit=None):
            for asset_id in recipe.get("source_reference_ids", []):
                if isinstance(asset_id, str) and asset_id:
                    referenced_ids.add(asset_id)

        for run in self.list_generation_runs(limit=None):
            for output in run.get("outputs", []):
                if isinstance(output, dict):
                    asset_id = output.get("asset_id")
                    if isinstance(asset_id, str) and asset_id:
                        referenced_ids.add(asset_id)
                    for key in ("asset_path", "image_path"):
                        value = output.get(key)
                        if isinstance(value, str) and value:
                            referenced_paths.add(value)
                elif isinstance(output, str) and output:
                    referenced_paths.add(output)

        return referenced_ids, referenced_paths

    def save_prompt_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_prompt_record(payload)
        constraints = payload.get("constraints", {})
        selected_assets = payload.get("selected_assets")
        if selected_assets is None and isinstance(constraints, dict):
            selected_assets = constraints.get("selected_assets", [])
        record = {
            "id": payload.get("id") or new_id("prompt"),
            "source_prompt": payload["source_prompt"],
            "style_id": payload.get("style_id"),
            "target_generation_skill": payload.get("target_generation_skill"),
            "selected_assets": selected_assets or [],
            "constraints": constraints,
            "intent_analysis": payload.get("intent_analysis", {}),
            "composition_plan": payload.get("composition_plan", {}),
            "refined_prompt": payload["refined_prompt"],
            "negative_prompt": payload.get("negative_prompt", ""),
            "generation_params": payload.get("generation_params", {}),
            "variants": payload.get("variants", []),
            "assumptions": payload.get("assumptions", []),
            "conflicts": payload.get("conflicts", []),
            "created_at": payload.get("created_at", now_iso()),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into prompt_records (
                  id, source_prompt, style_id, target_generation_skill, selected_assets_json, constraints_json,
                  intent_analysis_json, composition_plan_json, refined_prompt, negative_prompt, generation_params_json,
                  variants_json, assumptions_json, conflicts_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["source_prompt"],
                    record["style_id"],
                    record["target_generation_skill"],
                    json_dumps(record["selected_assets"]),
                    json_dumps(record["constraints"]),
                    json_dumps(record["intent_analysis"]),
                    json_dumps(record["composition_plan"]),
                    record["refined_prompt"],
                    record["negative_prompt"],
                    json_dumps(record["generation_params"]),
                    json_dumps(record["variants"]),
                    json_dumps(record["assumptions"]),
                    json_dumps(record["conflicts"]),
                    record["created_at"],
                ),
            )
        return record

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"alter table {table} add column {column} {definition}")

    def create_generation_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_generation_run(payload)
        timestamp = now_iso()
        prompt_record = payload.get("prompt_record", {})
        selected_assets = payload.get("selected_assets")
        if selected_assets is None and isinstance(prompt_record, dict):
            selected_assets = prompt_record.get("selected_assets")
            constraints = prompt_record.get("constraints", {})
            if selected_assets is None and isinstance(constraints, dict):
                selected_assets = constraints.get("selected_assets")
        record = {
            "id": payload.get("id") or new_id("generation"),
            "mode": payload.get("mode", "generate"),
            "source_prompt": payload.get("source_prompt", ""),
            "refined_prompt": payload["refined_prompt"],
            "negative_prompt": payload.get("negative_prompt", ""),
            "source_generation_id": payload.get("source_generation_id"),
            "source_output_asset_id": payload.get("source_output_asset_id"),
            "edit_instruction": payload.get("edit_instruction", ""),
            "edit_regions": payload.get("edit_regions", []),
            "style_id": payload.get("style_id"),
            "selected_assets": selected_assets or [],
            "generation_skill": payload["generation_skill"],
            "skill_params": payload.get("skill_params", {}),
            "skill_result_meta": payload.get("skill_result_meta", {}),
            "visual_review": payload.get("visual_review", {}),
            "outputs": payload.get("outputs", []),
            "status": payload.get("status", "created"),
            "feedback": payload.get("feedback", {}),
            "error": payload.get("error", ""),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into generation_runs (
                  id, mode, source_prompt, refined_prompt, negative_prompt,
                  source_generation_id, source_output_asset_id, edit_instruction, edit_regions_json,
                  style_id, selected_assets_json,
                  generation_skill, skill_params_json, skill_result_meta_json, visual_review_json,
                  outputs_json, status, feedback_json, error, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["mode"],
                    record["source_prompt"],
                    record["refined_prompt"],
                    record["negative_prompt"],
                    record["source_generation_id"],
                    record["source_output_asset_id"],
                    record["edit_instruction"],
                    json_dumps(record["edit_regions"]),
                    record["style_id"],
                    json_dumps(record["selected_assets"]),
                    record["generation_skill"],
                    json_dumps(record["skill_params"]),
                    json_dumps(record["skill_result_meta"]),
                    json_dumps(record["visual_review"]),
                    json_dumps(record["outputs"]),
                    record["status"],
                    json_dumps(record["feedback"]),
                    record["error"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        self._record_generation_evidence(record)
        suggestions = self.suggest_generation_reuse(record["id"], auto=True)
        if suggestions.get("recipe_candidates") or suggestions.get("visual_system_candidates"):
            record["reuse_suggestions"] = suggestions
        return record

    def update_generation_feedback(self, run_id: str, feedback: dict[str, Any], status: str | None) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("select * from generation_runs where id = ?", (run_id,)).fetchone()
            if not row:
                raise KeyError(f"Generation run not found: {run_id}")
            current = self._generation_from_row(row)
            merged_feedback = {**current["feedback"], **feedback}
            next_status = status or current["status"]
            conn.execute(
                "update generation_runs set feedback_json = ?, status = ?, updated_at = ? where id = ?",
                (json_dumps(merged_feedback), next_status, timestamp, run_id),
            )
        current["feedback"] = merged_feedback
        current["status"] = next_status
        current["updated_at"] = timestamp
        for selected in current.get("selected_assets", []):
            asset_id = self._selected_asset_id(selected)
            if asset_id:
                self.create_visual_asset_evidence(
                    asset_id,
                    {
                        "evidence_type": "user_feedback",
                        "generation_run_id": run_id,
                        "payload": {"feedback": feedback, "status": next_status},
                    },
                )
        if feedback.get("liked") is True or next_status == "liked":
            suggestions = self.suggest_generation_reuse(run_id, auto=True)
            if suggestions.get("recipe_candidates") or suggestions.get("visual_system_candidates"):
                current["reuse_suggestions"] = suggestions
        return current

    def get_generation_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from generation_runs where id = ?", (run_id,)).fetchone()
        return self._generation_from_row(row) if row else None

    def list_generation_runs(
        self,
        style_id: str | None = None,
        asset_id: str | None = None,
        status: str | None = None,
        review: str | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, Any]]:
        query = "select * from generation_runs"
        clauses: list[str] = []
        params: list[Any] = []
        if style_id:
            clauses.append("style_id = ?")
            params.append(style_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " where " + " and ".join(clauses)
        query += " order by updated_at desc"
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        runs = [self._generation_from_row(row) for row in rows]
        if asset_id:
            runs = [run for run in runs if self._run_uses_asset(run, asset_id)]
        if review:
            runs = [run for run in runs if run.get("visual_review", {}).get("style_consistency") == review]
        return runs[:limit] if limit is not None and limit >= 0 else runs

    def generation_stats(self, style_id: str | None = None, asset_id: str | None = None) -> dict[str, Any]:
        runs = self.list_generation_runs(style_id=style_id, asset_id=asset_id, limit=None)
        by_status: dict[str, int] = {}
        by_review: dict[str, int] = {}
        by_style: dict[str, dict[str, Any]] = {}
        by_asset: dict[str, dict[str, Any]] = {}
        feedback: dict[str, int] = {"liked": 0, "rejected": 0, "unrated": 0}
        deviations: dict[str, int] = {}

        for run in runs:
            status = run.get("status") or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

            review = run.get("visual_review", {}).get("style_consistency") or "not_reviewed"
            by_review[review] = by_review.get(review, 0) + 1

            style_key = run.get("style_id") or "(none)"
            style_stats = by_style.setdefault(
                style_key,
                {
                    "total": 0,
                    "liked": 0,
                    "rejected": 0,
                    "review": {},
                },
            )
            style_stats["total"] += 1
            style_stats["review"][review] = style_stats["review"].get(review, 0) + 1

            for selected in run.get("selected_assets", []):
                selected_id = self._selected_asset_id(selected)
                if not selected_id:
                    continue
                asset_stats = by_asset.setdefault(
                    selected_id,
                    {
                        "total": 0,
                        "liked": 0,
                        "rejected": 0,
                        "review": {},
                    },
                )
                asset_stats["total"] += 1
                asset_stats["review"][review] = asset_stats["review"].get(review, 0) + 1

            liked = run.get("feedback", {}).get("liked")
            if liked is True or run.get("status") == "liked":
                feedback["liked"] += 1
                style_stats["liked"] += 1
                for selected in run.get("selected_assets", []):
                    selected_id = self._selected_asset_id(selected)
                    if selected_id and selected_id in by_asset:
                        by_asset[selected_id]["liked"] += 1
            elif liked is False or run.get("status") == "rejected":
                feedback["rejected"] += 1
                style_stats["rejected"] += 1
                for selected in run.get("selected_assets", []):
                    selected_id = self._selected_asset_id(selected)
                    if selected_id and selected_id in by_asset:
                        by_asset[selected_id]["rejected"] += 1
            else:
                feedback["unrated"] += 1

            review_payload = run.get("visual_review", {})
            for deviation in [
                *review_payload.get("deviations", []),
                *review_payload.get("localized_deviations", []),
            ]:
                if isinstance(deviation, str) and deviation:
                    deviations[deviation] = deviations.get(deviation, 0) + 1

        return {
            "total": len(runs),
            "by_status": by_status,
            "by_review": by_review,
            "feedback": feedback,
            "by_style": by_style,
            "by_asset": by_asset,
            "common_deviations": [
                {"deviation": key, "count": count}
                for key, count in sorted(deviations.items(), key=lambda item: item[1], reverse=True)
            ],
        }

    def suggest_generation_reuse(
        self,
        run_id: str,
        kind: str | None = None,
        auto: bool = False,
    ) -> dict[str, Any]:
        run = self.get_generation_run(run_id)
        if not run:
            raise KeyError(f"Generation run not found: {run_id}")
        selected_assets = self._generation_selected_visual_assets(run)
        selected_ids = [asset["id"] for asset in selected_assets]
        selected_types = {asset["type"] for asset in selected_assets}
        batch_id = f"generation_{run_id}"
        review = run.get("visual_review", {})
        review_score = float(review.get("score", 0) or 0)
        consistency = review.get("style_consistency")
        liked = run.get("feedback", {}).get("liked") is True or run.get("status") == "liked"
        review_passed = consistency in {"pass", "minor_deviation"} or review_score >= 0.75
        result: dict[str, Any] = {
            "generation_run_id": run_id,
            "batch_id": batch_id,
            "eligible": False,
            "recipe_candidates": [],
            "visual_system_candidates": [],
            "skipped": [],
        }
        if len(selected_assets) < 2:
            result["skipped"].append("requires at least two selected visual assets")
            return result
        if not (liked or review_passed):
            result["skipped"].append("generation was not liked and did not pass visual review")
            return result
        result["eligible"] = True

        if kind in (None, "recipe"):
            existing_recipe_candidates = self.list_recipe_candidates(batch_id=batch_id, limit=None)
            if existing_recipe_candidates:
                result["recipe_candidates"] = existing_recipe_candidates
            elif self._has_duplicate_recipe(selected_ids):
                result["skipped"].append("similar recipe already exists")
            else:
                result["recipe_candidates"].append(self.create_recipe_candidate(self._generation_recipe_candidate_payload(run, selected_assets, batch_id)))

        can_suggest_system = (
            len(selected_assets) >= 3
            and len(selected_types) >= 3
            and (liked or review_score >= 0.85 or consistency == "pass")
            and bool(selected_types & {"character", "scene", "style"})
        )
        if kind in (None, "visual-system"):
            existing_system_candidates = self.list_visual_system_candidates(batch_id=batch_id, limit=None)
            if existing_system_candidates:
                result["visual_system_candidates"] = existing_system_candidates
            elif not can_suggest_system:
                result["skipped"].append("visual system suggestion requires stronger multi-asset evidence")
            elif self._has_duplicate_visual_system(selected_ids):
                result["skipped"].append("similar visual system already exists")
            else:
                result["visual_system_candidates"].append(
                    self.create_visual_system_candidate(
                        self._generation_visual_system_candidate_payload(run, selected_assets, batch_id)
                    )
                )
        return result

    def _generation_selected_visual_assets(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        assets = []
        seen: set[str] = set()
        for selected in run.get("selected_assets", []):
            asset_id = self._selected_asset_id(selected)
            if not asset_id or asset_id in seen:
                continue
            asset = self.get_visual_asset(asset_id)
            if asset and asset["status"] != "archived":
                assets.append(asset)
                seen.add(asset_id)
        return assets

    def _asset_set_jaccard(self, left: list[str], right: list[str]) -> float:
        left_set = set(left)
        right_set = set(right)
        if not left_set or not right_set:
            return 0.0
        return len(left_set & right_set) / len(left_set | right_set)

    def _visual_system_rules_from_sources(self, kind: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        categories_by_kind = {
            "worldview": [
                ("setting_scope", {"scene"}),
                ("environment_logic", {"scene", "mood", "lighting"}),
                ("culture_symbols", {"prop_symbol", "shape_line"}),
                ("technology_magic_rules", {"prop_symbol", "negative_rule"}),
                ("recurring_motifs", {"prop_symbol", "shape_line", "texture"}),
                ("tone_atmosphere", {"mood", "lighting", "color_palette"}),
            ],
            "genre": [
                ("genre_conventions", {"style", "scene", "prop_symbol"}),
                ("subject_scope", {"scene", "character", "prop_symbol"}),
                ("palette_lighting", {"color_palette", "lighting", "mood"}),
                ("composition_pacing", {"composition", "camera"}),
                ("rendering_expectations", {"style", "texture", "shape_line"}),
                ("genre_boundaries", {"negative_rule"}),
            ],
            "series": [
                ("series_identity", {"character", "scene", "prop_symbol"}),
                ("character_continuity", {"character", "style"}),
                ("location_continuity", {"scene"}),
                ("recurring_motifs", {"prop_symbol", "shape_line", "texture"}),
                ("palette_lighting", {"color_palette", "lighting", "mood"}),
                ("continuity_rules", {"composition", "camera", "negative_rule"}),
            ],
            "art_direction": [
                ("medium", {"style", "texture", "shape_line"}),
                ("rendering", {"style", "camera"}),
                ("color_lighting", {"color_palette", "lighting", "mood"}),
                ("composition_language", {"composition", "camera", "scene"}),
                ("material_brush_edge", {"texture", "shape_line", "style"}),
                ("subject_aesthetic", {"scene", "character", "prop_symbol", "mood"}),
            ],
        }
        rules = []
        for key, asset_types in categories_by_kind.get(kind, []):
            values = []
            for source in sources:
                if source.get("type") not in asset_types:
                    continue
                value = source.get("summary") or source.get("name")
                if isinstance(value, str) and value and value not in values:
                    values.append(value)
            rules.append({"key": key, "value": values[:4] if values else ["to_be_confirmed"]})
        return rules

    def _has_duplicate_recipe(self, selected_ids: list[str], threshold: float = 0.8) -> bool:
        for recipe in self.list_recipes(limit=None):
            recipe_ids = [relation["asset_id"] for relation in self.list_recipe_assets(recipe_id=recipe["id"])]
            if self._asset_set_jaccard(selected_ids, recipe_ids) >= threshold:
                return True
        return False

    def _has_duplicate_visual_system(self, selected_ids: list[str], threshold: float = 0.8) -> bool:
        for system in self.list_visual_systems(limit=None):
            system_ids = [relation["asset_id"] for relation in self.list_visual_system_assets(system_id=system["id"])]
            if self._asset_set_jaccard(selected_ids, system_ids) >= threshold:
                return True
        return False

    def _generation_recipe_candidate_payload(
        self,
        run: dict[str, Any],
        selected_assets: list[dict[str, Any]],
        batch_id: str,
    ) -> dict[str, Any]:
        review = run.get("visual_review", {})
        source_prompt = run.get("source_prompt") or run.get("refined_prompt", "")
        short_name = " ".join(source_prompt.split())[:48] or run["id"]
        return {
            "batch_id": batch_id,
            "name": f"Generated Recipe: {short_name}",
            "summary": "Suggested from a successful generation using multiple reusable visual assets.",
            "use_cases": ["post-generation reuse"],
            "required_asset_types": sorted({asset["type"] for asset in selected_assets}),
            "composition_rules": self._recipe_composition_rules_from_assets(selected_assets),
            "recommended_aspect_ratios": [run.get("skill_params", {}).get("aspectRatio")]
            if run.get("skill_params", {}).get("aspectRatio")
            else [],
            "recipe_assets": [
                {
                    "asset_id": asset["id"],
                    "role": "core" if asset["type"] in {"style", "scene", "character", "color_palette", "composition"} else "optional",
                    "weight": 0.85 if asset["type"] in {"style", "scene", "character", "color_palette", "composition"} else 0.6,
                    "reason": "selected asset contributed to a successful generation",
                }
                for asset in selected_assets
            ],
            "confidence": 0.75 if run.get("feedback", {}).get("liked") is True or run.get("status") == "liked" else 0.65,
            "source": "generation_run",
            "reason": "generation passed review or was liked by the user",
            "metadata": {
                "source_generation_id": run["id"],
                "source_generation_status": run.get("status"),
                "source_review_score": review.get("score"),
                "source_style_consistency": review.get("style_consistency"),
            },
            "status": "pending",
        }

    def _recipe_composition_rules_from_assets(self, selected_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        role_values = [f"{asset['type']}: {asset['name']}" for asset in selected_assets]
        if role_values:
            rules.append(
                {
                    "key": "asset_roles",
                    "value": role_values,
                    "reason": "selected assets were used together in a successful generation",
                }
            )
        type_names = {
            asset_type: [asset["name"] for asset in selected_assets if asset["type"] == asset_type]
            for asset_type in {asset["type"] for asset in selected_assets}
        }
        if any(asset_type in type_names for asset_type in ("style", "texture", "shape_line")):
            rules.append(
                {
                    "key": "style_application",
                    "value": [
                        f"{asset_type}: {', '.join(type_names[asset_type])}"
                        for asset_type in ("style", "texture", "shape_line")
                        if asset_type in type_names
                    ],
                    "reason": "style-facing assets define how the recipe should be rendered",
                }
            )
        if any(asset_type in type_names for asset_type in ("color_palette", "lighting")):
            rules.append(
                {
                    "key": "palette_lighting_binding",
                    "value": [
                        f"{asset_type}: {', '.join(type_names[asset_type])}"
                        for asset_type in ("color_palette", "lighting")
                        if asset_type in type_names
                    ],
                    "reason": "palette and lighting assets should be applied together",
                }
            )
        if any(asset_type in type_names for asset_type in ("composition", "camera")):
            rules.append(
                {
                    "key": "composition_camera_binding",
                    "value": [
                        f"{asset_type}: {', '.join(type_names[asset_type])}"
                        for asset_type in ("composition", "camera")
                        if asset_type in type_names
                    ],
                    "reason": "composition and camera assets define framing behavior",
                }
            )
        if any(asset_type in type_names for asset_type in ("character", "scene", "prop_symbol")):
            rules.append(
                {
                    "key": "subject_scene_binding",
                    "value": [
                        f"{asset_type}: {', '.join(type_names[asset_type])}"
                        for asset_type in ("character", "scene", "prop_symbol")
                        if asset_type in type_names
                    ],
                    "reason": "subject, scene, and symbolic assets define content binding",
                }
            )
        if "mood" in type_names:
            rules.append(
                {
                    "key": "mood_tone_binding",
                    "value": type_names["mood"],
                    "reason": "mood assets constrain the recipe tone",
                }
            )
        if "negative_rule" in type_names:
            rules.append(
                {
                    "key": "negative_constraints",
                    "value": type_names["negative_rule"],
                    "reason": "negative assets should be treated as recipe-level avoid constraints",
                }
            )
        return rules

    def _generation_visual_system_candidate_payload(
        self,
        run: dict[str, Any],
        selected_assets: list[dict[str, Any]],
        batch_id: str,
    ) -> dict[str, Any]:
        asset_types = {asset["type"] for asset in selected_assets}
        if "character" in asset_types:
            system_kind = "series"
        elif "scene" in asset_types or "prop_symbol" in asset_types:
            system_kind = "worldview"
        elif {"style", "texture", "shape_line"} & asset_types:
            system_kind = "genre"
        else:
            system_kind = "art_direction"
        anchor = next((asset for asset in selected_assets if asset["type"] in {"character", "scene", "style"}), selected_assets[0])
        review = run.get("visual_review", {})
        return {
            "batch_id": batch_id,
            "kind": system_kind,
            "name": f"Generated System: {anchor['name']}",
            "summary": "Suggested from a high-value generation that shows reusable higher-level visual consistency.",
            "tags": sorted(asset_types),
            "visual_rules": self._visual_system_rules_from_sources(system_kind, selected_assets),
            "avoid_rules": [run.get("negative_prompt", "")] if run.get("negative_prompt") else [],
            "existing_asset_relations": [
                {
                    "asset_id": asset["id"],
                    "role": "core" if asset["type"] in {"style", "scene", "character", "color_palette", "composition"} else "optional",
                    "weight": 0.85 if asset["type"] in {"style", "scene", "character", "color_palette", "composition"} else 0.6,
                    "reason": "selected asset contributed to a high-value generation",
                }
                for asset in selected_assets
            ],
            "related_existing_assets": [
                {"asset_id": asset["id"], "type": asset["type"], "name": asset["name"]}
                for asset in selected_assets
            ],
            "metadata": {
                "recommendation": "suggest_create",
                "source_generation_id": run["id"],
                "source_generation_status": run.get("status"),
                "source_review_score": review.get("score"),
                "source_style_consistency": review.get("style_consistency"),
                "reason": "liked or high-scoring generation with multiple reusable selected asset types",
            },
            "status": "pending",
        }

    def _selected_asset_id(self, selected: Any) -> str:
        if isinstance(selected, str):
            return selected
        if isinstance(selected, dict):
            value = selected.get("asset_id") or selected.get("id")
            return value if isinstance(value, str) else ""
        return ""

    def _run_uses_asset(self, run: dict[str, Any], asset_id: str) -> bool:
        return any(self._selected_asset_id(selected) == asset_id for selected in run.get("selected_assets", []))

    def _record_generation_evidence(self, record: dict[str, Any]) -> None:
        selected_asset_ids = [
            self._selected_asset_id(selected)
            for selected in record.get("selected_assets", [])
            if self._selected_asset_id(selected)
        ]
        if not selected_asset_ids:
            return
        status = record.get("status")
        review = record.get("visual_review", {})
        if record.get("mode") == "edit" and status in ("edited", "liked"):
            output_evidence_type = "edited_success"
        else:
            output_evidence_type = "generated_success" if status in ("generated", "liked") else "generated_failure"
        if status in ("generated", "edited", "liked", "failed", "rejected"):
            for output in record.get("outputs", []):
                for asset_id in selected_asset_ids:
                    self.create_visual_asset_evidence(
                        asset_id,
                        {
                            "evidence_type": output_evidence_type,
                            "generation_run_id": record["id"],
                            "payload": {"output": output, "status": status},
                        },
                    )
        if isinstance(review, dict) and review:
            for asset_id in selected_asset_ids:
                self.create_visual_asset_evidence(
                    asset_id,
                    {
                        "evidence_type": "review",
                        "generation_run_id": record["id"],
                        "payload": review,
                    },
                )

    def _style_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "tags": json_loads(row["tags_json"], []),
            "source_references": json_loads(row["source_references_json"], []),
            "style_profile": json_loads(row["style_profile_json"], {}),
            "prompt_template": row["prompt_template"],
            "negative_prompt": row["negative_prompt"],
            "status": row["status"],
            "parent_style_id": row["parent_style_id"],
            "merged_into_style_id": row["merged_into_style_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _asset_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "source_path": row["source_path"],
            "asset_path": row["asset_path"],
            "sha256": row["sha256"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "created_at": row["created_at"],
        }

    def _visual_asset_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "name": row["name"],
            "summary": row["summary"],
            "tags": json_loads(row["tags_json"], []),
            "profile": json_loads(row["profile_json"], {}),
            "source_references": json_loads(row["source_references_json"], []),
            "prompt_fragments": json_loads(row["prompt_fragments_json"], []),
            "negative_fragments": json_loads(row["negative_fragments_json"], []),
            "compatible_with": json_loads(row["compatible_with_json"], []),
            "avoid_with": json_loads(row["avoid_with_json"], []),
            "recommended_aspect_ratios": json_loads(row["recommended_aspect_ratios_json"], []),
            "status": row["status"],
            "parent_asset_id": row["parent_asset_id"],
            "merged_into_asset_id": row["merged_into_asset_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _visual_asset_candidate_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "batch_id": row["batch_id"],
            "type": row["type"],
            "name": row["name"],
            "payload": json_loads(row["payload_json"], {}),
            "source_reference_ids": json_loads(row["source_reference_ids_json"], []),
            "reuse_score": row["reuse_score"],
            "decision": row["decision"],
            "similar_candidates": json_loads(row["similar_candidates_json"], []),
            "status": row["status"],
            "target_asset_id": row["target_asset_id"],
            "confirmed_asset_id": row["confirmed_asset_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _visual_asset_evidence_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "asset_id": row["asset_id"],
            "evidence_type": row["evidence_type"],
            "generation_run_id": row["generation_run_id"],
            "payload": json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }

    def _visual_system_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "name": row["name"],
            "summary": row["summary"],
            "tags": json_loads(row["tags_json"], []),
            "visual_rules": json_loads(row["visual_rules_json"], []),
            "avoid_rules": json_loads(row["avoid_rules_json"], []),
            "source_reference_ids": json_loads(row["source_reference_ids_json"], []),
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _visual_system_asset_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "system_id": row["system_id"],
            "asset_id": row["asset_id"],
            "role": row["role"],
            "weight": row["weight"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _recipe_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "parent_system_ids": json_loads(row["parent_system_ids_json"], []),
            "use_cases": json_loads(row["use_cases_json"], []),
            "required_asset_types": json_loads(row["required_asset_types_json"], []),
            "composition_rules": json_loads(row["composition_rules_json"], []),
            "recommended_aspect_ratios": json_loads(row["recommended_aspect_ratios_json"], []),
            "source_reference_ids": json_loads(row["source_reference_ids_json"], []),
            "confidence": row["confidence"],
            "source": row["source"],
            "reason": row["reason"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _recipe_asset_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "recipe_id": row["recipe_id"],
            "asset_id": row["asset_id"],
            "role": row["role"],
            "weight": row["weight"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _recipe_candidate_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "batch_id": row["batch_id"],
            "payload": json_loads(row["payload_json"], {}),
            "status": row["status"],
            "confirmed_recipe_id": row["confirmed_recipe_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _visual_system_candidate_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "batch_id": row["batch_id"],
            "payload": json_loads(row["payload_json"], {}),
            "status": row["status"],
            "confirmed_system_id": row["confirmed_system_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _generation_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "mode": row["mode"],
            "source_prompt": row["source_prompt"],
            "refined_prompt": row["refined_prompt"],
            "negative_prompt": row["negative_prompt"],
            "source_generation_id": row["source_generation_id"],
            "source_output_asset_id": row["source_output_asset_id"],
            "edit_instruction": row["edit_instruction"],
            "edit_regions": json_loads(row["edit_regions_json"], []),
            "style_id": row["style_id"],
            "selected_assets": json_loads(row["selected_assets_json"], []),
            "generation_skill": row["generation_skill"],
            "skill_params": json_loads(row["skill_params_json"], {}),
            "skill_result_meta": json_loads(row["skill_result_meta_json"], {}),
            "visual_review": json_loads(row["visual_review_json"], {}),
            "outputs": json_loads(row["outputs_json"], []),
            "status": row["status"],
            "feedback": json_loads(row["feedback_json"], {}),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

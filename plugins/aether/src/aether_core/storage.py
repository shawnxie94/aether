from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .embeddings import (
    chunk_texts,
    content_hash,
    cosine_similarity,
    embed_with_retry,
    provider_from_config,
)
from .ids import new_id, slugify
from .jsonio import json_dumps, json_loads
from .migrations import run_migrations
from .recall import canonical_text, lexical_similarity, token_set, weighted_score
from .storage_time import now_iso
from .validation import (
    validate_generation_run,
    validate_prompt_record,
    validate_recipe,
    validate_recipe_asset,
    validate_recipe_candidate,
    validate_visual_system,
    validate_visual_system_candidate,
    validate_asset_relation,
    validate_visual_asset,
    validate_visual_asset_candidate,
)


class AetherStore:
    NON_RECALLABLE_STATUSES = {"archived", "deprecated", "merged"}
    COMPACT_TEXT_LIMIT = 520

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def connect(self):
        """Yield a sqlite3 connection, committing on clean exit.

        This is a generator-based context manager, not a raw
        ``sqlite3.Connection`` wrapper. Two reasons:

        1. CPython 3.14's ``sqlite3.Connection.close()`` does NOT auto-commit
           pending transactions. ``Connection.__exit__`` does (it calls
           ``commit()`` then ``close()``), but a plain ``close()`` rolls them
           back. We have to commit explicitly to keep behaviour consistent
           with the old ``with self.connect() as conn:`` call sites.
        2. It lets us drop the local connection binding inside ``finally`` so
           CPython's finalizer recognises the connection as fully cleaned up,
           which silences the false-positive ``ResourceWarning: unclosed
           database`` reported during interpreter shutdown.
        """
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except BaseException:
            # An exception is unwinding the with-block. Roll back any pending
            # write and re-raise so the caller sees the original error.
            try:
                if conn.in_transaction:
                    conn.rollback()
            except sqlite3.ProgrammingError:
                pass
            raise
        else:
            # No exception: commit pending writes before closing. Without
            # this, CPython 3.14 drops the transaction on close.
            try:
                conn.commit()
            except sqlite3.ProgrammingError:
                # Connection was already closed by a caller; safe to ignore.
                pass
        finally:
            try:
                conn.close()
            except sqlite3.ProgrammingError:
                # Already closed; nothing left to do.
                pass
            del conn

    def __del__(self) -> None:  # pragma: no cover - defensive only
        """Last-resort hook for any leaked sqlite3 connection.

        ``connect()`` is a context manager that always commits and closes on
        ``__exit__``, so this ``__del__`` should normally be a no-op. It
        exists so that if a future caller bypasses the context manager
        (e.g. stores a raw connection and drops the reference), the
        interpreter's finalizer still flushes the underlying handle.
        """
        return None

    def _truncate_text(self, value: str, limit: int | None = None) -> str:
        limit = limit or self.COMPACT_TEXT_LIMIT
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)].rstrip() + "..."

    def _compact_json_value(self, value: Any, *, depth: int = 0, list_limit: int = 8) -> Any:
        if isinstance(value, str):
            return self._truncate_text(value)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if depth >= 4:
            return self._truncate_text(json_dumps(value), limit=240)
        if isinstance(value, list):
            compacted = [self._compact_json_value(item, depth=depth + 1, list_limit=list_limit) for item in value[:list_limit]]
            if len(value) > list_limit:
                compacted.append({"omitted_count": len(value) - list_limit})
            return compacted
        if isinstance(value, dict):
            return {
                str(key): self._compact_json_value(item, depth=depth + 1, list_limit=list_limit)
                for key, item in value.items()
                if item not in (None, "", [], {})
            }
        return self._truncate_text(str(value))

    def _compact_recall_item(self, item: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "entity_type",
            "entity_id",
            "asset_id",
            "system_id",
            "recipe_id",
            "type",
            "kind",
            "name",
            "score",
            "semantic_score",
            "lexical_score",
            "relation_score",
            "quality_score",
            "matched_terms",
            "parent_system_ids",
            "family_key",
        )
        compacted = {key: item[key] for key in keys if key in item and item[key] not in (None, "", [], {})}
        if "matched_terms" in compacted and isinstance(compacted["matched_terms"], list):
            compacted["matched_terms"] = compacted["matched_terms"][:8]
        if item.get("provider_error"):
            compacted["provider_error"] = self._truncate_text(str(item["provider_error"]), limit=160)
        return compacted

    def compact_recall_candidates(self, recall: dict[str, Any], *, include_raw: bool = False) -> dict[str, Any]:
        if not isinstance(recall, dict):
            return {}
        compacted: dict[str, Any] = {}
        for key in ("visual_systems", "recipes", "visual_assets"):
            values = recall.get(key, [])
            if isinstance(values, list):
                compacted[key] = [self._compact_recall_item(item) for item in values[:5] if isinstance(item, dict)]
                if len(values) > 5:
                    compacted[f"{key}_omitted_count"] = len(values) - 5
        raw = recall.get("visual_assets_raw", [])
        if include_raw and isinstance(raw, list):
            compacted["visual_assets_raw"] = [self._compact_recall_item(item) for item in raw[:8] if isinstance(item, dict)]
            if len(raw) > 8:
                compacted["visual_assets_raw_omitted_count"] = len(raw) - 8
        elif isinstance(raw, list) and raw:
            compacted["visual_assets_raw_count"] = len(raw)
        elif recall.get("visual_assets_raw_count"):
            compacted["visual_assets_raw_count"] = recall["visual_assets_raw_count"]
        return {key: value for key, value in compacted.items() if value not in (None, "", [], {})}

    def _compact_selected_asset(self, asset: Any) -> Any:
        if not isinstance(asset, dict):
            return asset
        keys = ("type", "asset_id", "id", "name", "reason")
        return {key: self._compact_json_value(asset[key]) for key in keys if key in asset and asset[key] not in (None, "", [], {})}

    def _compact_selected_system(self, system: Any) -> Any:
        if not isinstance(system, dict):
            return system
        keys = ("system_id", "kind", "name", "reason", "recall")
        compacted = {key: self._compact_json_value(system[key]) for key in keys if key in system and system[key] not in (None, "", [], {})}
        if "visual_rules" in system:
            compacted["visual_rule_count"] = len(system.get("visual_rules") or [])
        if "avoid_rules" in system:
            compacted["avoid_rule_count"] = len(system.get("avoid_rules") or [])
        return compacted

    def _compact_selected_recipe(self, recipe: Any) -> Any:
        if not isinstance(recipe, dict):
            return recipe
        keys = ("recipe_id", "name", "reason", "recommended_aspect_ratios", "recall")
        compacted = {key: self._compact_json_value(recipe[key]) for key in keys if key in recipe and recipe[key] not in (None, "", [], {})}
        if "composition_rules" in recipe:
            compacted["composition_rule_count"] = len(recipe.get("composition_rules") or [])
        return compacted

    def _compact_composition_plan(self, plan: Any) -> Any:
        if not isinstance(plan, dict):
            return self._compact_json_value(plan)
        compacted = dict(plan)
        if isinstance(compacted.get("visual_systems"), list):
            compacted["visual_systems"] = [self._compact_selected_system(item) for item in compacted["visual_systems"]]
        if isinstance(compacted.get("recipes"), list):
            compacted["recipes"] = [self._compact_selected_recipe(item) for item in compacted["recipes"]]
        return self._compact_json_value(compacted)

    def compact_prompt_record_payload(self, payload: dict[str, Any], *, include_debug_recall: bool = False) -> dict[str, Any]:
        compacted = dict(payload)
        selected_assets = compacted.get("selected_assets")
        if isinstance(selected_assets, list):
            compacted["selected_assets"] = [self._compact_selected_asset(asset) for asset in selected_assets]
        constraints = compacted.get("constraints")
        if isinstance(constraints, dict):
            compact_constraints = dict(constraints)
            for key, compact_func in (
                ("selected_assets", self._compact_selected_asset),
                ("selected_systems", self._compact_selected_system),
                ("selected_recipes", self._compact_selected_recipe),
            ):
                if isinstance(compact_constraints.get(key), list):
                    compact_constraints[key] = [compact_func(item) for item in compact_constraints[key]]
            if isinstance(compact_constraints.get("conflicts"), list):
                compact_constraints["conflicts"] = self._compact_json_value(compact_constraints["conflicts"], list_limit=6)
            compacted["constraints"] = compact_constraints
        if isinstance(compacted.get("intent_analysis"), dict):
            intent = dict(compacted["intent_analysis"])
            for key in ("prompt_terms", "query_terms"):
                if isinstance(intent.get(key), list):
                    terms = intent[key]
                    intent[key] = terms[:32]
                    if len(terms) > 32:
                        intent[f"{key}_omitted_count"] = len(terms) - 32
            compacted["intent_analysis"] = intent
        if isinstance(compacted.get("recall_candidates"), dict):
            compacted["recall_candidates"] = self.compact_recall_candidates(
                compacted["recall_candidates"],
                include_raw=include_debug_recall,
            )
        for key in ("intent_sketch", "generation_params", "assumptions", "conflicts"):
            if key in compacted:
                compacted[key] = self._compact_json_value(compacted[key])
        if "composition_plan" in compacted:
            compacted["composition_plan"] = self._compact_composition_plan(compacted["composition_plan"])
        if isinstance(compacted.get("variants"), list):
            variants = []
            for variant in compacted["variants"]:
                if not isinstance(variant, dict):
                    variants.append(self._compact_json_value(variant))
                    continue
                compact_variant = dict(variant)
                for key in ("composition_plan", "selected_assets", "notes"):
                    if key in compact_variant:
                        compact_variant[key] = self._compact_json_value(compact_variant[key])
                variants.append(compact_variant)
            compacted["variants"] = variants
        return compacted

    def prompt_context_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record.get("id"),
            "source_prompt": record.get("source_prompt", ""),
            "target_generation_skill": record.get("target_generation_skill"),
            "selected_assets": record.get("selected_assets", []),
            "refined_prompt": record.get("refined_prompt", ""),
            "negative_prompt": record.get("negative_prompt", ""),
            "generation_params": record.get("generation_params", {}),
            "variant_count": len(record.get("variants", [])),
            "assumptions": record.get("assumptions", []),
            "conflict_count": len(record.get("conflicts", [])),
            "created_at": record.get("created_at"),
        }

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
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
                  decision text not null default 'create_new',
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
                  source_candidate_id text,
                  source_reference_id text,
                  payload_json text not null default '{}',
                  created_at text not null
                );

                create table if not exists visual_asset_revisions (
                  id text primary key,
                  asset_id text not null,
                  action text not null,
                  source_candidate_id text,
                  source_generation_id text,
                  target_entity_id text,
                  scores_json text not null default '{}',
                  before_json text not null default '{}',
                  after_json text not null default '{}',
                  diff_json text not null default '{}',
                  reason text not null default '',
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
                  parent_system_id text,
                  merged_into_system_id text,
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
                  metadata_json text not null default '{}',
                  status text not null default 'draft',
                  parent_recipe_id text,
                  merged_into_recipe_id text,
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

                create table if not exists panel_favorites (
                  entity_type text not null,
                  entity_id text not null,
                  created_at text not null,
                  primary key(entity_type, entity_id)
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

                create table if not exists recipe_evidence (
                  id text primary key,
                  recipe_id text not null,
                  evidence_type text not null,
                  source_candidate_id text,
                  source_generation_id text,
                  source_reference_id text,
                  payload_json text not null default '{}',
                  created_at text not null
                );

                create table if not exists visual_system_evidence (
                  id text primary key,
                  system_id text not null,
                  evidence_type text not null,
                  source_candidate_id text,
                  source_generation_id text,
                  source_reference_id text,
                  payload_json text not null default '{}',
                  created_at text not null
                );

                create table if not exists recipe_revisions (
                  id text primary key,
                  recipe_id text not null,
                  action text not null,
                  source_candidate_id text,
                  source_generation_id text,
                  target_entity_id text,
                  scores_json text not null default '{}',
                  before_json text not null default '{}',
                  after_json text not null default '{}',
                  diff_json text not null default '{}',
                  reason text not null default '',
                  created_at text not null
                );

                create table if not exists visual_system_revisions (
                  id text primary key,
                  system_id text not null,
                  action text not null,
                  source_candidate_id text,
                  source_generation_id text,
                  target_entity_id text,
                  scores_json text not null default '{}',
                  before_json text not null default '{}',
                  after_json text not null default '{}',
                  diff_json text not null default '{}',
                  reason text not null default '',
                  created_at text not null
                );

                create table if not exists prompt_records (
                  id text primary key,
                  source_prompt text not null,
                  style_id text,
                  target_generation_skill text,
                  selected_assets_json text not null default '[]',
                  constraints_json text not null default '{}',
                  intent_analysis_json text not null default '{}',
                  intent_sketch_json text not null default '{}',
                  recall_candidates_json text not null default '{}',
                  recall_strategy_json text not null default '{}',
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

                create table if not exists embeddings (
                  id text primary key,
                  entity_type text not null,
                  entity_id text not null,
                  content_hash text not null,
                  provider text not null,
                  model text not null,
                  dimensions integer not null,
                  vector_json text not null,
                  created_at text not null,
                  updated_at text not null,
                  unique(entity_type, entity_id, provider, model, dimensions)
                );

                create index if not exists idx_embeddings_entity
                  on embeddings(entity_type, entity_id);

                create index if not exists idx_embeddings_model
                  on embeddings(provider, model, dimensions);
                """
            )
            run_migrations(conn)

    def list_panel_favorites(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        sql = "select * from panel_favorites"
        params: list[Any] = []
        if entity_type:
            sql += " where entity_type = ?"
            params.append(entity_type)
        sql += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def is_panel_favorite(self, entity_type: str, entity_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "select 1 from panel_favorites where entity_type = ? and entity_id = ?",
                (entity_type, entity_id),
            ).fetchone()
        return row is not None

    def set_panel_favorite(self, entity_type: str, entity_id: str, favorite: bool) -> dict[str, Any]:
        if entity_type not in {"recipe", "visual_system"}:
            raise ValueError(f"Unsupported favorite entity type: {entity_type}")
        timestamp = now_iso()
        with self.connect() as conn:
            if favorite:
                conn.execute(
                    """
                    insert into panel_favorites (entity_type, entity_id, created_at)
                    values (?, ?, ?)
                    on conflict(entity_type, entity_id) do nothing
                    """,
                    (entity_type, entity_id, timestamp),
                )
            else:
                conn.execute(
                    "delete from panel_favorites where entity_type = ? and entity_id = ?",
                    (entity_type, entity_id),
                )
        return {"entity_type": entity_type, "entity_id": entity_id, "favorite": favorite}

    def create_visual_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_visual_asset(payload)
        timestamp = now_iso()
        asset_id = payload.get("id") or self._unique_slug_id(
            "visual_assets",
            slugify(f"{payload['type']}-{payload['name']}", "visual_asset"),
        )
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

    def canonical_entity_text(self, entity_type: str, entity: dict[str, Any]) -> str:
        if entity_type == "visual_asset":
            return canonical_text(
                [
                    entity.get("type"),
                    entity.get("name"),
                    entity.get("summary"),
                    entity.get("tags"),
                    entity.get("profile"),
                    entity.get("prompt_fragments"),
                    entity.get("negative_fragments"),
                    entity.get("compatible_with"),
                    entity.get("avoid_with"),
                ]
            )
        if entity_type == "visual_system":
            related_assets = []
            for relation in entity.get("assets", []):
                asset = self.get_visual_asset(relation["asset_id"])
                if asset:
                    related_assets.append(
                        {
                            "role": relation.get("role"),
                            "weight": relation.get("weight"),
                            "reason": relation.get("reason"),
                            "asset": {
                                "type": asset.get("type"),
                                "name": asset.get("name"),
                                "summary": asset.get("summary"),
                                "tags": asset.get("tags"),
                            },
                        }
                    )
            return canonical_text(
                [
                    entity.get("kind"),
                    entity.get("name"),
                    entity.get("summary"),
                    entity.get("tags"),
                    entity.get("visual_rules"),
                    entity.get("avoid_rules"),
                    related_assets,
                ]
            )
        if entity_type == "recipe":
            parent_systems = [
                self.get_visual_system(system_id, include_assets=False)
                for system_id in entity.get("parent_system_ids", [])
            ]
            related_assets = []
            for relation in entity.get("assets", []):
                asset = self.get_visual_asset(relation["asset_id"])
                if asset:
                    related_assets.append(
                        {
                            "role": relation.get("role"),
                            "weight": relation.get("weight"),
                            "reason": relation.get("reason"),
                            "asset": {
                                "type": asset.get("type"),
                                "name": asset.get("name"),
                                "summary": asset.get("summary"),
                                "tags": asset.get("tags"),
                            },
                        }
                    )
            return canonical_text(
                [
                    entity.get("name"),
                    entity.get("summary"),
                    entity.get("use_cases"),
                    entity.get("required_asset_types"),
                    entity.get("composition_rules"),
                    entity.get("recommended_aspect_ratios"),
                    [
                        {
                            "kind": system.get("kind"),
                            "name": system.get("name"),
                            "summary": system.get("summary"),
                            "tags": system.get("tags"),
                        }
                        for system in parent_systems
                        if system
                    ],
                    related_assets,
                ]
            )
        raise ValueError(f"Unsupported canonical entity type: {entity_type}")

    def _entities_for_recall(
        self,
        entity_type: str,
        status: str | None = "active",
        *,
        include_unavailable: bool = False,
    ) -> list[dict[str, Any]]:
        if entity_type == "visual_asset":
            entities = self.list_visual_assets(status=status, limit=None)
            return self._filter_recallable_entities(entity_type, entities, include_unavailable=include_unavailable)
        if entity_type == "visual_system":
            entities = [
                self.get_visual_system(system["id"]) or system
                for system in self.list_visual_systems(status=status, limit=None)
            ]
            return self._filter_recallable_entities(entity_type, entities, include_unavailable=include_unavailable)
        if entity_type == "recipe":
            entities = [
                self.get_recipe(recipe["id"]) or recipe
                for recipe in self.list_recipes(status=status, limit=None)
            ]
            return self._filter_recallable_entities(entity_type, entities, include_unavailable=include_unavailable)
        raise ValueError(f"Unsupported recall entity type: {entity_type}")

    def _filter_recallable_entities(
        self,
        entity_type: str,
        entities: list[dict[str, Any]],
        *,
        include_unavailable: bool = False,
    ) -> list[dict[str, Any]]:
        if include_unavailable:
            return entities
        return [entity for entity in entities if self._is_recallable_entity(entity_type, entity)]

    def _is_recallable_entity(self, entity_type: str, entity: dict[str, Any]) -> bool:
        if entity.get("status") in self.NON_RECALLABLE_STATUSES:
            return False
        merged_field = {
            "visual_asset": "merged_into_asset_id",
            "visual_system": "merged_into_system_id",
            "recipe": "merged_into_recipe_id",
        }[entity_type]
        return not entity.get(merged_field)

    def _entity_id(self, entity_type: str, entity: dict[str, Any]) -> str:
        if entity_type not in {"visual_asset", "visual_system", "recipe"}:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return entity["id"]

    def _entity_quality_score(self, entity_type: str, entity: dict[str, Any]) -> float:
        if entity_type == "visual_asset":
            return float(self.visual_asset_quality(entity["id"])["score"])
        asset_ids: list[str] = []
        if entity_type == "visual_system":
            asset_ids = [relation["asset_id"] for relation in entity.get("assets", [])]
        elif entity_type == "recipe":
            asset_ids = [relation["asset_id"] for relation in entity.get("assets", [])]
        scores = [float(self.visual_asset_quality(asset_id)["score"]) for asset_id in asset_ids]
        return round(sum(scores) / len(scores), 4) if scores else 0.5

    def _entity_relation_score(
        self,
        entity_type: str,
        entity: dict[str, Any],
        *,
        related_asset_ids: list[str] | None = None,
        parent_system_ids: list[str] | None = None,
    ) -> float:
        related = set(related_asset_ids or [])
        parents = set(parent_system_ids or [])
        if entity_type == "visual_asset":
            return 1.0 if entity["id"] in related else 0.0
        if entity_type == "visual_system":
            system_asset_ids = {relation["asset_id"] for relation in entity.get("assets", [])}
            relation = len(system_asset_ids & related) / len(related) if related else 0.0
            parent = 1.0 if entity["id"] in parents else 0.0
            return max(relation, parent)
        if entity_type == "recipe":
            recipe_asset_ids = {relation["asset_id"] for relation in entity.get("assets", [])}
            asset_relation = len(recipe_asset_ids & related) / len(related) if related else 0.0
            parent_relation = 1.0 if parents & set(entity.get("parent_system_ids", [])) else 0.0
            return max(asset_relation, parent_relation)
        return 0.0

    def _embedding_row(
        self,
        entity_type: str,
        entity_id: str,
        provider: str,
        model: str,
        dimensions: int,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            if dimensions:
                row = conn.execute(
                    """
                    select * from embeddings
                    where entity_type = ? and entity_id = ? and provider = ? and model = ? and dimensions = ?
                    """,
                    (entity_type, entity_id, provider, model, dimensions),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    select * from embeddings
                    where entity_type = ? and entity_id = ? and provider = ? and model = ?
                    order by updated_at desc
                    """,
                    (entity_type, entity_id, provider, model),
                ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "content_hash": row["content_hash"],
            "provider": row["provider"],
            "model": row["model"],
            "dimensions": row["dimensions"],
            "vector": json_loads(row["vector_json"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def upsert_embedding(
        self,
        entity_type: str,
        entity_id: str,
        text: str,
        vector: list[float],
        provider: str,
        model: str,
        dimensions: int,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": new_id("embedding"),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "content_hash": content_hash(text),
            "provider": provider,
            "model": model,
            "dimensions": dimensions or len(vector),
            "vector": vector,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into embeddings (
                  id, entity_type, entity_id, content_hash, provider, model, dimensions,
                  vector_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(entity_type, entity_id, provider, model, dimensions) do update set
                  content_hash=excluded.content_hash,
                  vector_json=excluded.vector_json,
                  updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["entity_type"],
                    record["entity_id"],
                    record["content_hash"],
                    record["provider"],
                    record["model"],
                    record["dimensions"],
                    json_dumps(record["vector"]),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def embedding_status(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            provider = provider_from_config(config)
            provider_error = ""
        except RuntimeError as exc:
            provider = None
            provider_error = str(exc)
        rows_by_entity: dict[str, int] = {}
        with self.connect() as conn:
            rows = conn.execute("select entity_type, count(*) as count from embeddings group by entity_type").fetchall()
        for row in rows:
            rows_by_entity[row["entity_type"]] = row["count"]
        entity_counts = {
            "visual_asset": len(self.list_visual_assets(limit=None)),
            "visual_system": len(self.list_visual_systems(limit=None)),
            "recipe": len(self.list_recipes(limit=None)),
        }
        index_health: dict[str, dict[str, int]] = {}
        if provider and provider.provider_name != "disabled":
            for entity_type in ("visual_asset", "visual_system", "recipe"):
                current = 0
                stale = 0
                missing = 0
                for entity in self._entities_for_recall(entity_type, status=None, include_unavailable=True):
                    entity_id = self._entity_id(entity_type, entity)
                    text = self.canonical_entity_text(entity_type, entity)
                    existing = self._embedding_row(
                        entity_type,
                        entity_id,
                        provider.provider_name,
                        provider.model,
                        provider.dimensions,
                    )
                    if not existing:
                        missing += 1
                    elif existing["content_hash"] == content_hash(text):
                        current += 1
                    else:
                        stale += 1
                index_health[entity_type] = {
                    "current": current,
                    "stale": stale,
                    "missing": missing,
                }
        return {
            "provider": getattr(provider, "provider_name", "unavailable") if provider else "unavailable",
            "model": getattr(provider, "model", "") if provider else "",
            "dimensions": getattr(provider, "dimensions", 0) if provider else 0,
            "provider_error": provider_error,
            "entity_counts": entity_counts,
            "indexed_counts": rows_by_entity,
            "index_health": index_health,
            "needs_rebuild": any(
                health["stale"] > 0 or health["missing"] > 0
                for health in index_health.values()
            ),
        }

    def index_embeddings(
        self,
        config: dict[str, Any] | None = None,
        entity_type: str | None = None,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        provider = provider_from_config(config)
        if provider.provider_name == "disabled":
            return {
                "indexed": [],
                "skipped": [{"reason": "embedding provider disabled"}],
                "provider": provider.provider_name,
                "model": provider.model,
                "dimensions": provider.dimensions,
            }
        entity_types = [entity_type] if entity_type else ["visual_asset", "visual_system", "recipe"]
        to_embed: list[tuple[str, str, str]] = []
        skipped: list[dict[str, Any]] = []
        for current_type in entity_types:
            for entity in self._entities_for_recall(current_type, status=None, include_unavailable=True):
                entity_id = self._entity_id(current_type, entity)
                text = self.canonical_entity_text(current_type, entity)
                text_hash = content_hash(text)
                existing = self._embedding_row(
                    current_type,
                    entity_id,
                    provider.provider_name,
                    provider.model,
                    provider.dimensions,
                )
                if existing and existing["content_hash"] == text_hash and not rebuild:
                    skipped.append({"entity_type": current_type, "entity_id": entity_id, "reason": "unchanged"})
                    continue
                to_embed.append((current_type, entity_id, text))
        vectors = self._embed_batches(provider, [item[2] for item in to_embed], config)
        indexed = [
            self.upsert_embedding(
                current_type,
                entity_id,
                text,
                vector,
                provider.provider_name,
                provider.model,
                provider.dimensions or len(vector),
            )
            for (current_type, entity_id, text), vector in zip(to_embed, vectors)
        ]
        return {
            "indexed": indexed,
            "skipped": skipped,
            "provider": provider.provider_name,
            "model": provider.model,
            "dimensions": provider.dimensions,
        }

    def _embed_batches(
        self,
        provider: Any,
        texts: list[str],
        config: dict[str, Any] | None,
    ) -> list[list[float]]:
        """Embed ``texts`` in chunks with retry on transient errors.

        The chunk size is read from ``config['embedding']['batchSize']`` and
        defaults to 32. Each chunk is sent through ``embed_with_retry`` so a
        single 429 or 5xx does not abort the whole rebuild. A chunk that
        exhausts its retries is logged and skipped; the surrounding chunks
        still complete so partial progress survives flaky networks.
        """
        if not texts:
            return []
        batch_size = 32
        if isinstance(config, dict):
            raw = config.get("embedding", {}).get("batchSize")
            try:
                if raw is not None and int(raw) > 0:
                    batch_size = int(raw)
            except (TypeError, ValueError):
                pass
        vectors: list[list[float]] = []
        for batch in chunk_texts(texts, batch_size=batch_size):
            try:
                vectors.extend(
                    embed_with_retry(provider.embed_texts, batch)
                )
            except RuntimeError:
                # Skip the failed batch; partial index is better than no
                # index when the provider is flaky. The next rebuild will
                # retry the same rows because their content_hash no longer
                # matches what is stored in ``embeddings``.
                continue
        return vectors

    def hybrid_recall(
        self,
        entity_type: str,
        query_text: str,
        *,
        config: dict[str, Any] | None = None,
        limit: int = 5,
        status: str | None = "active",
        related_asset_ids: list[str] | None = None,
        parent_system_ids: list[str] | None = None,
        min_score: float = 0.0,
        include_unavailable: bool = False,
    ) -> list[dict[str, Any]]:
        provider = None
        query_vector: list[float] | None = None
        provider_error = ""
        try:
            provider = provider_from_config(config)
            if provider.provider_name != "disabled" and query_text:
                query_vector = provider.embed_texts([query_text])[0]
        except RuntimeError as exc:
            provider_error = str(exc)
            provider = None

        results: list[dict[str, Any]] = []
        recall_status = None if include_unavailable else status
        for entity in self._entities_for_recall(
            entity_type,
            status=recall_status,
            include_unavailable=include_unavailable,
        ):
            entity_id = self._entity_id(entity_type, entity)
            text = self.canonical_entity_text(entity_type, entity)
            lexical_score, matched_terms = lexical_similarity(query_text, text)
            semantic_score = 0.0
            if provider and query_vector is not None:
                existing = self._embedding_row(
                    entity_type,
                    entity_id,
                    provider.provider_name,
                    provider.model,
                    provider.dimensions,
                )
                if existing and existing["content_hash"] == content_hash(text):
                    semantic_score = max(0.0, cosine_similarity(query_vector, existing["vector"]))
            relation_score = self._entity_relation_score(
                entity_type,
                entity,
                related_asset_ids=related_asset_ids,
                parent_system_ids=parent_system_ids,
            )
            quality_score = self._entity_quality_score(entity_type, entity)
            score = weighted_score(
                semantic_score=semantic_score,
                lexical_score=lexical_score,
                relation_score=relation_score,
                quality_score=quality_score,
            )
            if score <= min_score and lexical_score <= 0 and semantic_score <= 0 and relation_score <= 0:
                continue
            result = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "name": entity.get("name"),
                "score": score,
                "semantic_score": round(semantic_score, 4),
                "lexical_score": round(lexical_score, 4),
                "relation_score": round(relation_score, 4),
                "quality_score": round(quality_score, 4),
                "matched_terms": matched_terms,
                "provider_error": provider_error,
            }
            if include_unavailable:
                result["status"] = entity.get("status")
            if entity_type == "visual_asset":
                result["asset_id"] = entity_id
                result["type"] = entity.get("type")
                if include_unavailable:
                    result["merged_into_asset_id"] = entity.get("merged_into_asset_id")
            elif entity_type == "visual_system":
                result["system_id"] = entity_id
                result["kind"] = entity.get("kind")
                if include_unavailable:
                    result["merged_into_system_id"] = entity.get("merged_into_system_id")
            elif entity_type == "recipe":
                result["recipe_id"] = entity_id
                result["parent_system_ids"] = entity.get("parent_system_ids", [])
                if include_unavailable:
                    result["merged_into_recipe_id"] = entity.get("merged_into_recipe_id")
            results.append(result)
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def _candidate_novelty_score(self, query_text: str, target_text: str) -> float:
        query_tokens = token_set(query_text)
        if not query_tokens:
            return 0.0
        target_tokens = token_set(target_text)
        new_tokens = query_tokens - target_tokens
        return round(len(new_tokens) / len(query_tokens), 4)

    def _evolution_scores(
        self,
        entity_type: str,
        query_text: str,
        top: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not top:
            return {
                "hybrid_similarity": 0.0,
                "semantic_score": 0.0,
                "lexical_score": 0.0,
                "relation_score": 0.0,
                "quality_score": 0.0,
                "novelty_score": 1.0 if query_text else 0.0,
                "conflict_score": 0.0,
                "scope_match": False,
            }
        entity_id = top.get("entity_id") or top.get("asset_id") or top.get("system_id") or top.get("recipe_id")
        target: dict[str, Any] | None = None
        if entity_type == "visual_asset" and entity_id:
            target = self.get_visual_asset(entity_id)
        elif entity_type == "visual_system" and entity_id:
            target = self.get_visual_system(entity_id)
        elif entity_type == "recipe" and entity_id:
            target = self.get_recipe(entity_id)
        target_text = self.canonical_entity_text(entity_type, target) if target else ""
        return {
            "hybrid_similarity": round(float(top.get("score", top.get("similarity_score", 0.0))), 4),
            "semantic_score": round(float(top.get("semantic_score", 0.0)), 4),
            "lexical_score": round(float(top.get("lexical_score", 0.0)), 4),
            "relation_score": round(float(top.get("relation_score", 0.0)), 4),
            "quality_score": round(float(top.get("quality_score", 0.0)), 4),
            "novelty_score": self._candidate_novelty_score(query_text, target_text),
            "conflict_score": 0.0,
            "scope_match": bool(target),
        }

    def _evolution_action(self, entity_type: str, scores: dict[str, Any]) -> str:
        similarity = float(scores.get("hybrid_similarity", 0.0))
        semantic = float(scores.get("semantic_score", 0.0))
        lexical = float(scores.get("lexical_score", 0.0))
        relation = float(scores.get("relation_score", 0.0))
        novelty = float(scores.get("novelty_score", 1.0))
        comparable_score = max(similarity, semantic, lexical, relation)
        if entity_type == "visual_asset":
            if semantic >= 0.95:
                return "attach_evidence"
            if comparable_score >= 0.88 and novelty < 0.35:
                return "attach_evidence"
            if comparable_score >= 0.72:
                return "inherit_variant" if novelty >= 0.25 else "attach_evidence"
            if comparable_score >= 0.55:
                return "inherit_variant"
            return "create_new"
        if entity_type == "recipe":
            if semantic >= 0.95:
                return "attach_evidence"
            if comparable_score >= 0.86 and novelty < 0.25:
                return "attach_evidence"
            if comparable_score >= 0.72:
                return "inherit_variant" if novelty >= 0.25 else "attach_evidence"
            if comparable_score >= 0.58:
                return "inherit_variant"
            return "create_new"
        if entity_type == "visual_system":
            if semantic >= 0.95:
                return "attach_evidence"
            if comparable_score >= 0.86 and novelty < 0.25:
                return "attach_evidence"
            if comparable_score >= 0.72:
                return "inherit_variant" if novelty >= 0.25 else "attach_evidence"
            if comparable_score >= 0.58:
                return "inherit_variant"
            return "create_new"
        raise ValueError(f"Unsupported evolution entity type: {entity_type}")

    def _evolution_suggestion(
        self,
        entity_type: str,
        query_text: str,
        top: dict[str, Any] | None,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        scores = self._evolution_scores(entity_type, query_text, top)
        action = self._evolution_action(entity_type, scores)
        target_id = None
        if top:
            target_id = top.get("entity_id") or top.get("asset_id") or top.get("system_id") or top.get("recipe_id")
        return {
            "action": action,
            "target_id": target_id,
            "confidence": round(max(float(scores.get("hybrid_similarity", 0.0)), float(scores.get("semantic_score", 0.0))), 4),
            "scores": scores,
            "reason": reason or self._evolution_reason(entity_type, action, scores),
            "requires_user_confirmation": action in {"create_new", "inherit_variant", "merge_existing"},
        }

    def _evolution_reason(self, entity_type: str, action: str, scores: dict[str, Any]) -> str:
        similarity = scores.get("hybrid_similarity", 0.0)
        novelty = scores.get("novelty_score", 0.0)
        labels = {
            "create_new": "Create new",
            "attach_evidence": "Attach evidence",
            "inherit_variant": "Inherit variant",
            "merge_existing": "Merge existing",
            "needs_review": "Needs review",
        }
        return f"{labels.get(action, action)} suggested for {entity_type}; similarity={similarity}, novelty={novelty}."

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

    def _compact_unique(self, values: list[Any], limit: int = 12) -> list[Any]:
        seen: set[str] = set()
        compacted = []
        for value in values:
            key = json_dumps(value) if isinstance(value, (dict, list)) else str(value)
            if not key or key in seen:
                continue
            seen.add(key)
            compacted.append(value)
            if len(compacted) >= limit:
                break
        return compacted

    def _abstract_text(self, values: list[str], limit: int = 420) -> str:
        candidates = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if not candidates:
            return ""
        if candidates[0] in candidates[1:]:
            return candidates[0]
        text = " / ".join(dict.fromkeys(candidates))
        return text[:limit].rstrip()

    def _abstract_mapping(self, primary: dict[str, Any], secondary: dict[str, Any], limit: int = 4) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in [*primary.keys(), *secondary.keys()]:
            if key in merged:
                continue
            left = primary.get(key)
            right = secondary.get(key)
            if left == right or right in (None, "", [], {}):
                merged[key] = left
            elif left in (None, "", [], {}):
                merged[key] = right
            elif isinstance(left, list) or isinstance(right, list):
                left_values = left if isinstance(left, list) else [left]
                right_values = right if isinstance(right, list) else [right]
                merged[key] = self._compact_unique([*left_values, *right_values], limit=limit)
            else:
                merged[key] = self._compact_unique([left, right], limit=limit)
        return merged

    def _abstract_rules(self, primary: list[dict[str, Any]], secondary: list[dict[str, Any]], limit_per_key: int = 5) -> list[dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for rule in [*primary, *secondary]:
            if not isinstance(rule, dict) or not rule.get("key"):
                continue
            key = rule["key"]
            existing = by_key.setdefault(key, {"key": key, "value": [], "reason": ""})
            existing["value"] = self._compact_unique(
                [*existing.get("value", []), *rule.get("value", [])],
                limit=limit_per_key,
            )
            reason = rule.get("reason", "")
            if reason and reason not in existing.get("reason", ""):
                existing["reason"] = self._abstract_text([existing.get("reason", ""), reason], limit=220)
        return list(by_key.values())

    def _merge_preview(
        self,
        entity_type: str,
        source: dict[str, Any],
        target: dict[str, Any],
        proposed: dict[str, Any],
    ) -> dict[str, Any]:
        diff = {
            key: {"before": target.get(key), "after": proposed.get(key)}
            for key in proposed
            if key in target and target.get(key) != proposed.get(key)
        }
        return {
            "action": "merge_existing",
            "entity_type": entity_type,
            "canonical_id": target["id"],
            "duplicate_id": source["id"],
            "canonical_before": target,
            "duplicate_before": source,
            "proposed_after": proposed,
            "diff": diff,
            "migration_plan": {
                "relations": "Move duplicate relations and evidence onto canonical entity where applicable.",
                "duplicate_status": "merged",
            },
            "risk_notes": [],
            "reason": f"Abstract {entity_type} duplicate into canonical object instead of appending all fields.",
            "requires_user_confirmation": True,
        }

    def merge_visual_asset(self, source_asset_id: str, target_asset_id: str) -> dict[str, Any]:
        preview = self.visual_asset_merge_preview(source_asset_id, target_asset_id)
        before = preview["canonical_before"]
        after_payload = preview["proposed_after"]
        target = self.create_visual_asset(after_payload)
        with self.connect() as conn:
            for row in conn.execute(
                "select * from visual_system_assets where asset_id = ?",
                (source_asset_id,),
            ).fetchall():
                self.set_visual_system_asset(
                    row["system_id"],
                    {
                        "asset_id": target_asset_id,
                        "role": row["role"],
                        "weight": row["weight"],
                        "reason": row["reason"],
                    },
                )
            for row in conn.execute(
                "select * from recipe_assets where asset_id = ?",
                (source_asset_id,),
            ).fetchall():
                self.set_recipe_asset(
                    row["recipe_id"],
                    {
                        "asset_id": target_asset_id,
                        "role": row["role"],
                        "weight": row["weight"],
                        "reason": row["reason"],
                    },
                )
        source = self.update_visual_asset_status(source_asset_id, "merged", merged_into_asset_id=target_asset_id)
        self.create_revision(
            "visual_asset",
            target_asset_id,
            "merge_existing",
            before=before,
            after=target,
            diff=preview["diff"],
            target_entity_id=source_asset_id,
            reason=preview["reason"],
        )
        return {**source, "canonical": target, "merged": source, "preview": preview}

    def visual_asset_merge_preview(self, source_asset_id: str, target_asset_id: str) -> dict[str, Any]:
        source = self.get_visual_asset(source_asset_id)
        target = self.get_visual_asset(target_asset_id)
        if not source:
            raise KeyError(f"Source visual asset not found: {source_asset_id}")
        if not target:
            raise KeyError(f"Target visual asset not found: {target_asset_id}")
        if source["type"] != target["type"]:
            raise ValueError("Visual assets must have the same type to merge")
        proposed = {
            **target,
            "summary": self._abstract_text([target.get("summary", ""), source.get("summary", "")]),
            "tags": self._compact_unique([*target.get("tags", []), *source.get("tags", [])], limit=12),
            "profile": self._abstract_mapping(target.get("profile", {}), source.get("profile", {}), limit=4),
            "source_references": self._compact_unique([*target.get("source_references", []), *source.get("source_references", [])], limit=12),
            "prompt_fragments": self._compact_unique([*target.get("prompt_fragments", []), *source.get("prompt_fragments", [])], limit=8),
            "negative_fragments": self._compact_unique([*target.get("negative_fragments", []), *source.get("negative_fragments", [])], limit=8),
            "compatible_with": self._compact_unique([*target.get("compatible_with", []), *source.get("compatible_with", [])], limit=12),
            "avoid_with": self._compact_unique([*target.get("avoid_with", []), *source.get("avoid_with", [])], limit=12),
            "recommended_aspect_ratios": self._compact_unique(
                [*target.get("recommended_aspect_ratios", []), *source.get("recommended_aspect_ratios", [])],
                limit=6,
            ),
            "status": target.get("status", "draft"),
        }
        return self._merge_preview("visual_asset", source, target, proposed)

    def branch_visual_asset(self, parent_asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_visual_asset(parent_asset_id):
            raise KeyError(f"Parent visual asset not found: {parent_asset_id}")
        payload = {**payload, "parent_asset_id": parent_asset_id}
        payload.setdefault("status", "draft")
        return self.create_visual_asset(payload)

    def create_visual_asset_candidate_batch(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_visual_asset_candidate(payload)
        batch_id = payload.get("batch_id") or new_id("candidate_batch")
        source_references = payload.get("source_references", [])
        candidates = [
            self.create_visual_asset_candidate(
                {
                    **candidate,
                    "batch_id": batch_id,
                    "source_references": candidate.get("source_references", source_references),
                },
                config=config,
            )
            for candidate in payload.get("candidate_assets", [])
        ]
        recipes = [
            self.create_recipe_candidate({**recipe, "batch_id": batch_id}, config=config)
            for recipe in payload.get("recipe_candidates", [])
        ]
        system_candidate_payloads = payload.get("visual_system_candidates")
        if system_candidate_payloads is None:
            system_candidate_payloads = self._suggest_visual_system_candidates(
                batch_id,
                candidates,
                recipes,
                config=config,
            )
        systems = [
            self.create_visual_system_candidate({**system, "batch_id": batch_id}, config=config)
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
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        payloads = [candidate["payload"] for candidate in candidates]
        asset_types = {payload["type"] for payload in payloads}
        related_assets = self._related_visual_assets_for_candidate_payloads(payloads, config=config)
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
                "reason": "related active asset recalled by hybrid asset similarity",
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
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_text = canonical_text(
            [
                [
                    payload.get(key)
                    for key in (
                        "type",
                        "name",
                        "summary",
                        "tags",
                        "prompt_fragments",
                        "negative_fragments",
                        "profile",
                        "compatible_with",
                    )
                ]
                for payload in payloads
            ]
        )
        if not query_text:
            return []
        return [
            {
                "asset_id": item["asset_id"],
                "type": item["type"],
                "name": item["name"],
                "similarity_score": item["score"],
                "matched_terms": item["matched_terms"],
                "semantic_score": item["semantic_score"],
                "lexical_score": item["lexical_score"],
                "relation_score": item["relation_score"],
                "quality_score": item["quality_score"],
            }
            for item in self.hybrid_recall("visual_asset", query_text, config=config, limit=limit)
        ]

    def create_visual_asset_candidate(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_visual_asset_candidate(payload)
        timestamp = now_iso()
        candidate_id = payload.get("id") or new_id("asset_candidate")
        payload.pop("similar_candidates", None)
        similar_candidates = self._suggest_similar_visual_assets(payload, config=config)
        reuse_score = float(similar_candidates[0]["similarity_score"] if similar_candidates else 0)
        query_text = self._visual_asset_candidate_query_text(payload)
        evolution_suggestion = self._evolution_suggestion(
            "visual_asset",
            query_text,
            similar_candidates[0] if similar_candidates else None,
        )
        action = evolution_suggestion["action"]
        target_asset_id = (
            evolution_suggestion.get("target_id")
            if action in {"attach_evidence", "inherit_variant", "merge_existing"}
            else None
        )
        payload = {
            **payload,
            "reuse_score": reuse_score,
            "decision": action,
            "evolution_action": action,
            "evolution_suggestion": evolution_suggestion,
            "similar_candidates": similar_candidates,
            "target_asset_id": target_asset_id,
        }
        record = {
            "id": candidate_id,
            "batch_id": payload.get("batch_id") or new_id("candidate_batch"),
            "type": payload["type"],
            "name": payload["name"],
            "payload": payload,
            "source_reference_ids": payload.get("source_reference_ids", []),
            "reuse_score": reuse_score,
            "decision": action,
            "similar_candidates": similar_candidates,
            "status": payload.get("status", "pending"),
            "target_asset_id": target_asset_id,
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

    def _visual_asset_candidate_query_text(self, payload: dict[str, Any]) -> str:
        return canonical_text(
            [
                payload.get("type"),
                payload.get("name"),
                payload.get("summary"),
                payload.get("tags"),
                payload.get("prompt_fragments"),
                payload.get("negative_fragments"),
                payload.get("profile"),
            ]
        )

    def _suggest_similar_visual_assets(
        self,
        payload: dict[str, Any],
        limit: int = 5,
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_text = self._visual_asset_candidate_query_text(payload)
        suggestions = []
        for item in self.hybrid_recall("visual_asset", query_text, config=config, limit=50, min_score=0.0):
            if item.get("type") != payload["type"]:
                continue
            suggestions.append(
                {
                    "asset_id": item["asset_id"],
                    "name": item["name"],
                    "similarity_score": item["score"],
                    "matched_terms": item["matched_terms"],
                    "semantic_score": item["semantic_score"],
                    "lexical_score": item["lexical_score"],
                    "relation_score": item["relation_score"],
                    "quality_score": item["quality_score"],
                }
            )
            if len(suggestions) >= limit:
                break
        return suggestions

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
        action = decision
        payload["decision"] = action
        payload["evolution_action"] = action
        validate_visual_asset_candidate(payload)

        confirmed_asset_id: str | None = None
        status = "confirmed"
        before: dict[str, Any] | None = None
        after: dict[str, Any] | None = None
        if action == "create_new":
            asset_payload = self._candidate_to_visual_asset_payload(candidate)
            confirmed_asset_id = self.create_visual_asset(asset_payload)["id"]
            after = self.get_visual_asset(confirmed_asset_id)
            self.create_revision(
                "visual_asset",
                confirmed_asset_id,
                "create_new",
                after=after,
                scores=payload.get("evolution_suggestion", {}).get("scores", {}),
                source_candidate_id=candidate_id,
                reason=payload.get("evolution_suggestion", {}).get("reason", ""),
            )
        elif action == "inherit_variant":
            if not target_asset_id:
                raise KeyError("target_asset_id is required for inherit_variant")
            before = self.get_visual_asset(target_asset_id)
            asset_payload = self._candidate_to_visual_asset_payload(candidate)
            asset_payload["metadata"] = {
                **asset_payload.get("metadata", {}),
                "variant_delta": payload.get("variant_delta", {}),
                "variant_reason": payload.get("evolution_suggestion", {}).get("reason", ""),
            }
            confirmed_asset_id = self.branch_visual_asset(target_asset_id, asset_payload)["id"]
            after = self.get_visual_asset(confirmed_asset_id)
            self.create_revision(
                "visual_asset",
                confirmed_asset_id,
                "inherit_variant",
                before=before,
                after=after,
                scores=payload.get("evolution_suggestion", {}).get("scores", {}),
                source_candidate_id=candidate_id,
                target_entity_id=target_asset_id,
                reason=payload.get("evolution_suggestion", {}).get("reason", ""),
            )
        elif action == "attach_evidence":
            if not target_asset_id:
                raise KeyError("target_asset_id is required for attach_evidence")
            if not self.get_visual_asset(target_asset_id):
                raise KeyError(f"Target visual asset not found: {target_asset_id}")
            confirmed_asset_id = target_asset_id
        elif action == "merge_existing":
            if not target_asset_id:
                raise KeyError("target_asset_id is required for merge_existing")
            if not self.get_visual_asset(target_asset_id):
                raise KeyError(f"Target visual asset not found: {target_asset_id}")
            confirmed_asset_id = target_asset_id
        elif action == "ignore":
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
                (action, status, target_asset_id, confirmed_asset_id, timestamp, candidate_id),
            )
        updated = self.get_visual_asset_candidate(candidate_id)
        assert updated is not None
        if confirmed_asset_id:
            self.create_visual_asset_evidence(
                confirmed_asset_id,
                {
                    "evidence_type": "candidate_confirmation",
                    "source_candidate_id": candidate_id,
                    "payload": {
                        "candidate_id": candidate_id,
                        "decision": action,
                        "evolution_action": action,
                        "candidate": self.compact_candidate_payload(candidate["payload"]),
                    },
                },
            )
            if action in {"attach_evidence", "merge_existing"}:
                self.create_revision(
                    "visual_asset",
                    confirmed_asset_id,
                    action,
                    before=self.get_visual_asset(confirmed_asset_id),
                    after=self.get_visual_asset(confirmed_asset_id),
                    scores=payload.get("evolution_suggestion", {}).get("scores", {}),
                    source_candidate_id=candidate_id,
                    target_entity_id=target_asset_id,
                    reason=payload.get("evolution_suggestion", {}).get("reason", ""),
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
            payload = candidate.get("payload", {})
            suggestion = payload.get("evolution_suggestion", {})
            action = (
                payload.get("evolution_action")
                or suggestion.get("action")
                or candidate.get("decision")
                or "create_new"
            )
            target_asset_id = candidate.get("target_asset_id") or suggestion.get("target_id")
            if action in {"attach_evidence", "inherit_variant", "merge_existing"} and not target_asset_id:
                similar = candidate.get("similar_candidates", [])
                if similar:
                    target_asset_id = similar[0].get("asset_id")
            asset_results.append(self.decide_visual_asset_candidate(candidate["id"], action, target_asset_id))

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
            "status": payload.get("asset_status", "active"),
        }

    def compact_candidate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata", {})
        compacted = {
            key: self._compact_json_value(payload[key])
            for key in (
                "id",
                "type",
                "name",
                "summary",
                "tags",
                "profile",
                "prompt_fragments",
                "negative_fragments",
                "compatible_with",
                "avoid_with",
                "recommended_aspect_ratios",
                "source_reference_ids",
                "source_references",
                "parent_system_ids",
                "use_cases",
                "required_asset_types",
                "composition_rules",
                "visual_rules",
                "avoid_rules",
                "confidence",
                "source",
                "reason",
            )
            if key in payload and payload[key] not in (None, "", [], {})
        }
        for key in ("decision", "evolution_action", "variant_delta", "asset_status"):
            if payload.get(key) not in (None, "", [], {}):
                compacted[key] = self._compact_json_value(payload[key])
        suggestion = payload.get("evolution_suggestion")
        if isinstance(suggestion, dict):
            compacted["evolution_suggestion"] = {
                key: self._compact_json_value(suggestion[key])
                for key in ("action", "target_id", "confidence", "scores", "reason", "requires_user_confirmation")
                if key in suggestion and suggestion[key] not in (None, "", [], {})
            }
        if isinstance(metadata, dict) and metadata:
            compacted["metadata"] = {
                key: self._compact_json_value(metadata[key])
                for key in (
                    "recommendation",
                    "evolution_action",
                    "target_system_id",
                    "target_recipe_id",
                    "dedupe_score",
                    "evolution_suggestion",
                    "source_generation_id",
                    "reason",
                )
                if key in metadata and metadata[key] not in (None, "", [], {})
            }
        for key in ("related_existing_assets", "related_existing_systems", "related_existing_recipes", "similar_candidates"):
            values = payload.get(key)
            if isinstance(values, list) and values:
                compacted[key] = [self._compact_json_value(item) for item in values[:3]]
                if len(values) > 3:
                    compacted[f"{key}_omitted_count"] = len(values) - 3
        return compacted

    def _compact_candidate_row_payloads(
        self,
        table: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        compacted = []
        with self.connect() as conn:
            for row in rows:
                payload = row.get("payload", {})
                next_payload = self.compact_candidate_payload(payload) if isinstance(payload, dict) else {}
                conn.execute(
                    f"update {table} set payload_json = ? where id = ?",
                    (json_dumps(next_payload), row["id"]),
                )
                compacted.append(
                    {
                        "id": row["id"],
                        "status": row.get("status"),
                        "before_bytes": len(json_dumps(payload)),
                        "after_bytes": len(json_dumps(next_payload)),
                    }
                )
        return {
            "table": table,
            "compacted_count": len(compacted),
            "bytes_before": sum(item["before_bytes"] for item in compacted),
            "bytes_after": sum(item["after_bytes"] for item in compacted),
            "items": compacted,
        }

    def compact_visual_asset_candidates(
        self,
        status: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        candidates = self.list_visual_asset_candidates(status=status, batch_id=batch_id, limit=None)
        return self._compact_candidate_row_payloads("visual_asset_candidates", candidates)

    def compact_visual_system_candidates(
        self,
        status: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        candidates = self.list_visual_system_candidates(status=status, batch_id=batch_id, limit=None)
        return self._compact_candidate_row_payloads("visual_system_candidates", candidates)

    def compact_recipe_candidates(
        self,
        status: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        candidates = self.list_recipe_candidates(status=status, batch_id=batch_id, limit=None)
        return self._compact_candidate_row_payloads("recipe_candidates", candidates)

    def create_visual_asset_evidence(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("asset_evidence"),
            "asset_id": asset_id,
            "evidence_type": payload["evidence_type"],
            "generation_run_id": payload.get("generation_run_id"),
            "source_candidate_id": payload.get("source_candidate_id"),
            "source_reference_id": payload.get("source_reference_id"),
            "payload": payload.get("payload", {}),
            "created_at": payload.get("created_at", timestamp),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_asset_evidence (
                  id, asset_id, evidence_type, generation_run_id, source_candidate_id,
                  source_reference_id, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["asset_id"],
                    record["evidence_type"],
                    record["generation_run_id"],
                    record["source_candidate_id"],
                    record["source_reference_id"],
                    json_dumps(record["payload"]),
                    record["created_at"],
                ),
            )
        return record

    def create_recipe_evidence(self, recipe_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_recipe(recipe_id, include_assets=False):
            raise KeyError(f"Recipe not found: {recipe_id}")
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("recipe_evidence"),
            "recipe_id": recipe_id,
            "evidence_type": payload["evidence_type"],
            "source_candidate_id": payload.get("source_candidate_id"),
            "source_generation_id": payload.get("source_generation_id"),
            "source_reference_id": payload.get("source_reference_id"),
            "payload": payload.get("payload", {}),
            "created_at": payload.get("created_at", timestamp),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into recipe_evidence (
                  id, recipe_id, evidence_type, source_candidate_id, source_generation_id,
                  source_reference_id, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["recipe_id"],
                    record["evidence_type"],
                    record["source_candidate_id"],
                    record["source_generation_id"],
                    record["source_reference_id"],
                    json_dumps(record["payload"]),
                    record["created_at"],
                ),
            )
        return record

    def create_visual_system_evidence(self, system_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_visual_system(system_id, include_assets=False):
            raise KeyError(f"Visual system not found: {system_id}")
        timestamp = now_iso()
        record = {
            "id": payload.get("id") or new_id("system_evidence"),
            "system_id": system_id,
            "evidence_type": payload["evidence_type"],
            "source_candidate_id": payload.get("source_candidate_id"),
            "source_generation_id": payload.get("source_generation_id"),
            "source_reference_id": payload.get("source_reference_id"),
            "payload": payload.get("payload", {}),
            "created_at": payload.get("created_at", timestamp),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_system_evidence (
                  id, system_id, evidence_type, source_candidate_id, source_generation_id,
                  source_reference_id, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["system_id"],
                    record["evidence_type"],
                    record["source_candidate_id"],
                    record["source_generation_id"],
                    record["source_reference_id"],
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

    def list_recipe_evidence(
        self,
        recipe_id: str | None = None,
        evidence_type: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from recipe_evidence"
        clauses: list[str] = []
        params: list[Any] = []
        if recipe_id:
            clauses.append("recipe_id = ?")
            params.append(recipe_id)
        if evidence_type:
            clauses.append("evidence_type = ?")
            params.append(evidence_type)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        evidence = [self._recipe_evidence_from_row(row) for row in rows]
        return evidence[:limit] if limit is not None and limit >= 0 else evidence

    def list_visual_system_evidence(
        self,
        system_id: str | None = None,
        evidence_type: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        sql = "select * from visual_system_evidence"
        clauses: list[str] = []
        params: list[Any] = []
        if system_id:
            clauses.append("system_id = ?")
            params.append(system_id)
        if evidence_type:
            clauses.append("evidence_type = ?")
            params.append(evidence_type)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        evidence = [self._visual_system_evidence_from_row(row) for row in rows]
        return evidence[:limit] if limit is not None and limit >= 0 else evidence

    def create_revision(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
        scores: dict[str, Any] | None = None,
        source_candidate_id: str | None = None,
        source_generation_id: str | None = None,
        target_entity_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        table_by_type = {
            "visual_asset": ("visual_asset_revisions", "asset_id", "asset_revision"),
            "recipe": ("recipe_revisions", "recipe_id", "recipe_revision"),
            "visual_system": ("visual_system_revisions", "system_id", "system_revision"),
        }
        if entity_type not in table_by_type:
            raise ValueError(f"Unsupported revision entity type: {entity_type}")
        table, id_column, id_prefix = table_by_type[entity_type]
        timestamp = now_iso()
        record = {
            "id": new_id(id_prefix),
            id_column: entity_id,
            "action": action,
            "source_candidate_id": source_candidate_id,
            "source_generation_id": source_generation_id,
            "target_entity_id": target_entity_id,
            "scores": scores or {},
            "before": before or {},
            "after": after or {},
            "diff": diff or {},
            "reason": reason,
            "created_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                f"""
                insert into {table} (
                  id, {id_column}, action, source_candidate_id, source_generation_id,
                  target_entity_id, scores_json, before_json, after_json, diff_json,
                  reason, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record[id_column],
                    record["action"],
                    record["source_candidate_id"],
                    record["source_generation_id"],
                    record["target_entity_id"],
                    json_dumps(record["scores"]),
                    json_dumps(record["before"]),
                    json_dumps(record["after"]),
                    json_dumps(record["diff"]),
                    record["reason"],
                    record["created_at"],
                ),
            )
        return record

    def list_revisions(
        self,
        entity_type: str,
        entity_id: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        table_by_type = {
            "visual_asset": ("visual_asset_revisions", "asset_id"),
            "recipe": ("recipe_revisions", "recipe_id"),
            "visual_system": ("visual_system_revisions", "system_id"),
        }
        if entity_type not in table_by_type:
            raise ValueError(f"Unsupported revision entity type: {entity_type}")
        table, id_column = table_by_type[entity_type]
        sql = f"select * from {table}"
        params: tuple[Any, ...] = ()
        if entity_id:
            sql += f" where {id_column} = ?"
            params = (entity_id,)
        sql += " order by created_at desc"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        revisions = [self._revision_from_row(entity_type, id_column, row) for row in rows]
        return revisions[:limit] if limit is not None and limit >= 0 else revisions

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
        if payload.get("parent_system_id") and not self.get_visual_system(payload["parent_system_id"], include_assets=False):
            raise KeyError(f"Parent visual system not found: {payload['parent_system_id']}")
        timestamp = now_iso()
        system_id = payload.get("id") or self._unique_slug_id(
            "visual_systems",
            slugify(f"{payload['kind']}-{payload['name']}", "visual_system"),
        )
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
            "parent_system_id": payload.get("parent_system_id"),
            "merged_into_system_id": payload.get("merged_into_system_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into visual_systems (
                  id, kind, name, summary, tags_json, visual_rules_json, avoid_rules_json,
                  source_reference_ids_json, metadata_json, status, parent_system_id,
                  merged_into_system_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                  parent_system_id=excluded.parent_system_id,
                  merged_into_system_id=excluded.merged_into_system_id,
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
                    record["parent_system_id"],
                    record["merged_into_system_id"],
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

    def update_visual_system_status(
        self,
        system_id: str,
        status: str,
        merged_into_system_id: str | None = None,
        parent_system_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("select * from visual_systems where id = ?", (system_id,)).fetchone()
            if not row:
                raise KeyError(f"Visual system not found: {system_id}")
            conn.execute(
                """
                update visual_systems
                set status = ?,
                    merged_into_system_id = coalesce(?, merged_into_system_id),
                    parent_system_id = coalesce(?, parent_system_id),
                    updated_at = ?
                where id = ?
                """,
                (status, merged_into_system_id, parent_system_id, timestamp, system_id),
            )
        updated = self.get_visual_system(system_id)
        assert updated is not None
        return updated

    def visual_system_merge_preview(self, source_system_id: str, target_system_id: str) -> dict[str, Any]:
        source = self.get_visual_system(source_system_id)
        target = self.get_visual_system(target_system_id)
        if not source:
            raise KeyError(f"Source visual system not found: {source_system_id}")
        if not target:
            raise KeyError(f"Target visual system not found: {target_system_id}")
        if source["kind"] != target["kind"]:
            raise ValueError("Visual systems must have the same kind to merge")
        proposed = {
            **target,
            "summary": self._abstract_text([target.get("summary", ""), source.get("summary", "")]),
            "tags": self._compact_unique([*target.get("tags", []), *source.get("tags", [])], limit=16),
            "visual_rules": self._abstract_rules(target.get("visual_rules", []), source.get("visual_rules", [])),
            "avoid_rules": self._compact_unique([*target.get("avoid_rules", []), *source.get("avoid_rules", [])], limit=10),
            "source_reference_ids": self._compact_unique(
                [*target.get("source_reference_ids", []), *source.get("source_reference_ids", [])],
                limit=20,
            ),
            "metadata": self._abstract_mapping(target.get("metadata", {}), source.get("metadata", {}), limit=4),
            "status": target.get("status", "draft"),
        }
        return self._merge_preview("visual_system", source, target, proposed)

    def merge_visual_system(self, source_system_id: str, target_system_id: str) -> dict[str, Any]:
        preview = self.visual_system_merge_preview(source_system_id, target_system_id)
        before = preview["canonical_before"]
        system = self.create_visual_system(preview["proposed_after"])
        for relation in self.list_visual_system_assets(system_id=source_system_id):
            self.set_visual_system_asset(
                target_system_id,
                {
                    "asset_id": relation["asset_id"],
                    "role": relation["role"],
                    "weight": relation["weight"],
                    "reason": relation["reason"],
                },
            )
        for recipe in self.list_recipes(system_id=source_system_id, limit=None):
            parent_system_ids = self._compact_unique(
                [target_system_id if item == source_system_id else item for item in recipe.get("parent_system_ids", [])],
                limit=12,
            )
            self.create_recipe({**recipe, "parent_system_ids": parent_system_ids})
        merged = self.update_visual_system_status(source_system_id, "merged", merged_into_system_id=target_system_id)
        self.create_revision(
            "visual_system",
            target_system_id,
            "merge_existing",
            before=before,
            after=system,
            diff=preview["diff"],
            target_entity_id=source_system_id,
            reason=preview["reason"],
        )
        return {"canonical": system, "merged": merged, "preview": preview}

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

    def create_visual_system_candidate(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._annotate_visual_system_candidate_recall(dict(payload), config=config)
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

    def _annotate_visual_system_candidate_recall(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload.pop("related_existing_systems", None)
        metadata = dict(payload.get("metadata", {}))
        metadata["recommendation"] = "suggest_create"
        metadata.pop("evolution_action", None)
        metadata.pop("target_system_id", None)
        metadata.pop("dedupe_score", None)
        payload["metadata"] = metadata
        query_text = canonical_text(
            [
                payload.get("kind"),
                payload.get("name"),
                payload.get("summary"),
                payload.get("tags"),
                payload.get("visual_rules"),
                payload.get("avoid_rules"),
            ]
        )
        related_asset_ids = [
            relation["asset_id"]
            for relation in payload.get("existing_asset_relations", [])
            if isinstance(relation, dict) and relation.get("asset_id")
        ]
        systems = self.hybrid_recall(
            "visual_system",
            query_text,
            config=config,
            limit=5,
            related_asset_ids=related_asset_ids,
            min_score=0.0,
        )
        related_systems = []
        for system in systems:
            dedupe_score = max(
                float(system.get("score", 0.0)),
                float(system.get("semantic_score", 0.0)),
                float(system.get("lexical_score", 0.0)),
                float(system.get("relation_score", 0.0)),
            )
            scores = self._evolution_scores("visual_system", query_text, system)
            action = self._evolution_action("visual_system", scores)
            recommendation = {
                "attach_evidence": "attach_evidence",
                "inherit_variant": "inherit_variant",
                "create_new": "suggest_create",
                "merge_existing": "merge_existing",
            }.get(action, action)
            related_systems.append({**system, "dedupe_score": round(dedupe_score, 4), "recommendation": recommendation})
        if related_systems:
            payload["related_existing_systems"] = related_systems
            top = related_systems[0]
            suggestion = self._evolution_suggestion("visual_system", query_text, top)
            metadata["evolution_action"] = suggestion["action"]
            metadata["evolution_suggestion"] = suggestion
            metadata["recommendation"] = top["recommendation"]
            if suggestion.get("target_id"):
                metadata["target_system_id"] = top["system_id"]
                metadata["dedupe_score"] = top["dedupe_score"]
            payload["metadata"] = metadata
        else:
            suggestion = self._evolution_suggestion("visual_system", query_text, None)
            metadata["evolution_action"] = suggestion["action"]
            metadata["evolution_suggestion"] = suggestion
            payload["metadata"] = metadata
        return payload

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

    def confirm_visual_system_candidate(
        self,
        candidate_id: str,
        target_system_id: str | None = None,
        action: str | None = None,
        force_new: bool = False,
    ) -> dict[str, Any]:
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
        metadata = dict(payload.get("metadata", {}))
        if target_system_id:
            metadata["recommendation"] = "attach_evidence"
            metadata["evolution_action"] = "attach_evidence"
            metadata["target_system_id"] = target_system_id
        if force_new:
            metadata["recommendation"] = "suggest_create"
            metadata["evolution_action"] = "create_new"
            metadata.pop("target_system_id", None)
        if action:
            metadata["evolution_action"] = action
            if action == "create_new":
                metadata["recommendation"] = "suggest_create"
                metadata.pop("target_system_id", None)
            elif action in {"attach_evidence", "inherit_variant", "merge_existing"}:
                metadata["recommendation"] = action
                if target_system_id:
                    metadata["target_system_id"] = target_system_id
        target_system_id = metadata.get("target_system_id")
        evolution_action = metadata.get("evolution_action") or {
            "attach_or_extend": "attach_evidence",
            "possible_duplicate": "inherit_variant",
            "suggest_create": "create_new",
        }.get(metadata.get("recommendation"), "create_new")
        if evolution_action in {"attach_evidence", "merge_existing"} and target_system_id:
            if not self.get_visual_system(target_system_id, include_assets=False):
                raise KeyError(f"Target visual system not found: {target_system_id}")
            for relation in assets:
                self.set_visual_system_asset(target_system_id, relation)
            self.create_visual_system_evidence(
                target_system_id,
                {
                    "evidence_type": "candidate_confirmation",
                    "source_candidate_id": candidate_id,
                    "payload": {
                        "candidate_id": candidate_id,
                        "evolution_action": evolution_action,
                        "candidate": self.compact_candidate_payload(payload),
                    },
                },
            )
            current_system = self.get_visual_system(target_system_id)
            self.create_revision(
                "visual_system",
                target_system_id,
                evolution_action,
                before=current_system,
                after=current_system,
                scores=metadata.get("evolution_suggestion", {}).get("scores", {}),
                source_candidate_id=candidate_id,
                target_entity_id=target_system_id,
                reason=metadata.get("evolution_suggestion", {}).get("reason", ""),
            )
            timestamp = now_iso()
            with self.connect() as conn:
                conn.execute(
                    """
                    update visual_system_candidates
                    set status = ?, confirmed_system_id = ?, updated_at = ?
                    where id = ?
                    """,
                    ("confirmed", target_system_id, timestamp, candidate_id),
                )
            updated = self.get_visual_system_candidate(candidate_id)
            assert updated is not None
            updated["visual_system"] = self.get_visual_system(target_system_id)
            updated["dedupe_decision"] = evolution_action
            return updated
        if evolution_action == "inherit_variant" and target_system_id:
            if not self.get_visual_system(target_system_id, include_assets=False):
                raise KeyError(f"Parent visual system not found: {target_system_id}")
            metadata["parent_system_id"] = target_system_id
            payload["parent_system_id"] = target_system_id
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
                "related_existing_systems",
                "batch_id",
            }
        }
        system_payload["status"] = "active"
        system_payload["metadata"] = metadata
        system_payload["assets"] = assets
        system = self.create_visual_system(system_payload)
        self.create_visual_system_evidence(
            system["id"],
            {
                "evidence_type": "candidate_confirmation",
                "source_candidate_id": candidate_id,
                "payload": {
                    "candidate_id": candidate_id,
                    "evolution_action": evolution_action,
                    "candidate": self.compact_candidate_payload(payload),
                },
            },
        )
        self.create_revision(
            "visual_system",
            system["id"],
            evolution_action,
            after=system,
            scores=metadata.get("evolution_suggestion", {}).get("scores", {}),
            source_candidate_id=candidate_id,
            target_entity_id=target_system_id,
            reason=metadata.get("evolution_suggestion", {}).get("reason", ""),
        )
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
        if payload.get("parent_recipe_id") and not self.get_recipe(payload["parent_recipe_id"], include_assets=False):
            raise KeyError(f"Parent recipe not found: {payload['parent_recipe_id']}")
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
            "metadata": payload.get("metadata", {}),
            "status": payload.get("status", "draft"),
            "parent_recipe_id": payload.get("parent_recipe_id"),
            "merged_into_recipe_id": payload.get("merged_into_recipe_id"),
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into recipes (
                  id, name, summary, parent_system_ids_json, use_cases_json,
                  required_asset_types_json, composition_rules_json, recommended_aspect_ratios_json,
                  source_reference_ids_json, confidence, source, reason, metadata_json, status,
                  parent_recipe_id, merged_into_recipe_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                  metadata_json=excluded.metadata_json,
                  status=excluded.status,
                  parent_recipe_id=excluded.parent_recipe_id,
                  merged_into_recipe_id=excluded.merged_into_recipe_id,
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
                    json_dumps(record["metadata"]),
                    record["status"],
                    record["parent_recipe_id"],
                    record["merged_into_recipe_id"],
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
        if table not in {"recipes", "visual_assets", "visual_systems"}:
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

    def update_recipe_status(
        self,
        recipe_id: str,
        status: str,
        merged_into_recipe_id: str | None = None,
        parent_recipe_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute("select * from recipes where id = ?", (recipe_id,)).fetchone()
            if not row:
                raise KeyError(f"Recipe not found: {recipe_id}")
            conn.execute(
                """
                update recipes
                set status = ?,
                    merged_into_recipe_id = coalesce(?, merged_into_recipe_id),
                    parent_recipe_id = coalesce(?, parent_recipe_id),
                    updated_at = ?
                where id = ?
                """,
                (status, merged_into_recipe_id, parent_recipe_id, timestamp, recipe_id),
            )
        updated = self.get_recipe(recipe_id)
        assert updated is not None
        return updated

    def recipe_merge_preview(self, source_recipe_id: str, target_recipe_id: str) -> dict[str, Any]:
        source = self.get_recipe(source_recipe_id)
        target = self.get_recipe(target_recipe_id)
        if not source:
            raise KeyError(f"Source recipe not found: {source_recipe_id}")
        if not target:
            raise KeyError(f"Target recipe not found: {target_recipe_id}")
        proposed = {
            **target,
            "summary": self._abstract_text([target.get("summary", ""), source.get("summary", "")]),
            "parent_system_ids": self._compact_unique(
                [*target.get("parent_system_ids", []), *source.get("parent_system_ids", [])],
                limit=8,
            ),
            "use_cases": self._compact_unique([*target.get("use_cases", []), *source.get("use_cases", [])], limit=12),
            "required_asset_types": self._compact_unique(
                [*target.get("required_asset_types", []), *source.get("required_asset_types", [])],
                limit=10,
            ),
            "composition_rules": self._abstract_rules(
                target.get("composition_rules", []),
                source.get("composition_rules", []),
            ),
            "recommended_aspect_ratios": self._compact_unique(
                [*target.get("recommended_aspect_ratios", []), *source.get("recommended_aspect_ratios", [])],
                limit=6,
            ),
            "source_reference_ids": self._compact_unique(
                [*target.get("source_reference_ids", []), *source.get("source_reference_ids", [])],
                limit=20,
            ),
            "confidence": max(float(target.get("confidence", 0.5)), float(source.get("confidence", 0.5))),
            "metadata": self._abstract_mapping(target.get("metadata", {}), source.get("metadata", {}), limit=4),
            "status": target.get("status", "draft"),
        }
        return self._merge_preview("recipe", source, target, proposed)

    def merge_recipe(self, source_recipe_id: str, target_recipe_id: str) -> dict[str, Any]:
        preview = self.recipe_merge_preview(source_recipe_id, target_recipe_id)
        before = preview["canonical_before"]
        recipe = self.create_recipe(preview["proposed_after"])
        for relation in self.list_recipe_assets(recipe_id=source_recipe_id):
            self.set_recipe_asset(
                target_recipe_id,
                {
                    "asset_id": relation["asset_id"],
                    "role": relation["role"],
                    "weight": relation["weight"],
                    "reason": relation["reason"],
                },
            )
        merged = self.update_recipe_status(source_recipe_id, "merged", merged_into_recipe_id=target_recipe_id)
        self.create_revision(
            "recipe",
            target_recipe_id,
            "merge_existing",
            before=before,
            after=recipe,
            diff=preview["diff"],
            target_entity_id=source_recipe_id,
            reason=preview["reason"],
        )
        return {"canonical": recipe, "merged": merged, "preview": preview}

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

    def create_recipe_candidate(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._annotate_recipe_candidate_recall(dict(payload), config=config)
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

    def _annotate_recipe_candidate_recall(
        self,
        payload: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload.pop("related_existing_recipes", None)
        metadata = dict(payload.get("metadata", {}))
        metadata["recommendation"] = "suggest_create"
        metadata.pop("evolution_action", None)
        metadata.pop("target_recipe_id", None)
        metadata.pop("dedupe_score", None)
        payload["metadata"] = metadata
        query_text = canonical_text(
            [
                payload.get("name"),
                payload.get("summary"),
                payload.get("tags"),
                payload.get("use_cases"),
                payload.get("required_asset_types"),
                payload.get("composition_rules"),
                payload.get("recommended_aspect_ratios"),
            ]
        )
        related_asset_ids = [
            relation["asset_id"]
            for relation in payload.get("recipe_assets", [])
            if isinstance(relation, dict) and relation.get("asset_id")
        ]
        parent_system_ids = [system_id for system_id in payload.get("parent_system_ids", []) if isinstance(system_id, str)]
        recipes = self.hybrid_recall(
            "recipe",
            query_text,
            config=config,
            limit=5,
            related_asset_ids=related_asset_ids,
            parent_system_ids=parent_system_ids,
            min_score=0.0,
        )
        related_recipes = []
        for recipe in recipes:
            dedupe_score = max(
                float(recipe.get("score", 0.0)),
                float(recipe.get("semantic_score", 0.0)),
                float(recipe.get("lexical_score", 0.0)),
                float(recipe.get("relation_score", 0.0)),
            )
            scores = self._evolution_scores("recipe", query_text, recipe)
            action = self._evolution_action("recipe", scores)
            recommendation = {
                "attach_evidence": "attach_evidence",
                "inherit_variant": "inherit_variant",
                "create_new": "suggest_create",
                "merge_existing": "merge_existing",
            }.get(action, action)
            related_recipes.append({**recipe, "dedupe_score": round(dedupe_score, 4), "recommendation": recommendation})
        if related_recipes:
            payload["related_existing_recipes"] = related_recipes
            top = related_recipes[0]
            suggestion = self._evolution_suggestion("recipe", query_text, top)
            metadata["evolution_action"] = suggestion["action"]
            metadata["evolution_suggestion"] = suggestion
            metadata["recommendation"] = top["recommendation"]
            if suggestion.get("target_id"):
                metadata["target_recipe_id"] = top["recipe_id"]
                metadata["dedupe_score"] = top["dedupe_score"]
            payload["metadata"] = metadata
        else:
            suggestion = self._evolution_suggestion("recipe", query_text, None)
            metadata["evolution_action"] = suggestion["action"]
            metadata["evolution_suggestion"] = suggestion
            payload["metadata"] = metadata
        return payload

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

    def confirm_recipe_candidate(
        self,
        candidate_id: str,
        parent_system_ids: list[str] | None = None,
        target_recipe_id: str | None = None,
        variant_of_recipe_id: str | None = None,
        action: str | None = None,
        force_new: bool = False,
    ) -> dict[str, Any]:
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
        metadata = dict(recipe_payload.get("metadata", {}))
        if target_recipe_id:
            metadata["recommendation"] = "attach_evidence"
            metadata["evolution_action"] = "attach_evidence"
            metadata["target_recipe_id"] = target_recipe_id
        if variant_of_recipe_id:
            metadata["recommendation"] = "inherit_variant"
            metadata["evolution_action"] = "inherit_variant"
            metadata["target_recipe_id"] = variant_of_recipe_id
        if force_new:
            metadata["recommendation"] = "suggest_create"
            metadata["evolution_action"] = "create_new"
            metadata.pop("target_recipe_id", None)
        if action:
            metadata["evolution_action"] = action
            if action == "create_new":
                metadata["recommendation"] = "suggest_create"
                metadata.pop("target_recipe_id", None)
            elif action in {"attach_evidence", "inherit_variant", "merge_existing"}:
                metadata["recommendation"] = action
                if target_recipe_id or variant_of_recipe_id:
                    metadata["target_recipe_id"] = target_recipe_id or variant_of_recipe_id
        recipe_payload["metadata"] = metadata
        evolution_action = metadata.get("evolution_action") or {
            "merge_or_update": "attach_evidence",
            "variant": "inherit_variant",
            "possible_related": "inherit_variant",
            "suggest_create": "create_new",
        }.get(metadata.get("recommendation"), "create_new")
        if evolution_action in {"attach_evidence", "merge_existing"} and metadata.get("target_recipe_id"):
            target_recipe_id = metadata["target_recipe_id"]
            if not self.get_recipe(target_recipe_id, include_assets=False):
                raise KeyError(f"Target recipe not found: {target_recipe_id}")
            for relation in recipe_assets:
                self.set_recipe_asset(target_recipe_id, relation)
            self.create_recipe_evidence(
                target_recipe_id,
                {
                    "evidence_type": "candidate_confirmation",
                    "source_candidate_id": candidate_id,
                    "payload": {
                        "candidate_id": candidate_id,
                        "evolution_action": evolution_action,
                        "candidate": self.compact_candidate_payload(payload),
                    },
                },
            )
            current_recipe = self.get_recipe(target_recipe_id)
            self.create_revision(
                "recipe",
                target_recipe_id,
                evolution_action,
                before=current_recipe,
                after=current_recipe,
                scores=metadata.get("evolution_suggestion", {}).get("scores", {}),
                source_candidate_id=candidate_id,
                target_entity_id=target_recipe_id,
                reason=metadata.get("evolution_suggestion", {}).get("reason", ""),
            )
            timestamp = now_iso()
            with self.connect() as conn:
                conn.execute(
                    """
                    update recipe_candidates
                    set status = ?, confirmed_recipe_id = ?, updated_at = ?
                    where id = ?
                    """,
                    ("confirmed", target_recipe_id, timestamp, candidate_id),
                )
            updated = self.get_recipe_candidate(candidate_id)
            assert updated is not None
            updated["recipe"] = self.get_recipe(target_recipe_id)
            updated["dedupe_decision"] = evolution_action
            return updated
        if evolution_action == "inherit_variant" and metadata.get("target_recipe_id"):
            recipe_payload["metadata"] = {
                **metadata,
                "variant_of_recipe_id": metadata["target_recipe_id"],
                "dedupe_decision": "variant",
            }
            recipe_payload["parent_recipe_id"] = metadata["target_recipe_id"]
            if not recipe_payload.get("parent_system_ids"):
                target_recipe = self.get_recipe(metadata["target_recipe_id"])
                if target_recipe:
                    recipe_payload["parent_system_ids"] = target_recipe.get("parent_system_ids", [])
        recipe_payload["status"] = "active"
        recipe_payload["assets"] = recipe_assets
        recipe = self.create_recipe(recipe_payload)
        self.create_recipe_evidence(
            recipe["id"],
            {
                "evidence_type": "candidate_confirmation",
                "source_candidate_id": candidate_id,
                "payload": {
                    "candidate_id": candidate_id,
                    "evolution_action": evolution_action,
                    "candidate": self.compact_candidate_payload(payload),
                },
            },
        )
        self.create_revision(
            "recipe",
            recipe["id"],
            evolution_action,
            after=recipe,
            scores=metadata.get("evolution_suggestion", {}).get("scores", {}),
            source_candidate_id=candidate_id,
            target_entity_id=metadata.get("target_recipe_id"),
            reason=metadata.get("evolution_suggestion", {}).get("reason", ""),
        )
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
            "duplicate_group_count": len(self.duplicate_assets()),
            "unreferenced_count": len(self.unreferenced_assets()),
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
        payload = self.compact_prompt_record_payload(payload)
        constraints = payload.get("constraints", {})
        selected_assets = payload.get("selected_assets")
        if selected_assets is None and isinstance(constraints, dict):
            selected_assets = constraints.get("selected_assets", [])
        record = {
            "id": payload.get("id") or new_id("prompt"),
            "source_prompt": payload["source_prompt"],
            "style_id": None,
            "target_generation_skill": payload.get("target_generation_skill"),
            "selected_assets": selected_assets or [],
            "constraints": constraints,
            "intent_analysis": payload.get("intent_analysis", {}),
            "intent_sketch": payload.get("intent_sketch", {}),
            "recall_candidates": payload.get("recall_candidates", {}),
            "recall_strategy": payload.get("recall_strategy", {}),
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
                  intent_analysis_json, intent_sketch_json, recall_candidates_json, recall_strategy_json,
                  composition_plan_json, refined_prompt, negative_prompt, generation_params_json,
                  variants_json, assumptions_json, conflicts_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["source_prompt"],
                    record["style_id"],
                    record["target_generation_skill"],
                    json_dumps(record["selected_assets"]),
                    json_dumps(record["constraints"]),
                    json_dumps(record["intent_analysis"]),
                    json_dumps(record["intent_sketch"]),
                    json_dumps(record["recall_candidates"]),
                    json_dumps(record["recall_strategy"]),
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
            "style_id": None,
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
        asset_id: str | None = None,
        status: str | None = None,
        review: str | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, Any]]:
        query = "select * from generation_runs"
        clauses: list[str] = []
        params: list[Any] = []
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

    def generation_stats(self, asset_id: str | None = None) -> dict[str, Any]:
        runs = self.list_generation_runs(asset_id=asset_id, limit=None)
        by_status: dict[str, int] = {}
        by_review: dict[str, int] = {}
        by_asset: dict[str, dict[str, Any]] = {}
        feedback: dict[str, int] = {"liked": 0, "rejected": 0, "unrated": 0}
        deviations: dict[str, int] = {}

        for run in runs:
            status = run.get("status") or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

            review = run.get("visual_review", {}).get("style_consistency") or "not_reviewed"
            by_review[review] = by_review.get(review, 0) + 1

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
                for selected in run.get("selected_assets", []):
                    selected_id = self._selected_asset_id(selected)
                    if selected_id and selected_id in by_asset:
                        by_asset[selected_id]["liked"] += 1
            elif liked is False or run.get("status") == "rejected":
                feedback["rejected"] += 1
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
        config: dict[str, Any] | None = None,
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
                result["recipe_candidates"].append(
                    self.create_recipe_candidate(
                        self._generation_recipe_candidate_payload(run, selected_assets, batch_id),
                        config=config,
                    )
                )

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
                        self._generation_visual_system_candidate_payload(run, selected_assets, batch_id),
                        config=config,
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
            "source_candidate_id": row["source_candidate_id"],
            "source_reference_id": row["source_reference_id"],
            "payload": json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }

    def _recipe_evidence_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "recipe_id": row["recipe_id"],
            "evidence_type": row["evidence_type"],
            "source_candidate_id": row["source_candidate_id"],
            "source_generation_id": row["source_generation_id"],
            "source_reference_id": row["source_reference_id"],
            "payload": json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }

    def _visual_system_evidence_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "system_id": row["system_id"],
            "evidence_type": row["evidence_type"],
            "source_candidate_id": row["source_candidate_id"],
            "source_generation_id": row["source_generation_id"],
            "source_reference_id": row["source_reference_id"],
            "payload": json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }

    def _revision_from_row(self, entity_type: str, id_column: str, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "entity_type": entity_type,
            "entity_id": row[id_column],
            "action": row["action"],
            "source_candidate_id": row["source_candidate_id"],
            "source_generation_id": row["source_generation_id"],
            "target_entity_id": row["target_entity_id"],
            "scores": json_loads(row["scores_json"], {}),
            "before": json_loads(row["before_json"], {}),
            "after": json_loads(row["after_json"], {}),
            "diff": json_loads(row["diff_json"], {}),
            "reason": row["reason"],
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
            "parent_system_id": row["parent_system_id"],
            "merged_into_system_id": row["merged_into_system_id"],
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
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "parent_recipe_id": row["parent_recipe_id"],
            "merged_into_recipe_id": row["merged_into_recipe_id"],
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

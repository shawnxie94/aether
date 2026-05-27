from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ids import new_id, slugify
from .jsonio import json_dumps, json_loads
from .migrations import record_schema_version
from .storage_time import now_iso
from .validation import validate_generation_run, validate_prompt_record, validate_style


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

                create table if not exists prompt_records (
                  id text primary key,
                  source_prompt text not null,
                  style_id text,
                  target_generation_skill text,
                  constraints_json text not null default '{}',
                  intent_analysis_json text not null default '{}',
                  refined_prompt text not null,
                  negative_prompt text not null default '',
                  generation_params_json text not null default '{}',
                  variants_json text not null default '[]',
                  assumptions_json text not null default '[]',
                  created_at text not null
                );

                create table if not exists generation_runs (
                  id text primary key,
                  source_prompt text not null default '',
                  refined_prompt text not null,
                  negative_prompt text not null default '',
                  style_id text,
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
            self._ensure_column(conn, "generation_runs", "visual_review_json", "text not null default '{}'")
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
        record = {
            "id": payload.get("id") or new_id("sim"),
            "source_style_id": payload.get("source_style_id"),
            "candidate_style_id": payload["candidate_style_id"],
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
                    record["source_style_id"],
                    record["candidate_style_id"],
                    record["similarity_score"],
                    record["decision"],
                    json_dumps(record["matched_dimensions"]),
                    json_dumps(record["different_dimensions"]),
                    record["reason"],
                    record["created_at"],
                ),
            )
        return record

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

    def save_prompt_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_prompt_record(payload)
        record = {
            "id": payload.get("id") or new_id("prompt"),
            "source_prompt": payload["source_prompt"],
            "style_id": payload.get("style_id"),
            "target_generation_skill": payload.get("target_generation_skill"),
            "constraints": payload.get("constraints", {}),
            "intent_analysis": payload.get("intent_analysis", {}),
            "refined_prompt": payload["refined_prompt"],
            "negative_prompt": payload.get("negative_prompt", ""),
            "generation_params": payload.get("generation_params", {}),
            "variants": payload.get("variants", []),
            "assumptions": payload.get("assumptions", []),
            "created_at": payload.get("created_at", now_iso()),
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into prompt_records (
                  id, source_prompt, style_id, target_generation_skill, constraints_json,
                  intent_analysis_json, refined_prompt, negative_prompt, generation_params_json,
                  variants_json, assumptions_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["source_prompt"],
                    record["style_id"],
                    record["target_generation_skill"],
                    json_dumps(record["constraints"]),
                    json_dumps(record["intent_analysis"]),
                    record["refined_prompt"],
                    record["negative_prompt"],
                    json_dumps(record["generation_params"]),
                    json_dumps(record["variants"]),
                    json_dumps(record["assumptions"]),
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
        record = {
            "id": payload.get("id") or new_id("generation"),
            "source_prompt": payload.get("source_prompt", ""),
            "refined_prompt": payload["refined_prompt"],
            "negative_prompt": payload.get("negative_prompt", ""),
            "style_id": payload.get("style_id"),
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
                  id, source_prompt, refined_prompt, negative_prompt, style_id,
                  generation_skill, skill_params_json, skill_result_meta_json, visual_review_json,
                  outputs_json, status, feedback_json, error, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["source_prompt"],
                    record["refined_prompt"],
                    record["negative_prompt"],
                    record["style_id"],
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
        return current

    def get_generation_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from generation_runs where id = ?", (run_id,)).fetchone()
        return self._generation_from_row(row) if row else None

    def list_generation_runs(
        self,
        style_id: str | None = None,
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
        if review:
            runs = [run for run in runs if run.get("visual_review", {}).get("style_consistency") == review]
        return runs[:limit] if limit is not None and limit >= 0 else runs

    def generation_stats(self, style_id: str | None = None) -> dict[str, Any]:
        runs = self.list_generation_runs(style_id=style_id, limit=None)
        by_status: dict[str, int] = {}
        by_review: dict[str, int] = {}
        by_style: dict[str, dict[str, Any]] = {}
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

            liked = run.get("feedback", {}).get("liked")
            if liked is True or run.get("status") == "liked":
                feedback["liked"] += 1
                style_stats["liked"] += 1
            elif liked is False or run.get("status") == "rejected":
                feedback["rejected"] += 1
                style_stats["rejected"] += 1
            else:
                feedback["unrated"] += 1

            for deviation in run.get("visual_review", {}).get("deviations", []):
                if isinstance(deviation, str) and deviation:
                    deviations[deviation] = deviations.get(deviation, 0) + 1

        return {
            "total": len(runs),
            "by_status": by_status,
            "by_review": by_review,
            "feedback": feedback,
            "by_style": by_style,
            "common_deviations": [
                {"deviation": key, "count": count}
                for key, count in sorted(deviations.items(), key=lambda item: item[1], reverse=True)
            ],
        }

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

    def _generation_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_prompt": row["source_prompt"],
            "refined_prompt": row["refined_prompt"],
            "negative_prompt": row["negative_prompt"],
            "style_id": row["style_id"],
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

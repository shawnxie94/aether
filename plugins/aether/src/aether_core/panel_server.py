from __future__ import annotations

import gzip
import json
import mimetypes
import socket
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .config import LoadedConfig
from .panel_bundle import export_panel_bundle, import_panel_bundle
from .panel_export import ExportJobRegistry
from .panel_data import (
    collect_panel_favorites,
    collect_panel_recipes,
    collect_panel_summary,
    collect_panel_visual_assets,
    collect_panel_visual_systems,
    panel_etag,
)
from .panel_template import PANEL_HTML
from .storage import AetherStore


class PanelServer(ThreadingHTTPServer):
    config: LoadedConfig
    store: AetherStore
    # ``export_jobs`` is normally set by ``_bind_server`` in production.
    # The ``None`` default makes ad-hoc test servers work without having
    # to bind through the helper; the handler falls back to a fresh
    # registry if the attribute is still missing.
    export_jobs: "ExportJobRegistry | None" = None


class PanelRequestHandler(BaseHTTPRequestHandler):
    server: PanelServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/healthz", "/favicon.ico"}:
            self.send_response(HTTPStatus.OK)
            if parsed.path == "/":
                content_type = "text/html; charset=utf-8"
            elif parsed.path == "/healthz":
                content_type = "application/json"
            else:
                content_type = "image/x-icon"
            self.send_header("Content-Type", content_type)
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(PANEL_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/healthz":
            self._send_json({"ok": True})
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        # Per-section endpoints with ETag/304 support. Each one only walks
        # the rows it needs and reuses the per-section ETag helper, so
        # polling ``/api/panel-data/summary`` every few seconds is cheap
        # even on a multi-thousand-asset database.
        for path, sections, collector in (
            ("/api/panel-data/summary", ["summary"], collect_panel_summary),
            ("/api/visual-assets", ["visual_assets"], collect_panel_visual_assets),
            ("/api/visual-systems", ["visual_systems"], collect_panel_visual_systems),
            ("/api/recipes", ["recipes"], collect_panel_recipes),
            ("/api/favorites", ["favorites"], collect_panel_favorites),
        ):
            if parsed.path == path:
                self._send_etag_json(
                    lambda c=collector: collector(self.server.config, self.server.store),
                    sections,
                )
                return
        if parsed.path == "/api/export/status":
            self._export_status(parsed.query)
            return
        if parsed.path == "/api/export/download":
            self._export_download(parsed.query)
            return
        if parsed.path.startswith("/asset/"):
            self._send_asset(parsed.path.removeprefix("/asset/"))
            return
        if parsed.path == "/open":
            query = parse_qs(parsed.query)
            target = query.get("url", ["/"])[0]
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", target if target.startswith("/") else "/")
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/favorite":
            self._set_favorite()
            return
        if parsed.path == "/api/import":
            self._import_bundle(parsed.query)
            return
        if parsed.path == "/api/export":
            self._export_start()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _client_accepts_gzip(self) -> bool:
        """Return True when the client advertised gzip in Accept-Encoding."""
        header = self.headers.get("Accept-Encoding", "")
        if not header:
            return False
        # Parse the simple comma-separated list. ``gzip`` may appear as
        # ``gzip`` or ``gzip;q=0.x``. Reject explicit q=0 (disallowed).
        for raw_token in header.split(","):
            token = raw_token.strip().lower()
            if not token:
                continue
            params = [param.strip() for param in token.split(";")][1:]
            for param in params:
                if param.startswith("q="):
                    try:
                        if float(param.split("=", 1)[1]) == 0:
                            break
                    except ValueError:
                        continue
            else:
                if token.startswith("gzip"):
                    return True
        return False

    def _write_encoded(self, encoded: bytes, content_type: str) -> None:
        """Write a response body, gzip-encoding it when the client accepts it.

        Always sets ``Vary: Accept-Encoding`` so caches keep the right copy
        for gzip-aware and gzip-blind clients.
        """
        gzip_ok = self._client_accepts_gzip() and len(encoded) >= 512
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Vary", "Accept-Encoding")
        if gzip_ok:
            compressed = gzip.compress(encoded, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(compressed)))
            self.end_headers()
            self.wfile.write(compressed)
        else:
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    def _send_text(self, payload: str, content_type: str) -> None:
        self._write_encoded(payload.encode("utf-8"), content_type)

    def _send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._write_encoded(encoded, "application/json; charset=utf-8")

    def _send_etag_json(
        self,
        collector: Callable[[], Any],
        sections: list[str],
    ) -> None:
        """Send a JSON response with ETag/304 handling.

        ``collector`` returns the payload to serialize. ``sections`` is the
        list of section names that feed into the ETag (see
        :func:`aether_core.panel_data.panel_etag`). When the client sends
        an ``If-None-Match`` header that matches the current ETag, the
        response is a 304 with no body, so the panel can poll on a
        short interval without paying the full payload cost.
        """
        etag = panel_etag(self.server.store, sections)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            return
        encoded = json.dumps(collector(), ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("ETag", etag)
        self.send_header("Vary", "Accept-Encoding")
        if self._client_accepts_gzip() and len(encoded) >= 512:
            compressed = gzip.compress(encoded, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(compressed)))
            self.end_headers()
            self.wfile.write(compressed)
        else:
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    def _send_binary(self, payload: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _set_favorite(self) -> None:
        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return
        entity_type = payload.get("entity_type")
        entity_id = payload.get("entity_id")
        favorite = bool(payload.get("favorite"))
        if not isinstance(entity_type, str) or not isinstance(entity_id, str):
            self.send_error(HTTPStatus.BAD_REQUEST, "entity_type and entity_id are required")
            return
        if entity_type == "recipe":
            exists = self.server.store.get_recipe(entity_id, include_assets=False) is not None
        elif entity_type == "visual_system":
            exists = self.server.store.get_visual_system(entity_id, include_assets=False) is not None
        else:
            self.send_error(HTTPStatus.BAD_REQUEST, "Unsupported entity_type")
            return
        if not exists:
            self.send_error(HTTPStatus.NOT_FOUND, "Entity not found")
            return
        self._send_json(self.server.store.set_panel_favorite(entity_type, entity_id, favorite))

    def _export_start(self) -> None:
        """Kick off a background export job and return its handles.

        The actual zip build runs in a daemon thread inside
        :class:`ExportJobRegistry`. The panel polls
        ``/api/export/status`` and downloads the finished bundle from
        ``/api/export/download`` instead of blocking the request thread.
        """
        jobs = self._ensure_export_jobs()
        try:
            job = jobs.start(self.server.config, self.server.store)
        except RuntimeError as error:
            self.send_error(HTTPStatus.TOO_MANY_REQUESTS, str(error))
            return
        self._send_json(
            {
                "job_id": job.job_id,
                "status_url": f"/api/export/status?job_id={job.job_id}",
                "download_url": f"/api/export/download?job_id={job.job_id}",
            }
        )

    def _ensure_export_jobs(self) -> ExportJobRegistry:
        jobs = self.server.export_jobs
        if jobs is None:
            from .panel_export import ExportJobRegistry
            jobs = ExportJobRegistry()
            self.server.export_jobs = jobs
        return jobs

    def _export_status(self, query_string: str) -> None:
        """Return the JSON status of a background export job."""
        jobs = self._ensure_export_jobs()
        params = parse_qs(query_string)
        job_ids = params.get("job_id", [])
        if not job_ids:
            self.send_error(HTTPStatus.BAD_REQUEST, "job_id is required")
            return
        job = jobs.get(job_ids[0])
        if job is None:
            self.send_error(
                HTTPStatus.NOT_FOUND, "Export job not found or expired"
            )
            return
        self._send_json(jobs.to_status(job))

    def _export_download(self, query_string: str) -> None:
        """Stream the completed zip of a background export job."""
        params = parse_qs(query_string)
        job_ids = params.get("job_id", [])
        if not job_ids:
            self.send_error(HTTPStatus.BAD_REQUEST, "job_id is required")
            return
        jobs = self._ensure_export_jobs()
        job = jobs.get(job_ids[0])
        if job is None:
            self.send_error(
                HTTPStatus.NOT_FOUND, "Export job not found or expired"
            )
            return
        if job.status != "complete" or job.payload is None:
            self.send_error(
                HTTPStatus.CONFLICT,
                f"Export job is {job.status!r}, not ready for download",
            )
            return
        self._send_binary(job.payload, "application/zip", job.filename)

    def _import_bundle(self, query_string: str) -> None:
        mode = parse_qs(query_string).get("mode", ["merge"])[0]
        payload = self._read_body()
        if not payload:
            self.send_error(HTTPStatus.BAD_REQUEST, "Import bundle is required")
            return
        try:
            result = import_panel_bundle(self.server.config, self.server.store, payload, mode=mode)
        except ValueError as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        except OSError as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        self._send_json(result)

    def _send_asset(self, asset_id: str) -> None:
        asset = next((item for item in self.server.store.list_assets(limit=None) if item["id"] == asset_id), None)
        if not asset:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = Path(asset["asset_path"])
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = asset.get("mime_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def _bind_server(config: LoadedConfig, store: AetherStore, host: str, port: int) -> PanelServer:
    attempts = 1 if port == 0 else 20
    current_port = port
    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            server = PanelServer((host, current_port), PanelRequestHandler)
            server.config = config
            server.store = store
            server.export_jobs = ExportJobRegistry()
            return server
        except OSError as error:
            last_error = error
            if port == 0:
                break
            current_port += 1
    if last_error:
        raise last_error
    raise OSError("Unable to bind Aether panel server")


def run_panel(config: LoadedConfig, store: AetherStore, *, host: str, port: int, open_browser: bool) -> None:
    server = _bind_server(config, store, host, port)
    bound_host, bound_port = server.server_address
    url = f"http://{bound_host}:{bound_port}"
    print(json.dumps({"ok": True, "url": url, "host": bound_host, "port": bound_port}, ensure_ascii=False), flush=True)
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0

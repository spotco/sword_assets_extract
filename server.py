#!/usr/bin/env python3
"""Development server: serves static files and provides a /api/extract SSE endpoint
that runs the extraction pipeline for a given map name.

Usage:
    python server.py          # listens on http://localhost:5173/
"""
import http.server
import json
import subprocess
import sys
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

PORT = 5173
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "level_probe"))

from export_level_index import build_index


INDEX_PATH = ROOT / "extracted" / "web_levels" / "index.json"
VIEW_LOG_PATH = ROOT / "temp" / "web_level_viewer_debug.log"
VIEWER_TEMPLATE_PATH = ROOT / "web_level_viewer" / "index.template.html"


def ensure_level_index() -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = build_index(INDEX_PATH.parent)
    INDEX_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def render_viewer_html(level_root: str, *, api_root: str | None, static_site: bool) -> bytes:
    html = VIEWER_TEMPLATE_PATH.read_text(encoding="utf-8")
    api_attr = f' data-api-root="{api_root}"' if api_root else ""
    html = html.replace("__LEVEL_ROOT__", level_root)
    html = html.replace("__API_ROOT_ATTR__", api_attr)
    html = html.replace("__STATIC_SITE__", "true" if static_site else "false")
    return html.encode("utf-8")


def bundle_for_map(map_name: str) -> str:
    """Look up the bundle path from index.json, falling back to the standard convention."""
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        for level in data.get("levels", []):
            if level.get("mapName") == map_name:
                return level["bundle"]
    except Exception:
        pass
    return f"battle/map/{map_name}.unity3d"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/web_level_viewer/")
            self.end_headers()
            return
        if parsed.path in {"/web_level_viewer/", "/web_level_viewer/index.html"}:
            body = render_viewer_html("../extracted/web_levels", api_root="..", static_site=False)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/extracted/web_levels/index.json":
            ensure_level_index()
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/view-log":
            self._write_view_log()
            return
        if parsed.path == "/api/level-index":
            self._write_level_index()
            return

        if parsed.path != "/api/extract":
            self.send_error(404)
            return

        params = urllib.parse.parse_qs(parsed.query)
        map_name = (params.get("map") or [None])[0]
        if not map_name:
            self.send_error(400, "Missing map parameter")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        bundle = bundle_for_map(map_name)
        steps = [
            [sys.executable, "level_probe/extract_battle_grid.py", "--bundle", bundle],
            [sys.executable, "level_probe/dump_scene_layout.py", "--bundle", bundle],
            [sys.executable, "level_probe/export_grid_json.py", "--map", map_name],
            [sys.executable, "level_probe/export_mesh_json.py", "--map", map_name],
            [sys.executable, "level_probe/export_level_index.py"],
        ]

        try:
            for cmd in steps:
                self._sse("log", "$ " + " ".join(cmd[1:]))
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(ROOT),
                )
                for line in proc.stdout:
                    self._sse("log", line.rstrip())
                proc.wait()
                if proc.returncode != 0:
                    self._sse("error", f"Process exited with code {proc.returncode}")
                    return
            self._sse("done", map_name)
        except Exception as exc:
            try:
                self._sse("error", str(exc))
            except Exception:
                pass

    def _sse(self, event: str, data: str):
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        self.wfile.write(payload.encode())
        self.wfile.flush()

    def _write_view_log(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 64 * 1024:
                self.send_error(400, "Invalid log payload size")
                return
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "client": self.client_address[0] if self.client_address else "",
                "event": payload.get("event"),
                "details": payload.get("details"),
            }
            VIEW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with VIEW_LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self.send_response(204)
            self.end_headers()
        except Exception as exc:
            self.send_error(400, str(exc))

    def _write_level_index(self):
        try:
            ensure_level_index()
            payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(500, str(exc))

    def log_message(self, fmt, *args):
        try:
            path = str(args[0]).split()[1] if args else ""
            if path.startswith("/api/") or not path.startswith("/extracted/"):
                super().log_message(fmt, *args)
        except Exception:
            super().log_message(fmt, *args)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = Server(("", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}/  —  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

"""Local-only mock report API for exercising the client upload workflow."""

from __future__ import annotations

import argparse
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

REPORTS: dict[str, dict[str, Any]] = {}
MAX_BODY_BYTES = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "SysGapLocalMock/1.0"

    def _send_json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "mode": "local mock; in-memory only"})
            return
        if self.path.startswith("/report/"):
            report_id = self.path[len("/report/"):]
            report = REPORTS.get(report_id)
            if report is None:
                self._send_json(404, {"error": "report not found in this server session"})
                return
            self._send_json(200, report)
            return
        if self.path == "/__shutdown":
            self._send_json(200, {"status": "stopping"})
            self.server.shutdown()
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/v1/reports":
            self._send_json(404, {"error": "not found"})
            return
        content_length = self.headers.get("Content-Length")
        try:
            size = int(content_length or "")
        except ValueError:
            self._send_json(411, {"error": "Content-Length is required"})
            return
        if size <= 0 or size > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request body size is invalid or exceeds 2 MiB"})
            return
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "request body must be valid UTF-8 JSON"})
            return
        if not isinstance(payload, dict):
            self._send_json(422, {"error": "request must be a JSON object"})
            return
        if (
            payload.get("schema_version") != 1
            or not isinstance(payload.get("task"), str)
            or not isinstance(payload.get("hardware"), dict)
            or not isinstance(payload.get("telemetry"), dict)
            or payload["telemetry"].get("kind") != "inventory_assessment"
        ):
            self._send_json(422, {"error": "payload does not match the local client contract"})
            return

        report_id = str(uuid.uuid4())
        REPORTS[report_id] = payload
        report_url = f"http://127.0.0.1:{self.server.server_port}/report/{report_id}"
        self._send_json(201, {"report_id": report_id, "report_url": report_url})
        hardware = payload["hardware"]
        component_count = sum(bool(hardware.get(key)) for key in ("cpu", "gpus", "memory", "storage", "motherboard"))
        print(
            f"Accepted in-memory report {report_id}: task={payload['task']}, "
            f"detected component groups={component_count}. No data written to disk.",
            flush=True,
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid logging request bodies or client/device information.
        print(f"mock-api: {format % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the localhost-only SysGap mock report API.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(
        f"Local mock API listening at http://127.0.0.1:{args.port} "
        "(loopback only; reports are held in memory and cleared at shutdown).",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Local mock API stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

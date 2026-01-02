"""Minimal local web server for the JobTailor UI."""

from __future__ import annotations

import json
import sys
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .core import slugify_token, tailor_documents

ROOT_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT_DIR / "assets" / "ui"
OUTPUT_DIR = ROOT_DIR / "outputs" / "ui_runs"
UPLOAD_DIR = OUTPUT_DIR / "uploads"


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_filename(name: str, fallback: str = "upload") -> str:
    base = slugify_token(Path(name).stem) or fallback
    suffix = Path(name).suffix or ".pdf"
    return f"{base}{suffix}"


def _format_audit_preview(audit_json: dict[str, Any]) -> str:
    missing = audit_json.get("missing_keywords", [])
    risks = audit_json.get("formatting_risks", [])
    edits = audit_json.get("proposed_edits", [])
    lines = ["ATS AUDIT"]

    if missing:
        lines.append("\nMissing keywords:")
        lines.extend([f"- {item}" for item in missing[:12]])
    if risks:
        lines.append("\nFormatting risks:")
        lines.extend([f"- {item}" for item in risks[:12]])
    if edits:
        lines.append("\nProposed edits:")
        lines.extend([f"- {item}" for item in edits[:12]])

    return "\n".join(lines).strip()


class UiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._send_json({"status": "ok"})
            return
        if self.path in {"/", "/ui", "/ui/"}:
            self.path = "/assets/ui/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"status": "error", "message": "Expected multipart form data."}, status=400)
            return

        length = self.headers.get("Content-Length")
        if not length or not length.isdigit():
            self._send_json({"status": "error", "message": "Missing Content-Length."}, status=411)
            return

        body = self.rfile.read(int(length))
        fields, files = self._parse_multipart(content_type, body)

        cv_field = files.get("cv_file")
        if not cv_field or not cv_field.get("filename"):
            self._send_json({"status": "error", "message": "Upload a CV file."}, status=400)
            return

        job_source = (fields.get("job_source") or "url").strip().lower()
        job_url = (fields.get("job_url") or "").strip()
        job_text = (fields.get("job_text") or "").strip()

        if job_source == "url" and not job_url:
            self._send_json({"status": "error", "message": "Provide a job URL."}, status=400)
            return
        if job_source == "text" and not job_text:
            self._send_json({"status": "error", "message": "Provide job description text."}, status=400)
            return

        include_cover_letter = _parse_bool(fields.get("include_cover_letter"), default=True)
        make_pdf = _parse_bool(fields.get("make_pdf"), default=True)
        debug_artifacts = _parse_bool(fields.get("debug_artifacts"), default=False)
        dry_run = _parse_bool(fields.get("dry_run"), default=False)
        quiet = _parse_bool(fields.get("quiet"), default=False)

        model = (fields.get("model") or "gpt-5-mini").strip()
        temp_raw = fields.get("temperature") or "0.2"
        try:
            temperature = float(temp_raw)
        except ValueError:
            temperature = 0.2

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        cv_filename = _safe_filename(cv_field["filename"])
        cv_path = UPLOAD_DIR / f"{timestamp}_{cv_filename}"
        with open(cv_path, "wb") as handle:
            handle.write(cv_field["content"])

        job_text_path = None
        job_urls: list[str] | None = None

        if job_source == "text":
            job_text_path = UPLOAD_DIR / f"{timestamp}_job.txt"
            job_text_path.write_text(job_text, encoding="utf-8")
        else:
            job_urls = [job_url]

        try:
            created_paths = tailor_documents(
                cv_file=cv_path,
                job_urls=job_urls,
                job_text_file=job_text_path,
                out_dir=OUTPUT_DIR,
                model=model,
                temperature=temperature,
                dry_run=dry_run,
                make_pdf=make_pdf,
                verbose=not quiet,
                debug_artifacts=debug_artifacts,
                include_cover_letter=include_cover_letter,
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json({"status": "error", "message": str(exc)}, status=500)
            return

        output_dir = created_paths[0].parent if created_paths else OUTPUT_DIR
        cv_preview = ""
        cover_preview = ""
        audit_preview = ""

        for path in created_paths:
            if path.name.endswith("_cv.md"):
                cv_preview = path.read_text(encoding="utf-8").strip()
            if path.name.endswith("_cover_letter.md"):
                cover_preview = path.read_text(encoding="utf-8").strip()
            if path.name.endswith("_ats_audit.json"):
                audit_json = json.loads(path.read_text(encoding="utf-8"))
                audit_preview = _format_audit_preview(audit_json)

        payload = {
            "status": "ok",
            "created_files": [str(p.relative_to(ROOT_DIR)) for p in created_paths],
            "output_dir": str(output_dir.relative_to(ROOT_DIR)),
            "preview": {
                "cv": cv_preview,
                "cover": cover_preview,
                "audit": audit_preview,
            },
        }

        self._send_json(payload)

    def _parse_multipart(self, content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        boundary_token = "boundary="
        if boundary_token not in content_type:
            return {}, {}

        boundary = content_type.split(boundary_token, 1)[1].strip()
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]

        delimiter = f"--{boundary}".encode("utf-8")
        sections = body.split(delimiter)

        fields: dict[str, str] = {}
        files: dict[str, dict[str, Any]] = {}

        for section in sections:
            if not section or section in {b"--\r\n", b"--"}:
                continue
            if section.startswith(b"\r\n"):
                section = section[2:]
            if section.endswith(b"\r\n"):
                section = section[:-2]

            header_blob, _, content = section.partition(b"\r\n\r\n")
            if not header_blob:
                continue

            headers: dict[str, str] = {}
            for line in header_blob.split(b"\r\n"):
                if b":" not in line:
                    continue
                name, value = line.split(b":", 1)
                headers[name.decode("utf-8", errors="replace").lower()] = value.decode(
                    "utf-8", errors="replace"
                ).strip()

            disposition = headers.get("content-disposition", "")
            disp_parts = [part.strip() for part in disposition.split(";") if part.strip()]
            disp_params: dict[str, str] = {}
            for part in disp_parts[1:]:
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                disp_params[key.strip()] = value

            name = disp_params.get("name")
            filename = disp_params.get("filename")
            if not name:
                continue

            if filename:
                files[name] = {"filename": filename, "content": content}
            else:
                fields[name] = content.decode("utf-8", errors="replace").strip()

        return fields, files


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    load_dotenv()
    server = ThreadingHTTPServer((host, port), UiHandler)
    print(f"JobTailor UI server running at http://{host}:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    run()

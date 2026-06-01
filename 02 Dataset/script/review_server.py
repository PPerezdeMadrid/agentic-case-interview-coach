import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_APP_PATH = "/script/review_static/index.html"
DEFAULT_PDF = "Duke-Casebook-2017-Profitability-18.pdf"
PDF_GLOBS = [
    "*.pdf",
]
JSON_GLOBS = [
    "script/output/**/*.json",
    "duke_data_processed/**/*.json",
]


def relative_posix(path: Path) -> str:
    return path.relative_to(BASE_DIR).as_posix()


def discover_files():
    pdfs = []
    for pattern in PDF_GLOBS:
        pdfs.extend(BASE_DIR.glob(pattern))

    json_files = []
    for pattern in JSON_GLOBS:
        json_files.extend(BASE_DIR.glob(pattern))

    pdf_entries = [
        {
            "label": path.name,
            "path": relative_posix(path),
        }
        for path in sorted(set(pdfs))
        if path.is_file()
    ]

    json_entries = []
    for path in sorted(set(json_files)):
        if not path.is_file():
            continue

        rel_path = relative_posix(path)
        json_entries.append({
            "label": path.name,
            "path": rel_path,
            "suggested_pdf": suggest_pdf_for_json(rel_path),
        })

    return {
        "default_pdf": DEFAULT_PDF,
        "pdfs": pdf_entries,
        "jsons": json_entries,
    }


def suggest_pdf_for_json(json_relative_path: str) -> str | None:
    lowered = json_relative_path.lower()

    if "duke_casebook_2017_profitability_18" in lowered:
        return DEFAULT_PDF

    if "yachtco" in lowered:
        return "YachtCo.pdf"

    return None


def summarize_json(data):
    if isinstance(data, list):
        pages = [item.get("source_page") for item in data if isinstance(item, dict) and item.get("source_page") is not None]
        return {
            "format": "raw_pages",
            "item_count": len(data),
            "min_page": min(pages) if pages else None,
            "max_page": max(pages) if pages else None,
        }

    if isinstance(data, dict) and isinstance(data.get("case_content"), list):
        blocks = data["case_content"]
        pages = [item.get("source_page") for item in blocks if isinstance(item, dict) and item.get("source_page") is not None]
        return {
            "format": "structured_case",
            "item_count": len(blocks),
            "min_page": min(pages) if pages else None,
            "max_page": max(pages) if pages else None,
        }

    return {
        "format": "unknown",
        "item_count": None,
        "min_page": None,
        "max_page": None,
    }


class ReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", DEFAULT_APP_PATH)
            self.end_headers()
            return

        if parsed.path == "/api/files":
            self._send_json(discover_files())
            return

        if parsed.path == "/api/json":
            self._serve_json_file(parsed.query)
            return

        self.path = parsed.path
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/json/save":
            self._save_json_file()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint.")

    def _serve_json_file(self, query_string: str):
        params = parse_qs(query_string)
        rel_path = params.get("path", [None])[0]

        if not rel_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing 'path' query parameter.")
            return

        target = self._resolve_user_path(rel_path)
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "JSON file not found.")
            return

        if target.suffix.lower() != ".json":
            self.send_error(HTTPStatus.BAD_REQUEST, "Requested file is not a JSON file.")
            return

        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        payload = {
            "path": relative_posix(target),
            "dir": target.relative_to(BASE_DIR).parent.as_posix(),
            "summary": summarize_json(data),
            "data": data,
        }
        self._send_json(payload)

    def _save_json_file(self):
        try:
            payload = self._read_request_json()
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        rel_path = payload.get("path")
        raw_content = payload.get("content")

        if not rel_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing 'path' in request body.")
            return

        if not isinstance(raw_content, str):
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing JSON text in 'content'.")
            return

        try:
            target = self._resolve_user_path(rel_path)
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "JSON file not found.")
            return

        if target.suffix.lower() != ".json":
            self.send_error(HTTPStatus.BAD_REQUEST, "Requested file is not a JSON file.")
            return

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})")
            return

        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        response = {
            "saved": True,
            "path": relative_posix(target),
            "dir": target.relative_to(BASE_DIR).parent.as_posix(),
            "summary": summarize_json(data),
            "data": data,
        }
        self._send_json(response)

    def _read_request_json(self):
        content_length_header = self.headers.get("Content-Length")
        if not content_length_header:
            raise ValueError("Missing Content-Length header.")

        try:
            content_length = int(content_length_header)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc

        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid request JSON: {exc.msg}") from exc

    def _resolve_user_path(self, raw_path: str) -> Path:
        rel_path = Path(unquote(raw_path)).as_posix().lstrip("/")
        candidate = (BASE_DIR / rel_path).resolve()

        if BASE_DIR not in candidate.parents and candidate != BASE_DIR:
            raise ValueError("Path escapes base directory.")

        return candidate

    def _send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Local reviewer for case JSON against source PDFs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    mimetypes.add_type("application/pdf", ".pdf")

    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"Review server running at http://{args.host}:{args.port}{DEFAULT_APP_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()

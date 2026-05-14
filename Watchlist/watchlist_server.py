import json
import mimetypes
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


HERE = Path(__file__).resolve().parent
WATCHLIST_PATH = HERE / "stock_watchlist_auto.json"
NOTES_PATH = HERE / "notes_auto.json"
CONFIG_PATH = HERE / "watchlist_config.json"
DEFAULT_BACKUP_DIR = HERE / "backups"
HTML_PATH = HERE / "stock_watchlist.html"
HOST = "127.0.0.1"
PORT = 8765

_update_lock = threading.Lock()


def read_json_file(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json_file(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def normalize_watchlist_data(data):
    if not isinstance(data, dict):
        return {"hot": {}, "waiting": {}, "holding": {}}
    if any(k in data for k in ("hot", "waiting", "holding")):
        hot = data.get("hot") if isinstance(data.get("hot"), dict) else {}
        waiting = data.get("waiting") if isinstance(data.get("waiting"), dict) else {}
        holding = data.get("holding") if isinstance(data.get("holding"), dict) else {}
        return {"hot": hot, "waiting": waiting, "holding": holding}
    return {"hot": data, "waiting": {}, "holding": {}}

def read_watchlist_data():
    return normalize_watchlist_data(read_json_file(WATCHLIST_PATH, {}))

def read_config():
    data = read_json_file(CONFIG_PATH, {})
    if not isinstance(data, dict):
        return {}
    return data

def backup_dir():
    raw = read_config().get("backupDir")
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_BACKUP_DIR

def backup_watchlist(days=7):
    if not WATCHLIST_PATH.exists():
        return None
    target_dir = backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"stock_watchlist_auto_{stamp}.json"
    shutil.copy2(WATCHLIST_PATH, target)
    cutoff = datetime.now().timestamp() - days * 86400
    for old in target_dir.glob("stock_watchlist_auto_*.json"):
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    return target


def parse_perf_data():
    html = HTML_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"/\* __PERF_DATA__ \*/\s*let perfData\s*=\s*(\{[\s\S]*?\});\s*/\* __PERF_DATA_END__ \*/",
        html,
    )
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


class Handler(BaseHTTPRequestHandler):
    server_version = "WatchlistServer/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return True
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return False

    def read_body_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/watchlist":
            self.send_json(200, read_watchlist_data())
            return
        if parsed.path == "/api/notes":
            self.send_json(200, read_json_file(NOTES_PATH, {}))
            return
        if parsed.path == "/api/status":
            self.send_json(
                200,
                {
                    "ok": True,
                    "backupDir": str(backup_dir()),
                    "watchlist": WATCHLIST_PATH.name,
                    "notes": NOTES_PATH.name,
                },
            )
            return
        if parsed.path == "/api/config":
            cfg = read_config()
            cfg["backupDir"] = str(backup_dir())
            self.send_json(200, cfg)
            return
        if parsed.path == "/api/perf":
            self.send_json(200, parse_perf_data())
            return
        if parsed.path == "/api/backups":
            bdir = backup_dir()
            backups = []
            if bdir.exists():
                for f in sorted(
                    bdir.glob("stock_watchlist_auto_*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    m = re.match(
                        r"stock_watchlist_auto_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json",
                        f.name,
                    )
                    label = f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}" if m else f.name
                    size = f.stat().st_size
                    size_str = f"{size} B" if size < 1024 else f"{size // 1024} KB"
                    backups.append({"name": f.name, "label": label, "sizeStr": size_str})
            self.send_json(200, {"backups": backups})
            return

        rel = unquote(parsed.path.lstrip("/") or "stock_watchlist.html")
        target = (HERE / rel).resolve()
        try:
            target.relative_to(HERE)
        except ValueError:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/watchlist":
            try:
                data = self.read_body_json()
                if not isinstance(data, dict):
                    raise ValueError("watchlist must be an object")
                write_json_file(WATCHLIST_PATH, normalize_watchlist_data(data))
                self.send_json(200, {"ok": True})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/notes":
            try:
                data = self.read_body_json()
                if not isinstance(data, dict):
                    raise ValueError("notes must be an object")
                write_json_file(NOTES_PATH, data)
                self.send_json(200, {"ok": True})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/config":
            try:
                data = self.read_body_json()
                if not isinstance(data, dict):
                    raise ValueError("config must be an object")
                backup = str(data.get("backupDir", "")).strip()
                if not backup:
                    raise ValueError("backupDir is required")
                path = Path(backup).expanduser().resolve()
                path.mkdir(parents=True, exist_ok=True)
                test = path / ".watchlist_write_test"
                test.write_text("ok", encoding="utf-8")
                test.unlink(missing_ok=True)
                cfg = read_config()
                cfg["backupDir"] = str(path)
                write_json_file(CONFIG_PATH, cfg)
                self.send_json(200, {"ok": True, "backupDir": str(path)})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc), "backupDir": str(backup_dir())})
            return

        if parsed.path == "/api/restore":
            try:
                data = self.read_body_json()
                filename = data.get("file", "").strip()
                if not re.fullmatch(r"stock_watchlist_auto_\d{8}_\d{6}\.json", filename):
                    raise ValueError("invalid filename")
                src = backup_dir() / filename
                if not src.exists():
                    raise FileNotFoundError(f"{filename} not found")
                if WATCHLIST_PATH.exists():
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    shutil.copy2(WATCHLIST_PATH, backup_dir() / f"stock_watchlist_auto_{stamp}.json")
                shutil.copy2(src, WATCHLIST_PATH)
                self.send_json(200, {"ok": True})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/update_perf":
            if not _update_lock.acquire(blocking=False):
                self.send_json(409, {"ok": False, "error": "update already running"})
                return
            try:
                proc = subprocess.run(
                    [sys.executable, str(HERE / "update_perf.py")],
                    cwd=str(HERE),
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                )
                self.send_json(
                    200 if proc.returncode == 0 else 500,
                    {
                        "ok": proc.returncode == 0,
                        "returncode": proc.returncode,
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                        "perfData": parse_perf_data(),
                    },
                )
            except Exception as exc:
                self.send_json(500, {"ok": False, "error": str(exc), "perfData": parse_perf_data()})
            finally:
                _update_lock.release()
            return

        self.send_error(404)


def main():
    url = f"http://{HOST}:{PORT}/stock_watchlist.html"
    backup_path = backup_watchlist()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Watchlist server: {url}")
    if backup_path:
        print(f"Startup backup: {backup_path}")
        print("Keeping all backups within 7 days.")
    else:
        print("Startup backup: skipped (stock_watchlist_auto.json not found).")
    print("Close this window to stop the server.")
    webbrowser.open(url)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

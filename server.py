"""Unified Production and Development Server for PolicyNest.

Serves both the Embarko-based frontend static site and the production copilot_api backend
on a single port, eliminating CORS complications in standalone deployments (Docker, Railway, etc.).

Routes:
- /api/* -> Handled by copilot_api.main.H
- /*     -> Static files served from policynest_mvp/site/
"""
import os
import sys
import time
import secrets
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "policynest_mvp" / "site"
API_DIR = ROOT / "policynest_mvp" / "copilot_api"

sys.path.insert(0, str(API_DIR))
import main as api_module
import config

PORT = int(os.environ.get("PORT", "8000"))
HOST = "0.0.0.0"


class UnifiedHandler(api_module.H, SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=str(SITE_DIR), **kwargs)

    def do_OPTIONS(self):
        if self.path.startswith("/api/"):
            return api_module.H.do_OPTIONS(self)
        return SimpleHTTPRequestHandler.do_OPTIONS(self)

    def do_GET(self):
        if self.path.startswith("/api/") or self.path == "/api":
            return api_module.H.do_GET(self)
        # Serve index.html for root or client routes
        clean_path = self.path.split("?")[0].lstrip("/")
        if not clean_path or not (SITE_DIR / clean_path).is_file():
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if self.path.startswith("/api/"):
            return api_module.H.do_POST(self)
        self.send_error(405, "Method Not Allowed")

    def log_message(self, format, *args):
        if os.environ.get("QUIET_LOGS") == "1":
            return
        super().log_message(format, *args)


def run():
    api_module.auth.init_db()
    api_module.workflows.init()
    api_module.telemetry.init()
    server = ThreadingHTTPServer((HOST, PORT), UnifiedHandler)
    print(f"PolicyNest Unified Server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()

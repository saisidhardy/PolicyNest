"""Start static app and API with durable local demo storage. No live AI calls by default."""
from pathlib import Path
import argparse
import functools
import os
import secrets
import sys
import threading
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]

def configure():
    local=ROOT/'.local';local.mkdir(exist_ok=True)
    key=local/'jwt.key'
    if not key.exists():key.write_text(secrets.token_urlsafe(48),encoding='ascii')
    os.environ.setdefault('JWT_SECRET',key.read_text(encoding='ascii'))
    os.environ.setdefault('POLICYNEST_DB_PATH',str(local/'policynest.sqlite3'))
    os.environ['POLICYNEST_SKIP_DOTENV']='1'
    sys.path.insert(0,str(ROOT/'policynest_mvp'/'copilot_api'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--ai',action='store_true');a=p.parse_args()
    configure()
    if not a.ai:os.environ['ANTHROPIC_API_KEY']=''
    import main as api
    api.auth.init_db();api.workflows.init();api.telemetry.init()
    server=ThreadingHTTPServer(('127.0.0.1',8787),api.H)
    class QuietStatic(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    static=ThreadingHTTPServer(('127.0.0.1',8000),functools.partial(QuietStatic,directory=str(ROOT/'policynest_mvp'/'site')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    print('PolicyNest: http://localhost:8000 · API: http://localhost:8787 · AI: '+('configured provider' if a.ai else 'deterministic retrieval'),flush=True)
    try:static.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.shutdown();static.server_close();server.server_close();api.rag.close()

if __name__=='__main__':main()

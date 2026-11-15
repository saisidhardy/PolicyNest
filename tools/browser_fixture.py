"""Isolated synthetic browser-test backend; credentials arrive over stdin and are never logged."""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'policynest_mvp'/'copilot_api'))
config=json.loads(sys.stdin.readline())
temp=tempfile.TemporaryDirectory(prefix='policynest-browser-')
os.environ['POLICYNEST_DB_PATH']=str(Path(temp.name)/'test.sqlite3')
os.environ['JWT_SECRET']=secrets.token_urlsafe(48)
os.environ['ANTHROPIC_API_KEY']=''
os.environ['POLICYNEST_SKIP_DOTENV']='1'
import main
reviewer=main.auth.register('reviewer@example.test',config['password'],'Test Reviewer')
admin=main.auth.register('admin@example.test',config['password'],'Test Admin')
with main.auth._db() as db:
    db.execute("UPDATE users SET role='reviewer' WHERE id=?",(reviewer['id'],))
    db.execute("UPDATE users SET role='admin' WHERE id=?",(admin['id'],))
server=ThreadingHTTPServer(('127.0.0.1',8788),main.H)
threading.Thread(target=lambda:(sys.stdin.readline(),server.shutdown()),daemon=True).start()
print(json.dumps({'ready':True,'reviewer':reviewer['id']}),flush=True)
try:server.serve_forever()
finally:main.rag.close();server.server_close();temp.cleanup()

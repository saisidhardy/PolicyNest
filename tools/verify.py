"""Record actual verification output. --browser requires run_local.py serving port 8000."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--browser',action='store_true');args=p.parse_args()
checks=[('backend',[sys.executable,'tools/run_backend_tests.py']),('static',[sys.executable,'tools/check_pack.py']),('explanations',['node','tools/test_explanations.mjs']),('engine',['node','eval/run_eval.js','policynest_mvp/PolicyNest.html','04_DATASETS','eval/out']),('rag',[sys.executable,'eval/run_rag.py'])]
if args.browser:checks += [('assistant_browser',['node','tools/test_assistant.mjs']),('integrated_browser',['node','tools/test_integrated.mjs']),('T1_T10',[sys.executable,'tools/t1_t10.py','http://localhost:8000'])]
out=ROOT/'test-results';out.mkdir(exist_ok=True)
results=[]
for name,cmd in checks:
    print('RUN '+name,flush=True);started=time.time()
    try:
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=480,env=dict(os.environ,PYTHONIOENCODING='utf-8'))
        (out/(name+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
        row={'name':name,'exit_code':r.returncode,'seconds':round(time.time()-started,2),'log':'test-results/'+name+'.log'}
    except subprocess.TimeoutExpired:
        row={'name':name,'exit_code':124,'seconds':480,'error':'Timed out; not verified'}
    results.append(row);print(('PASS ' if row['exit_code']==0 else 'FAIL ')+name,flush=True)
    (ROOT/'eval'/'out'/'verification.json').write_text(json.dumps({'run_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':results},indent=2),encoding='utf-8')
sys.exit(any(r['exit_code'] for r in results))

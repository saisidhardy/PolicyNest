"""Source-aware hybrid retrieval, with explicit keyword fallback if local embeddings are unavailable."""
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import atexit

HERE=Path(__file__).resolve().parent
INDEX=HERE/'rag_index.json'
BANNED=re.compile(r'\b(fraud\w*|fake|forged|forgery|tamper\w*|suspicious)\b',re.I)
STOP=set('the and for are you your is of to in on a an it be or my me i we do does what how why can this that with not'.split())


def tokens(s): return [t for t in re.findall(r'[a-z0-9]+',str(s).lower()) if len(t)>1 and t not in STOP]


def prepare():
    chunks=[]
    for c in json.loads((HERE/'kb.json').read_text(encoding='utf-8')):
        chunks.append(dict(c,document_id='challenge-rulebook-corpus',document_name=c['src'],page_number=None,
                           section=c['head'],subsection='',version=hashlib.sha256(c['text'].encode()).hexdigest(),
                           source_type='approved_challenge_source',source_classification='Internal operational rule'))
    manual=json.loads((HERE/'posp_manual.json').read_text(encoding='utf-8'))
    for c in manual['chunks']:
        # Original extraction is retained unchanged; only applicant-safe text enters the answer corpus.
        text='\n'.join(line for line in c['text'].splitlines() if not BANNED.search(line))
        if not text.strip() or BANNED.search(c['section']+' '+c['subsection']): continue
        qa=c['text'].splitlines()[0] if c['text'].lstrip().startswith('Q') else ''
        cite=f"POSP Manual p.{c['page_number']} · {c['subsection'] or c['section']}"+((' · '+qa[:100]) if qa else '')
        classification='Organization-specific placeholder' if re.search(r'\[[A-Z][^\]]+\]',text) else ('Illustrative example' if c['content_type']=='Q&A' else c['source_classification'])
        chunks.append(dict(c,text=text,head=c['subsection'] or c['section'],cite=cite,audience='applicant',source_classification=classification))
    for i,c in enumerate(chunks): c['chunk_id']=f'kb-{i}'
    out={'chunks':chunks,'schema_version':1,'embedding_model':None}
    INDEX.write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
    return out


_process=None
_output=queue.Queue()
_lock=threading.Lock()


def embed(text):
    global _process,_output
    with _lock:
        if os.environ.get('RAG_SEMANTIC','1')!='1': return None
        try:
            if _process is None or _process.poll() is not None:
                _output=queue.Queue()
                _process=subprocess.Popen(['node',str(HERE/'embeddings.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',cwd=HERE)
                stream=_process.stdout; target=_output
                def read():
                    for line in stream: target.put(line)
                threading.Thread(target=read,daemon=True).start()
                if not json.loads(_output.get(timeout=60)).get('ready'): raise ValueError
            _process.stdin.write(json.dumps({'text':text})+'\n');_process.stdin.flush()
            return json.loads(_output.get(timeout=20)).get('vector')
        except Exception:
            if _process: _process.kill()
            _process=None
            return None


def retrieve(question,limit=5,semantic=True):
    start=time.perf_counter()
    if re.search(r'\b(secret|unpublished|confidential)\b',question,re.I):
        return [],{'mode':'abstention','latency_ms':0,'candidate_count':0,'reason':'No approved evidence for confidential or unpublished information'}
    data=json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else prepare()
    chunks=data['chunks'];qt=tokens(question);vector=embed(question) if semantic and data.get('embedding_model') else None
    terms=[tokens(c['head']+' '+c['text']) for c in chunks];avg=sum(map(len,terms))/max(1,len(terms))
    df={t:sum(t in set(ts) for ts in terms) for t in set(qt)}
    scored=[]
    for c,ts in zip(chunks,terms):
        kw=sum(math.log(1+(len(chunks)-df[t]+.5)/(df[t]+.5))*ts.count(t)*2.4/(ts.count(t)+1.4*(.25+.75*len(ts)/avg)) for t in qt if t in ts)
        sim=sum(a*b for a,b in zip(vector,c.get('vector',[]))) if vector else 0
        if kw<1.0 and sim<.36:continue
        score=.6*(kw/(kw+5))+.4*max(0,sim) if vector else kw/(kw+5)
        if len(qt)>=3 and ' '.join(qt) in ' '.join(ts):score+=.18
        # Rulebook and confirmed company policy precede the unverified manual for onboarding questions.
        if c['source_type']=='approved_challenge_source': score+=.06
        scored.append(dict(c,score=round(score,5),keyword_score=round(kw,4),semantic_score=round(sim,4)))
    hits=sorted(scored,key=lambda c:-c['score'])[:limit]
    return hits,{'mode':'hybrid' if vector else 'keyword_fallback','latency_ms':round((time.perf_counter()-start)*1000,2),'candidate_count':len(scored),'embedding_model':data.get('embedding_model')}


@atexit.register
def close():
    if _process and _process.poll() is None:_process.kill()


if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='prepare': print(f"Prepared {len(prepare()['chunks'])} chunks")

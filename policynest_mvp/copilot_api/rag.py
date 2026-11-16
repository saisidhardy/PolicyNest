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
import logging

log=logging.getLogger('policynest.rag')

HERE=Path(__file__).resolve().parent
INDEX=HERE/'rag_index.json'
BANNED=re.compile(r'\b(fraud\w*|fake|forged|forgery|tamper\w*|suspicious)\b',re.I)
# Manual passages that contradict the rulebook or this app (exam pass mark 35% vs 50%; passport-size photo rule vs a selfie)
# never reach an applicant answer. The rulebook and the app's facts take precedence.
CONTRADICTS=re.compile(r'minimum score of 35\s?%|passport[- ]size',re.I)
SCHEMA=2
STOP=set('the and for are you your is of to in on a an it be or my me i we do does what how why can this that with not'.split())


def tokens(s): return [t for t in re.findall(r'[a-z0-9]+',str(s).lower()) if len(t)>1 and t not in STOP]


def prepare():
    chunks=[]
    for c in json.loads((HERE/'kb.json').read_text(encoding='utf-8')):
        chunks.append(dict(c,document_id='challenge-rulebook-corpus',document_name=c['src'],page_number=None,
                           section=c['head'],subsection='',version=hashlib.sha256(c['text'].encode()).hexdigest(),
                           source_type='approved_challenge_source',source_classification='Internal operational rule'))
    degraded=False
    try: manual=json.loads((HERE/'posp_manual.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        log.warning('posp_manual.json missing or unreadable: using the rulebook passages only (index not written)'); manual={'chunks':[]}; degraded=True
    for c in manual['chunks']:
        # Original extraction is retained unchanged; only applicant-safe text enters the answer corpus.
        text='\n'.join(line for line in c['text'].splitlines() if not BANNED.search(line))
        if not text.strip() or BANNED.search(c['section']+' '+c['subsection']) or CONTRADICTS.search(text): continue
        qa=c['text'].splitlines()[0] if c['text'].lstrip().startswith('Q') else ''
        cite=f"POSP Manual p.{c['page_number']} · {c['subsection'] or c['section']}"+((' · '+qa[:100]) if qa else '')
        classification='Organization-specific placeholder' if re.search(r'\[[A-Z][^\]]+\]',text) else ('Illustrative example' if c['content_type']=='Q&A' else c['source_classification'])
        chunks.append(dict(c,text=text,head=c['subsection'] or c['section'],cite=cite,audience='applicant',source_classification=classification))
    for i,c in enumerate(chunks): c['chunk_id']=f'kb-{i}'
    out={'chunks':chunks,'schema_version':SCHEMA,'embedding_model':None}
    if degraded: return out
    try: INDEX.write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
    except OSError as e: log.warning('could not write the retrieval index (%s)',type(e).__name__)
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


def _kb_only():
    """Applicant-safe rulebook passages from kb.json alone (used when the index or the manual is missing)."""
    try:
        raw=json.loads((HERE/'kb.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        log.warning('kb.json missing or unreadable: no retrieval corpus')
        return {'chunks':[],'schema_version':1,'embedding_model':None}
    chunks=[dict(c,document_id='challenge-rulebook-corpus',document_name=c.get('src',''),page_number=None,section=c['head'],subsection='',
                 version=hashlib.sha256(c['text'].encode()).hexdigest(),source_type='approved_challenge_source',
                 source_classification='Internal operational rule') for c in raw if c.get('audience','applicant')=='applicant']
    for i,c in enumerate(chunks): c['chunk_id']=f'kb-{i}'
    return {'chunks':chunks,'schema_version':1,'embedding_model':None}


def _load_index():
    """Index file, else rebuild it, else keyword/kb-only with a logged warning. Never raises."""
    try:
        if INDEX.exists():
            data=json.loads(INDEX.read_text(encoding='utf-8'))
            if data.get('schema_version')==SCHEMA: return data
        return prepare()
    except (OSError,ValueError,KeyError) as e:
        log.warning('retrieval index unavailable (%s); using the rulebook passages only',type(e).__name__)
        return _kb_only()


def retrieve(question,limit=5,semantic=True):
    start=time.perf_counter()
    if re.search(r'\b(secret|unpublished|confidential)\b',question,re.I):
        return [],{'mode':'abstention','latency_ms':0,'candidate_count':0,'reason':'No approved evidence for confidential or unpublished information'}
    data=_load_index()
    if not data['chunks']:
        return [],{'mode':'unavailable','latency_ms':0,'candidate_count':0,'embedding_model':None}
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

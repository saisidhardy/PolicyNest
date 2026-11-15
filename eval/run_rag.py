"""Repeatable development retrieval evaluation; never presented as human answer correctness."""
import json
from pathlib import Path
import re
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'policynest_mvp'/'copilot_api'))
import rag

def main():
    rows=[]
    for case in json.loads((ROOT/'eval'/'rag_cases.json').read_text()):
        hits,diagnostics=rag.retrieve(case['question'])
        if case.get('abstain'):
            ok=not hits
        else:
            ok=any(re.search(case['expected'],c['text']+' '+c['head'],re.I) and (not case.get('page') or c['page_number']==case['page']) for c in hits)
        citation_ok=all(c['cite'] and c['section'] and c['version'] and (c['page_number'] is not None if c['source_type']=='operational_reference' else True) for c in hits)
        rows.append({'id':case['id'],'retrieval_pass':ok,'citation_metadata_valid':citation_ok,'latency_ms':diagnostics['latency_ms'],'mode':diagnostics['mode'],'sources':[c['cite'] for c in hits]})
        print(('PASS ' if ok else 'FAIL ')+case['id'],flush=True)
    out={'scope':'Development retrieval and metadata checks; not held-out decision evaluation or independent factual-answer assessment','cases':len(rows),'retrieval_passes':sum(r['retrieval_pass'] for r in rows),'citation_metadata_passes':sum(r['citation_metadata_valid'] for r in rows),'median_latency_ms':statistics.median(r['latency_ms'] for r in rows),'answer_correctness':'Not independently measured; live LLM not exercised','answer_completeness':'Requires human rubric scoring','rows':rows}
    (ROOT/'eval'/'out'/'rag_results.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
    return 0 if all(r['retrieval_pass'] and r['citation_metadata_valid'] for r in rows) else 1

if __name__=='__main__':sys.exit(main())

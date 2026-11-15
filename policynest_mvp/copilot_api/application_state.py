"""Minimised applicant progress. Client observations never become verified compliance findings."""
import re
import math

STAGES = ['Before you start','Your details','Documents','Verification','Training','Exam','Certificate']
DOCUMENTS = ['PAN card','Aadhaar (front)','Aadhaar (back)','Class 10 marksheet','Cancelled cheque','Selfie']
STATES = {'not uploaded','reading','photo','rejected','ok'}
ISSUE = re.compile(r'^[A-Z][A-Z0-9_]{0,39}$')


def minimise(value):
    if not isinstance(value,dict): raise ValueError('invalid_snapshot')
    stage=value.get('stage','Before you start')
    if stage not in STAGES: raise ValueError('invalid_stage')
    def number(x,default,maximum):
        return max(0,min(maximum,float(x))) if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) else default
    docs=[];seen=set()
    for d in value.get('documents',[])[:6] if isinstance(value.get('documents',[]),list) else []:
        if not isinstance(d,dict): continue
        # Fixed slots, no filenames, names, OCR, images, arbitrary explanations or identifiers.
        key=d.get('key')
        if key not in ('PAN','AADHAAR_FRONT','AADHAAR_BACK','CLASS10','BANK','SELFIE') or key in seen: continue
        seen.add(key)
        issues=d.get('open_issues',[])
        docs.append({'key':key,'status':d.get('status') if d.get('status') in STATES else 'not uploaded',
                     'open_issues':[s for s in issues[:8] if isinstance(s,str) and ISSUE.fullmatch(s)] if isinstance(issues,list) else [],
                     'version':max(1,int(number(d.get('version',1),1,100)))})
    for d in docs:d['open_issues']=['FACE_MATCH_LOW' if c=='FACE_MATCH_LOW_REPEAT' else c for c in d['open_issues']]
    return {'stage':stage,'documents':docs,'training_hours':number(value.get('training_hours'),0,15),
            'exam_score':number(value.get('exam_score'),None,100),
            'decision':value.get('decision') if value.get('decision') in ('APPROVE','REJECT','NEEDS_MORE_INFO','HUMAN_REVIEW') else None,
            'provenance':'applicant_device_demo','screen':stage}


def context(snapshot):
    value=minimise(snapshot or {})
    labels=dict(zip(('PAN','AADHAAR_FRONT','AADHAAR_BACK','CLASS10','BANK','SELFIE'),DOCUMENTS))
    value['documents']=[dict(d,document=labels[d['key']]) for d in value['documents']]
    pending=[d['document'] for d in value['documents'] if d['status']!='ok']
    value['suggested_next_step']='Please address the pending document feedback.' if pending else 'Continue with the next action on your current application screen.'
    value['application_status']='Device-reported demo progress; reviewer decisions are recorded separately.'
    return value

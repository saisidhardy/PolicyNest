"""Privacy-minimised technical measurements and separately defined product events."""
import hashlib
import hmac
import json
import os
import secrets
import time
import auth

EVENTS={'registration','login','onboarding_started','stage_completed','application_submitted','application_approved','application_rejected','document_uploaded','document_corrected','ocr_succeeded','ocr_failed','verification_completed','training_started','training_completed','exam_passed','exam_failed','assistant_opened','assistant_question','assistant_resolved','human_escalation','appeal_submitted','appeal_resolved','reviewer_action','certificate_issued','application_resumed'}
METRICS={'load','lcp','inp','cls','js_error','api_failure','upload_ms','ocr_ms','assistant_ms'}
STAGES={'Before you start','Your details','Documents','Verification','Training','Exam','Certificate'}


def init():
    with auth._db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS technical (id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, route TEXT NOT NULL, status INTEGER NOT NULL, duration REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS business_events (event_id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, subject TEXT NOT NULL, name TEXT NOT NULL, actor_type TEXT NOT NULL, stage TEXT NOT NULL, source TEXT NOT NULL, duration REAL, result TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS frontend_metrics (id TEXT PRIMARY KEY,timestamp INTEGER NOT NULL,name TEXT NOT NULL,value REAL NOT NULL)')
        columns={r[1] for r in db.execute('PRAGMA table_info(business_events)')}
        for name in ('document_type','issue_code'):
            if name not in columns:db.execute('ALTER TABLE business_events ADD COLUMN '+name+' TEXT')
        now=int(time.time())
        db.execute('DELETE FROM technical WHERE timestamp<?',(now-30*86400,))
        db.execute('DELETE FROM frontend_metrics WHERE timestamp<?',(now-30*86400,))
        db.execute('DELETE FROM business_events WHERE timestamp<?',(now-90*86400,))


def technical(route,status,duration,request_id):
    init()
    # Only route templates supplied by the handler; no request bodies, URLs, query strings or IPs.
    with auth._db() as db: db.execute('INSERT INTO technical VALUES(?,?,?,?,?)',(request_id,int(time.time()),route,int(status),float(duration)))


def business(actor,event):
    if not isinstance(event,dict) or event.get('event_name') not in EVENTS: raise ValueError('invalid_event')
    stage=event.get('stage','Before you start')
    if stage not in STAGES: raise ValueError('invalid_stage')
    source=event.get('source','demo')
    if source not in ('demo','operational') or (source=='operational' and actor['role'] not in ('admin','service')): raise ValueError('invalid_source')
    init()
    subject=hmac.new(auth._secret(),str(actor['id']).encode(),hashlib.sha256).hexdigest()[:24]
    duration=event.get('duration_ms');duration=max(0,min(86400000,float(duration))) if isinstance(duration,(int,float)) else None
    event_id=secrets.token_hex(16)
    document=event.get('document_type') if event.get('document_type') in ('PAN','AADHAAR_FRONT','AADHAAR_BACK','CLASS10','BANK','SELFIE') else None
    issue=event.get('issue_code') if event.get('issue_code') in ('IMAGE_BLURRY','IMAGE_CROPPED','NAME_MISMATCH','DOB_MISMATCH','BANK_NAME_MISMATCH','NOT_ACCEPTED','DOC_MISSING') else None
    with auth._db() as db: db.execute('INSERT INTO business_events(event_id,timestamp,subject,name,actor_type,stage,source,duration,result,document_type,issue_code) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(event_id,int(time.time()),subject,event['event_name'],actor['role'],stage,source,duration,event.get('result') if event.get('result') in ('success','failure','pending') else 'pending',document,issue))
    return event_id


def frontend(values):
    if not isinstance(values,list) or len(values)>20: raise ValueError('invalid_metrics')
    init()
    with auth._db() as db:
        for value in values:
            if not isinstance(value,dict) or value.get('name') not in METRICS or not isinstance(value.get('value'),(int,float)): continue
            db.execute('INSERT INTO frontend_metrics VALUES(?,?,?,?)',(secrets.token_hex(16),int(time.time()),value['name'],max(0,min(86400000,float(value['value'])))))


def report(actor,days=30,source='demo',stage=None):
    if actor['role'] not in ('admin','ops'): raise ValueError('forbidden')
    init();since=int(time.time())-max(1,min(90,int(days)))*86400
    with auth._db() as db:
        tech=[dict(r) for r in db.execute('SELECT route,COUNT(*) requests,AVG(duration) mean_ms,SUM(status>=400) errors FROM technical WHERE timestamp>=? GROUP BY route',(since,))]
        sql='SELECT name,COUNT(*) events,COUNT(DISTINCT subject) applicants,AVG(duration) mean_duration_ms FROM business_events WHERE timestamp>=? AND source=?'
        args=[since,source]
        if stage in STAGES:sql+=' AND stage=?';args.append(stage)
        business=[dict(r) for r in db.execute(sql+' GROUP BY name',args)]
        front=[dict(r) for r in db.execute('SELECT name,COUNT(*) samples,AVG(value) mean_value FROM frontend_metrics WHERE timestamp>=? GROUP BY name',(since,))]
        statuses=[dict(r) for r in db.execute('SELECT status,COUNT(*) requests FROM technical WHERE timestamp>=? GROUP BY status',(since,))]
        stages=[dict(r) for r in db.execute('SELECT stage,COUNT(DISTINCT subject) applicants,AVG(duration) mean_stage_ms FROM business_events WHERE timestamp>=? AND source=? AND name=? GROUP BY stage',(since,source,'stage_completed'))]
        failures=[dict(r) for r in db.execute("SELECT document_type,issue_code,COUNT(*) failures FROM business_events WHERE timestamp>=? AND source=? AND name='ocr_failed' GROUP BY document_type,issue_code",(since,source))]
        durations=sorted(r[0] for r in db.execute('SELECT duration FROM technical WHERE timestamp>=?',(since,)))
        workload=[dict(r) for r in db.execute('SELECT reviewer_id,COUNT(*) assigned FROM cases WHERE reviewer_id IS NOT NULL GROUP BY reviewer_id')]
        appeals=[dict(r) for r in db.execute('SELECT status,COUNT(*) cases,AVG(resolved-created) resolution_seconds FROM appeals WHERE created>=? GROUP BY status',(since,))]
    counts={r['name']:r['applicants'] for r in business}
    ocr_n=sum(r['events'] for r in business if r['name']=='ocr_succeeded');ocr_d=sum(r['events'] for r in business if r['name'] in ('ocr_succeeded','ocr_failed'))
    def rate(n,d):return {'numerator':counts.get(n,0),'denominator':counts.get(d,0),'rate':counts.get(n,0)/counts[d] if counts.get(d) else None}
    return {'window_days':days,'source':source,'stage':stage,'technical':tech,'http_statuses':statuses,'frontend':front,'events':business,'stage_conversion':stages,'document_failures':failures,'reviewer_workload':workload,'appeals':appeals,
            'latency_distribution_ms':{'p50':durations[int((len(durations)-1)*.5)] if durations else None,'p95':durations[int((len(durations)-1)*.95)] if durations else None},
            'metrics':{'registration_to_start':rate('onboarding_started','registration'),'submission_rate':rate('application_submitted','onboarding_started'),'certification_rate':rate('certificate_issued','onboarding_started'),'rejection_rate':rate('application_rejected','application_submitted'),'correction_rate':rate('document_corrected','application_submitted'),'ocr_success_rate':{'numerator':ocr_n,'denominator':ocr_d,'rate':ocr_n/ocr_d if ocr_d else None},'human_escalation':rate('human_escalation','application_submitted'),'appeal_rate':rate('appeal_submitted','onboarding_started'),'assistant_resolution':rate('assistant_resolved','assistant_question')},
            'limitations':'Windowed distinct-user event ratios, not longitudinal cohorts. Missing events mean unknown outcomes, not abandonment. Browser observations are client-reported.'}

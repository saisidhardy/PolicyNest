"""Applicant portal service: profile, versioned application, timeline and notifications.

Nothing here stores photos, OCR text, a full PAN, a full Aadhaar or a full bank account number.
Timeline rows and notifications hold only allow-listed event keys plus a stage and a document slot,
so they cannot carry identifiers or document contents. Authorisation goes through policy.allows.
"""
import json
import re
import secrets
import sqlite3
import time

import auth
import policy


class PortalError(Exception):
    def __init__(self, status, error, **extra):
        super().__init__(error)
        self.status = status
        self.payload = dict(extra, error=error)


# ---------------------------------------------------------------- schema
def init():
    with auth._db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS applications (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
          reference TEXT NOT NULL UNIQUE, version INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'DRAFT',
          details TEXT NOT NULL DEFAULT '{}', progress TEXT NOT NULL DEFAULT '{}',
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS timeline (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, t INTEGER NOT NULL, actor TEXT NOT NULL, key TEXT NOT NULL,
          stage TEXT NOT NULL DEFAULT '', doc TEXT NOT NULL DEFAULT '',
          UNIQUE(user_id, key, stage, doc, t))""")
        db.execute("""CREATE TABLE IF NOT EXISTS notifications (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, type TEXT NOT NULL, key TEXT NOT NULL,
          stage TEXT NOT NULL DEFAULT '', doc TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
          read INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, reference TEXT NOT NULL DEFAULT '')""")
        db.execute('CREATE INDEX IF NOT EXISTS timeline_user ON timeline(user_id, t)')
        db.execute('CREATE INDEX IF NOT EXISTS notif_user ON notifications(user_id, read, created_at)')


# ---------------------------------------------------------------- helpers
def _applicant(user):
    """Only applicants own a portal application; ownership is the user id, checked through the ABAC policy."""
    resource = {'applicant_id': user['id'], 'status': 'DRAFT', 'sensitivity': 'applicant'}
    if user.get('role') != 'applicant' or not policy.allows(user, 'portal.read', resource) \
            or not policy.allows(user, 'portal.write', resource):
        raise PortalError(403, 'forbidden')
    return user


def _mask_mobile(m):
    digits = re.sub(r'\D', '', str(m or ''))
    return ('•' * 6 + digits[-4:]) if len(digits) >= 4 else None


def _clean_mobile(value):
    digits = re.sub(r'[\s\-]', '', str(value or ''))
    digits = re.sub(r'^(\+91|91|0)(?=\d{10}$)', '', digits)
    if not re.fullmatch(r'[6-9]\d{9}', digits):
        raise PortalError(400, 'invalid_mobile')
    return digits


def public_profile(row):
    return {'id': int(row['id']), 'email': row['email'], 'display_name': row['display_name'], 'role': row['role'],
            'email_verified': False, 'mobile_verified': False,  # no verification provider exists yet
            'mobile_masked': _mask_mobile(row['mobile']), 'language': row['language'],
            'analytics_consent': bool(row['analytics_consent'])}


def get_profile(user):
    with auth._db() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
    if not row:
        raise PortalError(401, 'unauthenticated')
    return {'user': public_profile(row)}


def patch_profile(user, body):
    sets, args = [], []
    if 'display_name' in body:
        name = str(body['display_name'] or '').strip() if isinstance(body['display_name'], str) else ''
        if not 2 <= len(name) <= 80:
            raise PortalError(400, 'invalid_display_name')
        sets.append('display_name=?'); args.append(name)
    if 'mobile' in body:
        if body['mobile'] in (None, ''):
            sets.append('mobile=NULL')
        else:
            sets.append('mobile=?'); args.append(_clean_mobile(body['mobile']))
    if 'language' in body:
        if body['language'] not in ('en', 'hi'):
            raise PortalError(400, 'invalid_language')
        sets.append('language=?'); args.append(body['language'])
    if 'analytics_consent' in body:
        if not isinstance(body['analytics_consent'], bool):
            raise PortalError(400, 'invalid_consent')
        sets.append('analytics_consent=?'); args.append(1 if body['analytics_consent'] else 0)
    if sets:
        with auth._db() as db:
            db.execute('UPDATE users SET ' + ','.join(sets) + ' WHERE id=?', args + [user['id']])
    return get_profile(user)


def has_analytics_consent(user):
    with auth._db() as db:
        row = db.execute('SELECT analytics_consent FROM users WHERE id=?', (user['id'],)).fetchone()
    return bool(row and row['analytics_consent'])


# ---------------------------------------------------------------- application
PAN_FULL = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]{5}\d{4}[A-Za-z](?![A-Za-z0-9])')
DETAIL_TEXT = {'name': 80, 'dob': 10, 'email': 254, 'state': 40, 'city': 60, 'education': 40, 'ifsc': 11}
SLOTS = ('PAN', 'AADHAAR_FRONT', 'AADHAAR_BACK', 'CLASS10', 'BANK', 'SELFIE')
CODE = re.compile(r'^[A-Za-z][A-Za-z0-9_\-]{0,39}$')
LABEL = re.compile(r'^[A-Za-z0-9 _\-]{1,40}$')
MAX_PROGRESS = 12_000


def clean_details(value, stored=None):
    if not isinstance(value, dict):
        raise PortalError(400, 'invalid_details')
    out = {}
    for k, v in value.items():
        if k in DETAIL_TEXT:
            if v is None or v == '':
                continue
            if not isinstance(v, str) or len(v) > DETAIL_TEXT[k]:
                raise PortalError(400, 'invalid_details', field=k)
            out[k] = v.strip()
        elif k == 'mobile':
            if v is None or v == '':
                continue
            if isinstance(v, str) and '•' in v:  # the masked copy we returned: keep what is stored
                if stored and stored.get('mobile'):
                    out['mobile'] = stored['mobile']
                continue
            out['mobile'] = _clean_mobile(v)
        elif k in ('aadhaar4', 'acct_last4'):
            if v is None or v == '':
                continue
            if not isinstance(v, (str, int)) or isinstance(v, bool) or not re.fullmatch(r'\d{1,4}', str(v)):
                raise PortalError(400, 'identifier_too_long', field=k)
            out[k] = str(v)
        elif k == 'pan_last4':
            if v is None or v == '':
                continue
            if not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9]{1,4}', v):
                raise PortalError(400, 'identifier_too_long', field=k)
            out[k] = v.upper()
        elif k == 'language':
            if v not in ('en', 'hi'):
                raise PortalError(400, 'invalid_language')
            out[k] = v
        # unknown keys are dropped
    for k, v in out.items():  # defence in depth: no full PAN, 12-digit Aadhaar or long account number anywhere
        if k in ('mobile', 'email'):  # an email such as 9876543210@gmail.com is legitimate
            continue
        if PAN_FULL.search(v) or re.search(r'\d{4}\s?\d{4}\s?\d{4}', v) or re.search(r'\d{9,18}', v):
            raise PortalError(400, 'identifier_not_accepted', field=k)
    return out


def _int(v, lo, hi, field):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
        raise PortalError(400, 'invalid_progress', field=field)
    return int(v)


def _code(v, field, n=40):
    if not isinstance(v, str) or not CODE.fullmatch(v) or len(v) > n:
        raise PortalError(400, 'invalid_progress', field=field)
    return v


def _label(v, field):
    if not isinstance(v, str) or not LABEL.fullmatch(v):
        raise PortalError(400, 'invalid_progress', field=field)
    return v


def clean_progress(value):
    if not isinstance(value, dict):
        raise PortalError(400, 'invalid_progress')
    out = {}
    if 'stage' in value and value['stage'] is not None:
        out['stage'] = _label(value['stage'], 'stage')
    if 'dpage' in value and value['dpage'] is not None:
        out['dpage'] = _int(value['dpage'], 0, 10, 'dpage')
    if 'doc_index' in value and value['doc_index'] is not None:
        out['doc_index'] = _int(value['doc_index'], 0, 10, 'doc_index')
    r = value.get('resume')
    if isinstance(r, dict):
        res = {}
        for k in ('stage', 'milestone', 'action'):
            if r.get(k) is not None:
                res[k] = _label(r[k], 'resume.' + k)
        for k in ('page', 'doc'):
            if r.get(k) is not None:
                res[k] = _int(r[k], 0, 20, 'resume.' + k) if k == 'page' else _code(r[k], 'resume.doc', 24)
        if r.get('t') is not None:
            res['t'] = _int(r['t'], 0, 4_102_444_800_000, 'resume.t')
        out['resume'] = res
    d = value.get('documents')
    if isinstance(d, dict):
        docs = {}
        for slot, v in list(d.items())[:8]:
            if not isinstance(v, dict) or not isinstance(slot, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,23}', slot):
                raise PortalError(400, 'invalid_progress', field='documents')
            item = {'status': _label(v.get('status', 'not uploaded'), 'documents.status')[:20],
                    'version': _int(v.get('version', 1), 1, 100, 'documents.version')}
            issues = v.get('issues', [])
            if not isinstance(issues, list) or len(issues) > 8:
                raise PortalError(400, 'invalid_progress', field='documents.issues')
            item['issues'] = [_code(i, 'documents.issues') for i in issues]
            docs[slot] = item
        out['documents'] = docs
    if 'decision' in value:
        if value['decision'] not in (None, 'APPROVE', 'REJECT', 'NEEDS_MORE_INFO', 'HUMAN_REVIEW'):
            raise PortalError(400, 'invalid_progress', field='decision')
        out['decision'] = value['decision']
    if value.get('round') is not None:
        out['round'] = _int(value['round'], 0, 20, 'round')
    t = value.get('training')
    if isinstance(t, dict):
        mods = t.get('modules', [])
        if not isinstance(mods, list) or len(mods) > 20:
            raise PortalError(400, 'invalid_progress', field='training')
        out['training'] = {'modules': [_code(m, 'training.modules') for m in mods],
                           'hours': _int(t.get('hours', 0), 0, 15, 'training.hours')}
    e = value.get('exam')
    if isinstance(e, dict):
        ex = {}
        if e.get('score') is not None:
            ex['score'] = _int(e['score'], 0, 100, 'exam.score')
        if e.get('passed') is not None:
            if not isinstance(e['passed'], bool):
                raise PortalError(400, 'invalid_progress', field='exam.passed')
            ex['passed'] = e['passed']
        if e.get('attempts') is not None:
            ex['attempts'] = _int(e['attempts'], 0, 50, 'exam.attempts')
        if e.get('retake_at') is not None:
            ex['retake_at'] = _int(e['retake_at'], 0, 4_102_444_800_000, 'exam.retake_at')
        out['exam'] = ex
    c = value.get('certificate')
    if isinstance(c, dict):
        cert = {}
        if c.get('code') is not None:
            cert['code'] = _code(c['code'], 'certificate.code')
        if c.get('seal') is not None:
            cert['seal'] = _code(c['seal'], 'certificate.seal')
        if c.get('issued_at') is not None:
            cert['issued_at'] = _int(c['issued_at'], 0, 4_102_444_800_000, 'certificate.issued_at')
        out['certificate'] = cert
    if len(json.dumps(out, separators=(',', ':'))) > MAX_PROGRESS:
        raise PortalError(400, 'progress_too_large')
    return out


def derive_status(progress):
    if progress.get('certificate', {}).get('code'):
        return 'CERTIFIED'
    d = progress.get('decision')
    if d == 'REJECT':
        return 'REJECTED'
    if d == 'HUMAN_REVIEW':
        return 'IN_REVIEW'
    if d == 'NEEDS_MORE_INFO':
        return 'NEEDS_MORE_INFO'
    if d == 'APPROVE':
        return 'VERIFIED'
    return 'IN_PROGRESS' if progress.get('stage') not in (None, 'Before you start') else 'DRAFT'


def _public_app(row):
    details = json.loads(row['details'])
    if details.get('mobile'):
        details['mobile'] = _mask_mobile(details['mobile'])
    keys = row.keys()
    out = {'reference': row['reference'], 'version': row['version'], 'status': row['status'], 'details': details,
           'progress': json.loads(row['progress']), 'updated_at': row['updated_at']}
    if 'stage' in keys:
        out['stage'] = row['stage']
    if 'section' in keys:
        out['section'] = row['section']
    if 'page' in keys:
        out['page'] = row['page']
    if 'resume_position' in keys:
        out['resume_position'] = json.loads(row['resume_position'] or '{}')
    return out


def _new_reference():
    return 'PN-%d-%05d' % (time.gmtime().tm_year, secrets.randbelow(100000))


def create_application(user):
    _applicant(user)
    init()
    now = int(time.time())
    with auth._db() as db:
        for _ in range(30):
            row = db.execute('SELECT * FROM applications WHERE user_id=?', (user['id'],)).fetchone()
            if row:
                return _public_app(row)
            try:
                db.execute('INSERT INTO applications(user_id,reference,created_at,updated_at) VALUES(?,?,?,?)',
                           (user['id'], _new_reference(), now, now))
            except sqlite3.IntegrityError:
                continue  # reference collision (or a concurrent create): look again
        raise PortalError(503, 'reference_unavailable')


def get_application(user):
    _applicant(user)
    init()
    with auth._db() as db:
        row = db.execute('SELECT * FROM applications WHERE user_id=?', (user['id'],)).fetchone()
    if not row:
        raise PortalError(404, 'no_application')
    return _public_app(row)


def put_application(user, body):
    _applicant(user)
    init()
    version = body.get('version')
    if isinstance(version, bool) or not isinstance(version, int):
        raise PortalError(400, 'version_required')
    with auth._db() as db:
        row = db.execute('SELECT * FROM applications WHERE user_id=?', (user['id'],)).fetchone()
        if not row:
            raise PortalError(404, 'no_application')
        stored_details = json.loads(row['details'])
        details = clean_details(body['details'], stored_details) if 'details' in body else stored_details
        progress = clean_progress(body['progress']) if 'progress' in body else json.loads(row['progress'])
        now = int(time.time())

        cols = {r[1] for r in db.execute('PRAGMA table_info(applications)')}
        extra_sets, extra_args = [], []
        if 'resume_position' in cols and 'resume_position' in body:
            extra_sets.append('resume_position=?')
            extra_args.append(json.dumps(body['resume_position'] or {}, separators=(',', ':')))
        if 'stage' in cols and 'stage' in body:
            extra_sets.append('stage=?')
            extra_args.append(str(body['stage'])[:30])
        if 'section' in cols and 'section' in body:
            extra_sets.append('section=?')
            extra_args.append(str(body['section'])[:30])
        if 'page' in cols and 'page' in body:
            extra_sets.append('page=?')
            extra_args.append(int(body['page']))

        set_clause = 'version=version+1,details=?,progress=?,status=?,updated_at=?'
        if extra_sets:
            set_clause += ',' + ','.join(extra_sets)

        args = [json.dumps(details, separators=(',', ':')), json.dumps(progress, separators=(',', ':')),
                derive_status(progress), now] + extra_args + [user['id'], version]

        changed = db.execute(f'UPDATE applications SET {set_clause} WHERE user_id=? AND version=?', args).rowcount
        if not changed:
            current = db.execute('SELECT * FROM applications WHERE user_id=?', (user['id'],)).fetchone()
            raise PortalError(409, 'stale', application=_public_app(current))
    return {'version': version + 1, 'updated_at': now}


# ---------------------------------------------------------------- events, timeline, notifications
# key -> (actor, notification type or None, action route). Applicants may send only the "you"/"policynest"
# keys below; reviewer keys are written by the server when a person decides.
EVENTS = {
    'application_started': ('you', None, ''),
    'resumed': ('you', None, ''),
    'saved_exit': ('you', None, ''),
    'details_saved': ('you', 'success', '#documents'),
    'doc_uploaded': ('you', None, ''),
    'doc_verified': ('policynest', 'success', '#documents'),
    'doc_needs_fix': ('policynest', 'action', '#documents'),
    'doc_refused': ('policynest', 'action', '#documents'),
    'docs_complete': ('policynest', 'success', '#apply'),
    'verification_passed': ('policynest', 'success', '#apply'),
    'verification_followup': ('policynest', 'action', '#documents'),
    'verification_review': ('policynest', 'info', '#history'),
    'fixes_received': ('you', 'info', '#history'),
    'training_module_done': ('you', 'success', '#training'),
    'training_complete': ('you', 'success', '#exam'),
    'exam_passed': ('policynest', 'success', '#certificate'),
    'exam_failed': ('policynest', 'action', '#exam'),
    'agreement_executed': ('you', 'success', '#certificate'),
    'certificate_issued': ('policynest', 'success', '#certificate'),
    'certificate_revoked': ('policynest', 'error', '#status'),
    'dispute_submitted': ('you', 'info', '#history'),
    'verification_completed': ('policynest', 'info', '#documents'),
    'doc_corrected': ('you', 'info', '#documents'),
}
REVIEWER_EVENTS = {
    'review_approved': ('reviewer', 'success', '#home'),
    'review_more_info': ('reviewer', 'action', '#documents'),
    'review_rejected': ('reviewer', 'info', '#history'),
    'review_in_progress': ('reviewer', 'info', '#history'),
    'appeal_update': ('reviewer', 'info', '#history'),
    'verification_unsuccessful': ('reviewer', 'info', '#history'),
    'review_resumed': ('reviewer', 'info', '#history'),
}
TIMELINE_KEEP = 500
NOTIFICATIONS_KEEP = 200
APPLICANT_ACTORS = ('you', 'policynest', 'reviewer', 'compliance')


def record(db, user_id, key, stage='', doc='', t=None, defs=None):
    """Write one timeline row (and its notification, when the event has one). Returns True if new."""
    actor, ntype, action = (defs or {**EVENTS, **REVIEWER_EVENTS})[key]
    now = int(time.time())
    # The client time is the idempotency key, so it is stored as sent (a retried offline batch of any age
    # stays idempotent); it is clamped only when shown (see timeline()). No usable time: server time.
    t = int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) and t == t and t > 0 else int(time.time() * 1000)
    shown = t
    try:
        cur = db.execute('INSERT INTO timeline(user_id,t,actor,key,stage,doc) VALUES(?,?,?,?,?,?)',
                         (user_id, shown, actor, key, stage or '', doc or ''))
    except sqlite3.IntegrityError:
        return False  # the same event again (a retried offline queue): already recorded
    if ntype:
        ref = db.execute('SELECT reference FROM applications WHERE user_id=?', (user_id,)).fetchone()
        db.execute('INSERT INTO notifications(user_id,type,key,stage,doc,action,read,created_at,reference) VALUES(?,?,?,?,?,?,0,?,?)',
                   (user_id, ntype, key, stage or '', doc or '', action, now, ref['reference'] if ref else ''))
        db.execute('DELETE FROM notifications WHERE user_id=? AND id NOT IN (SELECT id FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?)',
                   (user_id, user_id, NOTIFICATIONS_KEEP))
    db.execute('DELETE FROM timeline WHERE user_id=? AND id NOT IN (SELECT id FROM timeline WHERE user_id=? ORDER BY id DESC LIMIT ?)',
               (user_id, user_id, TIMELINE_KEEP))
    return True


def record_reviewer_event(db, applicant_id, key):
    """Called by workflows when a person decides. Carries no rationale, note or evidence."""
    init()
    if key in REVIEWER_EVENTS:
        record(db, applicant_id, key)


def post_events(user, body):
    _applicant(user)
    init()
    events = body.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 20:
        raise PortalError(400, 'invalid_events')
    accepted = 0
    with auth._db() as db:
        if not db.execute('SELECT 1 FROM applications WHERE user_id=?', (user['id'],)).fetchone():
            raise PortalError(404, 'no_application')
        for e in events:
            if not isinstance(e, dict) or e.get('key') not in EVENTS:
                continue
            stage = e.get('stage') or ''
            doc = e.get('doc') or ''
            if (stage and not (isinstance(stage, str) and LABEL.fullmatch(stage))) or \
                    (doc and not (isinstance(doc, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,23}', doc))):
                continue
            if record(db, user['id'], e['key'], stage, doc, e.get('t'), EVENTS):
                accepted += 1
    return {'accepted': accepted}


def timeline(user, params):
    _applicant(user)
    init()
    sql, args = 'SELECT id,t,actor,key,stage,doc FROM timeline WHERE user_id=?', [user['id']]
    actor = (params.get('actor') or [''])[0]
    if actor in APPLICANT_ACTORS:
        sql += ' AND actor=?'; args.append(actor)
    stage = (params.get('stage') or [''])[0]
    if stage and LABEL.fullmatch(stage):
        sql += ' AND stage=?'; args.append(stage)
    sql += ' ORDER BY t DESC,id DESC LIMIT ?'
    args.append(_limit(params, 100, 200))
    allowed = set(EVENTS) | set(REVIEWER_EVENTS)
    with auth._db() as db:
        rows = [dict(r) for r in db.execute(sql, args)]
    items = []
    for r in rows:
        if r['key'] not in allowed or r['actor'] not in APPLICANT_ACTORS:
            continue  # nothing outside the applicant-safe list is ever shown
        item = {'id': r['id'], 't': min(max(r['t'], (int(time.time()) - 86400 * 30) * 1000), (int(time.time()) + 3600) * 1000), 'actor': r['actor'], 'key': r['key']}
        if r['stage']:
            item['stage'] = r['stage']
        if r['doc']:
            item['doc'] = r['doc']
        items.append(item)
    return {'items': items}


def _limit(params, default, maximum):
    try:
        n = int((params.get('limit') or [default])[0])
    except (TypeError, ValueError):
        n = default
    return max(1, min(maximum, n))


def list_notifications(user, params):
    _applicant(user)
    init()
    with auth._db() as db:
        rows = db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ?',
                          (user['id'], _limit(params, 50, 100))).fetchall()
        unread = db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0', (user['id'],)).fetchone()[0]
    items = []
    for r in rows:
        item = {'id': r['id'], 'type': r['type'], 'key': r['key'], 'read': bool(r['read']),
                'created_at': r['created_at'], 'reference': r['reference']}
        for k in ('stage', 'doc', 'action'):
            if r[k]:
                item[k] = r[k]
        items.append(item)
    return {'items': items, 'unread': unread}


def mark_read(user, body):
    _applicant(user)
    init()
    with auth._db() as db:
        if body.get('all') is True:
            db.execute('UPDATE notifications SET read=1 WHERE user_id=?', (user['id'],))
        else:
            ids = body.get('ids')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
                raise PortalError(400, 'invalid_ids')
            db.execute('UPDATE notifications SET read=1 WHERE user_id=? AND id IN (%s)' % ','.join('?' * len(ids)),
                       [user['id']] + ids)
        unread = db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0', (user['id'],)).fetchone()[0]
    return {'unread': unread}


# ---------------------------------------------------------------- milestone 2 handlers
def _handle_dashboard(u, b, p):
    import application as app_module
    lang = (p.get('lang') or ['en'])[0]
    return 200, app_module.get_applicant_dashboard(u, lang=lang)

def _handle_resume(u, b, p):
    import application as app_module
    return 200, app_module.get_resume_position(u)

def _handle_draft_save(u, b, p):
    import application as app_module
    try:
        return 200, app_module.save_draft(u, b)
    except ValueError as e:
        if str(e) == 'conflict_detected':
            raise PortalError(409, 'conflict_detected', application=app_module.get_application(u))
        raise PortalError(400, str(e))

def _handle_submit(u, b, p):
    import application as app_module
    try:
        return 200, app_module.submit_application(u)
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_profile_get(u, b, p):
    import profile as prof_module
    return 200, {'profile': prof_module.get_applicant_profile(u)}

def _handle_profile_patch(u, b, p):
    import profile as prof_module
    try:
        return 200, {'profile': prof_module.update_applicant_profile(u, b)}
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_change_password(u, b, p):
    import profile as prof_module
    try:
        return 200, prof_module.change_applicant_password(u, b.get('current_password'), b.get('new_password'))
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_sign_out_all(u, b, p):
    import profile as prof_module
    return 200, prof_module.sign_out_all_sessions(u)

def _handle_data_export(u, b, p):
    import profile as prof_module
    return 200, prof_module.export_applicant_data(u)

def _handle_delete_request(u, b, p):
    import profile as prof_module
    return 200, prof_module.request_account_deletion(u, b.get('reason'))


# ---------------------------------------------------------------- milestone 3 document handlers
def _handle_doc_upload(u, b, p):
    import base64
    import documents
    slot = b.get('slot')
    content_b64 = b.get('content_base64') or b.get('file_base64')
    if not content_b64:
        raise PortalError(400, 'missing_file_content')
    try:
        if ',' in content_b64:
            content_b64 = content_b64.split(',', 1)[1]
        file_bytes = base64.b64decode(content_b64)
    except Exception:
        raise PortalError(400, 'invalid_base64_content')
    file_name = b.get('file_name', f"{slot}.bin")
    client_signals = b.get('client_signals')
    try:
        return 200, documents.upload_document(u, slot, file_bytes, file_name, client_signals)
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_doc_list(u, b, p):
    import documents
    return 200, {'documents': documents.list_documents(u)}

def _handle_doc_download(u, b, p):
    import documents
    doc_id = p.get('doc_id', [''])[0] or (b.get('doc_id') if isinstance(b, dict) else '')
    if not doc_id:
        raise PortalError(400, 'missing_doc_id')
    try:
        content, mime_type, file_name = documents.get_document_content(u, doc_id)
        if p.get('format', [''])[0] == 'json':
            import base64
            return 200, {
                'doc_id': doc_id,
                'mime_type': mime_type,
                'file_name': file_name,
                'content_base64': base64.b64encode(content).decode('ascii'),
            }
        return 200, (content, mime_type, file_name)
    except FileNotFoundError:
        raise PortalError(404, 'document_not_found')
    except PermissionError as e:
        raise PortalError(403, str(e))

def _handle_doc_verify(u, b, p):
    import documents
    return 200, documents.verify_application(u)

def _handle_doc_cross_checks(u, b, p):
    import documents
    return 200, {'checks': documents.get_cross_document_checks(u)}

def _handle_doc_correction(u, b, p):
    import base64
    import documents
    slot = b.get('slot')
    content_b64 = b.get('content_base64') or b.get('file_base64')
    if not content_b64:
        raise PortalError(400, 'missing_file_content')
    try:
        if ',' in content_b64:
            content_b64 = content_b64.split(',', 1)[1]
        file_bytes = base64.b64decode(content_b64)
    except Exception:
        raise PortalError(400, 'invalid_base64_content')
    file_name = b.get('file_name', f"{slot}_corrected.bin")
    explanation = b.get('explanation')
    try:
        return 200, documents.submit_document_correction(u, slot, file_bytes, file_name, explanation=explanation)
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_doc_guidelines(u, b, p):
    import documents
    slot = p.get('slot', [None])[0]
    lang = p.get('lang', ['en'])[0]
    return 200, {'guidelines': documents.get_guidelines(slot, lang)}


# ---------------------------------------------------------------- milestone 4 review operations handlers
def _handle_reviewer_queues(u, b, p):
    import review_ops
    try:
        q_type = p.get('type', ['my_queue'])[0]
        status_filter = p.get('status', [None])[0]
        search = p.get('search', [None])[0]
        page = int(p.get('page', ['1'])[0])
        limit = int(p.get('limit', ['20'])[0])
        return 200, review_ops.get_queues(u, queue_type=q_type, status_filter=status_filter, search=search, page=page, limit=limit)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_reviewer_claim(u, b, p):
    import review_ops
    try:
        return 200, review_ops.claim_case(u, b.get('case_id'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')
    except ValueError as e:
        raise PortalError(409 if str(e) == 'case_already_claimed' else 400, str(e))

def _handle_reviewer_release(u, b, p):
    import review_ops
    try:
        return 200, review_ops.release_case(u, b.get('case_id'), reason=b.get('reason', 'Self-released'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')

def _handle_reviewer_reassign(u, b, p):
    import review_ops
    try:
        return 200, review_ops.reassign_case(u, b.get('case_id'), int(b.get('target_reviewer_id')), reason=b.get('reason', 'Workload rebalancing'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_reviewer_dossier(u, b, p):
    import review_ops
    case_id = p.get('case_id', [''])[0] or (b.get('case_id') if isinstance(b, dict) else '')
    if not case_id:
        raise PortalError(400, 'missing_case_id')
    try:
        return 200, {'dossier': review_ops.get_case_dossier(u, case_id)}
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')

def _handle_reviewer_decide(u, b, p):
    import review_ops
    try:
        return 200, review_ops.decide_case(
            u,
            case_id=b.get('case_id'),
            status=b.get('status'),
            note=b.get('note'),
            rule=b.get('rule'),
            slot_defects=b.get('slot_defects'),
            cooling_off_days=b.get('cooling_off_days'),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_appeals_submit(u, b, p):
    import review_ops
    try:
        return 200, review_ops.submit_appeal(u, b.get('case_id'), b.get('explanation'), evidence=b.get('evidence'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_appeals_list(u, b, p):
    import review_ops
    try:
        return 200, {'appeals': review_ops.list_appeals(u, status_filter=p.get('status', [None])[0])}
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_appeals_decide(u, b, p):
    import review_ops
    try:
        return 200, review_ops.decide_appeal(
            u,
            appeal_reference=b.get('appeal_reference') or b.get('id'),
            verdict=b.get('verdict'),
            response_text=b.get('response'),
            restore_status=b.get('restore_status'),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'appeal_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_fraud_cases_list(u, b, p):
    import fraud_ops
    try:
        limit = int(p.get('limit', [50])[0])
        offset = int(p.get('offset', [0])[0])
        status = p.get('status', [None])[0]
        risk_tier = p.get('risk_tier', [None])[0]
        return 200, fraud_ops.list_fraud_cases(u, status_filter=status, risk_tier=risk_tier, limit=limit, offset=offset)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_fraud_case_get(u, b, p):
    import fraud_ops
    case_id = p.get('id', [None])[0] or (b.get('case_id') if isinstance(b, dict) else None) or (b.get('id') if isinstance(b, dict) else None)
    if not case_id:
        raise PortalError(400, 'case_id_required')
    try:
        return 200, fraud_ops.get_fraud_dossier(u, case_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')

def _handle_fraud_investigate(u, b, p):
    import fraud_ops
    case_id = b.get('case_id') or b.get('id')
    if not case_id:
        raise PortalError(400, 'case_id_required')
    try:
        return 200, fraud_ops.assign_investigator(u, case_id, b.get('investigator_id'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')

def _handle_fraud_decide(u, b, p):
    import fraud_ops
    case_id = b.get('case_id') or b.get('id')
    if not case_id:
        raise PortalError(400, 'case_id_required')
    try:
        return 200, fraud_ops.decide_fraud_case(
            u,
            case_id=case_id,
            decision=b.get('decision'),
            notes=b.get('notes'),
            blacklist_identifiers=b.get('blacklist_identifiers'),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'case_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_fraud_evaluate(u, b, p):
    import fraud_engine
    target_app = (b.get('application_id') if isinstance(b, dict) else None) or (b.get('id') if isinstance(b, dict) else None) or u.get('id')
    client_ip = (b.get('client_ip') if isinstance(b, dict) else None) or p.get('client_ip', [None])[0]
    try:
        return 200, fraud_engine.evaluate_application_risk(target_app, client_ip=client_ip)
    except FileNotFoundError:
        raise PortalError(404, 'application_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_fraud_blacklist_get(u, b, p):
    import fraud_ops
    try:
        ident_type = p.get('type', [None])[0]
        limit = int(p.get('limit', [100])[0])
        return 200, {'blacklist': fraud_ops.list_blacklist(u, identifier_type=ident_type, limit=limit)}
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_fraud_blacklist_add(u, b, p):
    import fraud_ops
    try:
        return 200, fraud_ops.add_to_blacklist(
            u,
            identifier_type=b.get('type'),
            identifier_value=b.get('value'),
            reason=b.get('reason'),
            source_case_id=b.get('source_case_id'),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_fraud_rules(u, b, p):
    import fraud_engine
    return 200, {'rules': list(fraud_engine.FRAUD_RULES.values())}

def _handle_training_overview(u, b, p):
    import training_lms
    try:
        lang = p.get('lang', ['en'])[0]
        return 200, training_lms.get_training_overview(u, lang=lang)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'application_not_found')

def _handle_training_module_detail(u, b, p):
    import training_lms
    module_id = p.get('id', [None])[0] or (b.get('module_id') if isinstance(b, dict) else None)
    if not module_id:
        raise PortalError(400, 'module_id_required')
    lang = p.get('lang', ['en'])[0]
    try:
        return 200, training_lms.get_module_detail(u, module_id, lang=lang)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'module_not_found')

def _handle_training_heartbeat(u, b, p):
    import training_lms
    module_id = b.get('module_id')
    if not module_id:
        raise PortalError(400, 'module_id_required')
    try:
        return 200, training_lms.record_training_heartbeat(
            u,
            module_id=module_id,
            seconds_increment=int(b.get('seconds_increment', 30)),
            section_index=int(b.get('section_index', 0)),
            bookmark=b.get('bookmark'),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_training_complete_module(u, b, p):
    import training_lms
    module_id = b.get('module_id')
    if not module_id:
        raise PortalError(400, 'module_id_required')
    try:
        return 200, training_lms.complete_training_module(u, module_id=module_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_training_admin_list_modules(u, b, p):
    import training_lms
    try:
        return 200, {'modules': training_lms.admin_list_modules(u)}
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_training_admin_upsert_module(u, b, p):
    import training_lms
    try:
        return 200, training_lms.admin_upsert_module(
            u,
            module_id=b.get('id'),
            title=b.get('title'),
            duration_minutes=int(b.get('duration_minutes', 60)),
            content=b.get('content', {}),
            sequence_order=int(b.get('sequence_order', 1)),
        )
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_training_admin_user_progress(u, b, p):
    import training_lms
    target_user_id = int(p.get('user_id', [0])[0] or b.get('user_id', 0))
    if not target_user_id:
        raise PortalError(400, 'user_id_required')
    try:
        return 200, training_lms.admin_get_user_progress(u, target_user_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'user_not_found')

def _handle_training_admin_reset(u, b, p):
    import training_lms
    target_user_id = int(b.get('user_id', 0))
    if not target_user_id:
        raise PortalError(400, 'user_id_required')
    try:
        return 200, training_lms.admin_reset_user_progress(u, target_user_id, b.get('module_id'))
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_exam_eligibility(u, b, p):
    import examination
    try:
        return 200, examination.get_exam_eligibility(u)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_exam_start(u, b, p):
    import examination
    lang = p.get('lang', ['en'])[0] or (b.get('lang') if isinstance(b, dict) else 'en')
    try:
        return 200, examination.start_exam_session(u, lang=lang)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_exam_incident(u, b, p):
    import examination
    exam_id = b.get('exam_id') or b.get('id')
    incident_type = b.get('incident_type', 'TAB_SWITCH')
    if not exam_id:
        raise PortalError(400, 'exam_id_required')
    try:
        return 200, examination.record_exam_incident(u, exam_id, incident_type, b.get('details'))
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'exam_not_found')

def _handle_exam_submit(u, b, p):
    import examination
    exam_id = b.get('exam_id') or b.get('id')
    answers = b.get('answers', {})
    if not exam_id:
        raise PortalError(400, 'exam_id_required')
    try:
        return 200, examination.submit_exam_attempt(u, exam_id, answers)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'exam_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_exam_admin_attempts(u, b, p):
    import examination
    target_user_id = int(p.get('user_id', [0])[0] or (b.get('user_id', 0) if isinstance(b, dict) else 0))
    flagged = p.get('flagged', ['0'])[0] in ('1', 'true', 'True')
    try:
        return 200, {'attempts': examination.admin_list_attempts(u, user_id=target_user_id or None, flagged_only=flagged)}
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_exam_admin_override(u, b, p):
    import examination
    target_user_id = int(b.get('user_id', 0))
    if not target_user_id:
        raise PortalError(400, 'user_id_required')
    try:
        return 200, examination.admin_override_cooldown(u, target_user_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_cert_eligibility(u, b, p):
    import certification
    try:
        return 200, certification.get_certificate_eligibility(u)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_cert_agreement_template(u, b, p):
    import certification
    lang = p.get('lang', ['en'])[0]
    try:
        return 200, certification.get_posp_agreement_template(u, lang=lang)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_cert_agreement_execute(u, b, p):
    import certification
    declaration = b.get('declaration_accepted', True)
    client_ip = b.get('client_ip', '127.0.0.1')
    try:
        return 200, certification.execute_posp_agreement(u, declaration_accepted=declaration, client_ip=client_ip)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_cert_issue(u, b, p):
    import certification
    try:
        return 200, certification.issue_posp_certificate(u)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_cert_me(u, b, p):
    import certification
    try:
        return 200, certification.get_user_certificate(u)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'certificate_not_found')

def _handle_cert_admin_list(u, b, p):
    import certification
    status = p.get('status', [None])[0]
    limit = int(p.get('limit', ['50'])[0])
    try:
        return 200, {'certificates': certification.admin_list_certificates(u, status=status, limit=limit)}
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_cert_admin_revoke(u, b, p):
    import certification
    cert_id = b.get('certificate_number') or b.get('id')
    reason = b.get('reason', 'Administrative revocation')
    if not cert_id:
        raise PortalError(400, 'certificate_number_required')
    try:
        return 200, certification.admin_revoke_certificate(u, cert_id, reason)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'certificate_not_found')

def _handle_notif_dispatch(u, b, p):
    import communications
    user_id = int(b.get('user_id') or u['id'])
    template_key = b.get('template_key') or b.get('template')
    if not template_key:
        raise PortalError(400, 'template_key_required')
    context = b.get('context', {})
    channels = tuple(b.get('channels', ['in_app', 'email', 'sms']))
    try:
        return 200, communications.dispatch_notification(user_id, template_key, context=context, channels=channels)
    except FileNotFoundError:
        raise PortalError(404, 'user_not_found')
    except ValueError as e:
        raise PortalError(400, str(e))

def _handle_notif_dispatched_list(u, b, p):
    import communications
    user_id = int(p.get('user_id', [u['id']])[0])
    limit = int(p.get('limit', ['50'])[0])
    return 200, {'dispatched': communications.list_dispatched_messages(user_id, limit=limit)}

def _handle_audit_timeline(u, b, p):
    import communications
    target_user_id = int(p.get('user_id', [u['id']])[0])
    try:
        return 200, communications.get_unified_audit_timeline(u, target_user_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')

def _handle_compliance_pack(u, b, p):
    import communications
    target_user_id = int(p.get('user_id', [0])[0] or b.get('user_id', 0))
    if not target_user_id:
        raise PortalError(400, 'user_id_required')
    try:
        return 200, communications.generate_compliance_audit_pack(u, target_user_id)
    except PermissionError:
        raise PortalError(403, 'forbidden')
    except FileNotFoundError:
        raise PortalError(404, 'target_not_found')

def _handle_verification(u, b, p):
    import verification
    try:
        return 200, verification.get_system_verification_report(u)
    except ValueError as e:
        raise PortalError(403, str(e))

def _handle_qa_seed(u, b, p):
    import qa
    try:
        return 200, qa.seed_qa_environment(u)
    except ValueError as e:
        raise PortalError(403, str(e))

def _handle_qa_reset(u, b, p):
    import qa
    try:
        return 200, qa.reset_qa_environment(u)
    except ValueError as e:
        raise PortalError(403, str(e))


# ---------------------------------------------------------------- route table

def _handle_dev_inbox(u, b, p):
    limit = int(p.get("limit", ["50"])[0])
    recipient = p.get("recipient", [None])[0] or p.get("email", [None])[0]
    with auth._db() as db:
        query = "SELECT id, user_id, channel, template_key, recipient, subject, content, status, created_at FROM communication_dispatches"
        args = []
        if u and u.get("role") in ("admin", "ops", "reviewer"):
            if recipient:
                query += " WHERE recipient=?"
                args.append(recipient)
        elif u:
            query += " WHERE user_id=? OR recipient=?"
            args.extend([u["id"], u.get("email", "")])
        else:
            if recipient:
                query += " WHERE recipient=?"
                args.append(recipient)
        query += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        rows = db.execute(query, args).fetchall()
        inbox = []
        for r in rows:
            d = dict(r)
            d["body_preview"] = (d.get("content") or "")[:140]
            inbox.append(d)
        return 200, {"inbox": inbox, "total": len(inbox)}

def _handle_email_verify(u, b, p):
    token = (b.get("token") if isinstance(b, dict) else None) or p.get("token", [None])[0]
    if not token:
        raise PortalError(400, "token_required")
    success = auth.verify_email_token(token)
    if not success:
        raise PortalError(400, "invalid_or_expired_token")
    return 200, {"ok": True, "message": "Email verified successfully"}

def _handle_analytics_events(u, b, p):
    events = b.get("events", []) if isinstance(b, dict) else []
    if not isinstance(events, list):
        if isinstance(b, dict) and "event_name" in b:
            events = [b]
        else:
            raise PortalError(400, "invalid_events_payload")

    user_id = u["id"] if u else None
    inserted = 0
    with auth._db() as db:
        for ev in events[:100]:
            name = str(ev.get("event_name") or ev.get("name") or "unknown")[:64]
            category = str(ev.get("category") or "general")[:32]
            url = str(ev.get("url") or "")[:256]
            session_id = str(ev.get("session_id") or "")[:64]
            props = ev.get("properties") or {}
            clean_props = {}
            if isinstance(props, dict):
                for k, v in props.items():
                    k_str = str(k).lower()
                    if any(bad in k_str for bad in ("password", "secret", "pan", "aadhaar", "otp", "token")):
                        clean_props[k] = "[REDACTED]"
                    else:
                        clean_props[k] = v
            ts = int(ev.get("timestamp") or time.time())
            ev_id = f"EVT-{secrets.token_hex(8)}"
            db.execute(
                "INSERT INTO analytics_events (event_id, user_id, session_id, event_name, event_category, properties_json, url, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ev_id, user_id, session_id, name, category, json.dumps(clean_props), url, ts),
            )
            inserted += 1
    return 200, {"ok": True, "inserted": inserted}

def _handle_analytics_dashboard(u, b, p):
    with auth._db() as db:
        users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        verified_email_count = db.execute("SELECT COUNT(*) FROM users WHERE email_verified=1").fetchone()[0]
        cases_count = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        submitted_cases = db.execute("SELECT COUNT(*) FROM cases WHERE status NOT IN ('DRAFT', 'DOCUMENTS_PENDING')").fetchone()[0]
        approved_cases = db.execute("SELECT COUNT(*) FROM cases WHERE status IN ('VERIFIED_PENDING_TRAINING', 'TRAINING_IN_PROGRESS', 'TRAINING_COMPLETED', 'EXAMINATION_IN_PROGRESS', 'EXAMINATION_PASSED', 'CERTIFIED')").fetchone()[0]
        certified_cases = db.execute("SELECT COUNT(*) FROM cases WHERE status='CERTIFIED'").fetchone()[0]
        
        doc_count = db.execute("SELECT COUNT(*) FROM document_records").fetchone()[0]
        
        event_breakdown = [dict(r) for r in db.execute("SELECT event_name, COUNT(*) count FROM analytics_events GROUP BY event_name ORDER BY count DESC LIMIT 10").fetchall()]
        recent_dispatches = db.execute("SELECT COUNT(*) FROM communication_dispatches").fetchone()[0]

        return 200, {
            "overview": {
                "total_registered_applicants": users_count,
                "email_verified_applicants": verified_email_count,
                "total_applications_created": cases_count,
                "applications_submitted": submitted_cases,
                "applications_approved": approved_cases,
                "posp_certified_agents": certified_cases,
                "documents_uploaded_total": doc_count,
                "dispatches_logged": recent_dispatches,
            },
            "conversion_funnel": [
                {"stage": "Registration", "count": max(users_count, 1), "percentage": 100.0},
                {"stage": "Email Verified", "count": verified_email_count, "percentage": round(verified_email_count / max(users_count, 1) * 100, 1)},
                {"stage": "Documents Uploaded", "count": min(doc_count, cases_count), "percentage": round(min(doc_count, cases_count) / max(users_count, 1) * 100, 1)},
                {"stage": "Submitted for Review", "count": submitted_cases, "percentage": round(submitted_cases / max(users_count, 1) * 100, 1)},
                {"stage": "KYC Verified", "count": approved_cases, "percentage": round(approved_cases / max(users_count, 1) * 100, 1)},
                {"stage": "POSP Certified", "count": certified_cases, "percentage": round(certified_cases / max(users_count, 1) * 100, 1)},
            ],
            "top_events": event_breakdown,
            "is_dynamic": True,
            "generated_at": int(time.time()),
        }

ROUTES = {
    ('GET', '/api/me'): lambda u, b, p: (200, get_profile(u)),
    ('PATCH', '/api/me'): lambda u, b, p: (200, patch_profile(u, b)),
    ('GET', '/api/me/profile'): _handle_profile_get,
    ('PATCH', '/api/me/profile'): _handle_profile_patch,
    ('GET', '/api/me/dashboard'): _handle_dashboard,
    ('POST', '/api/me/change-password'): _handle_change_password,
    ('POST', '/api/me/sessions/sign-out-all'): _handle_sign_out_all,
    ('POST', '/api/me/privacy/export'): _handle_data_export,
    ('POST', '/api/me/privacy/delete-request'): _handle_delete_request,
    ('POST', '/api/applications/me'): lambda u, b, p: (200, {'application': create_application(u)}),
    ('GET', '/api/applications/me'): lambda u, b, p: (200, {'application': get_application(u)}),
    ('PUT', '/api/applications/me'): lambda u, b, p: (200, put_application(u, b)),
    ('POST', '/api/applications/me/draft'): _handle_draft_save,
    ('GET', '/api/applications/me/resume'): _handle_resume,
    ('POST', '/api/applications/me/submit'): _handle_submit,
    ('POST', '/api/applications/me/events'): lambda u, b, p: (200, post_events(u, b)),
    ('GET', '/api/applications/me/timeline'): lambda u, b, p: (200, timeline(u, p)),
    ('GET', '/api/notifications'): lambda u, b, p: (200, list_notifications(u, p)),
    ('POST', '/api/notifications/read'): lambda u, b, p: (200, mark_read(u, b)),
    ('POST', '/api/documents/upload'): _handle_doc_upload,
    ('GET', '/api/documents'): _handle_doc_list,
    ('GET', '/api/documents/download'): _handle_doc_download,
    ('POST', '/api/documents/verify'): _handle_doc_verify,
    ('GET', '/api/documents/cross-checks'): _handle_doc_cross_checks,
    ('POST', '/api/documents/correction'): _handle_doc_correction,
    ('GET', '/api/documents/guidelines'): _handle_doc_guidelines,
    ('GET', '/api/reviewer/queues'): _handle_reviewer_queues,
    ('POST', '/api/reviewer/claim'): _handle_reviewer_claim,
    ('POST', '/api/reviewer/release'): _handle_reviewer_release,
    ('POST', '/api/reviewer/reassign'): _handle_reviewer_reassign,
    ('GET', '/api/reviewer/dossier'): _handle_reviewer_dossier,
    ('POST', '/api/reviewer/decision'): _handle_reviewer_decide,
    ('POST', '/api/appeals/submit'): _handle_appeals_submit,
    ('GET', '/api/appeals'): _handle_appeals_list,
    ('POST', '/api/appeals/decide'): _handle_appeals_decide,
    ('GET', '/api/fraud/cases'): _handle_fraud_cases_list,
    ('GET', '/api/fraud/case'): _handle_fraud_case_get,
    ('POST', '/api/fraud/investigate'): _handle_fraud_investigate,
    ('POST', '/api/fraud/decide'): _handle_fraud_decide,
    ('POST', '/api/fraud/evaluate'): _handle_fraud_evaluate,
    ('GET', '/api/fraud/blacklist'): _handle_fraud_blacklist_get,
    ('POST', '/api/fraud/blacklist'): _handle_fraud_blacklist_add,
    ('GET', '/api/fraud/rules'): _handle_fraud_rules,
    ('GET', '/api/training/modules'): _handle_training_overview,
    ('GET', '/api/training/module'): _handle_training_module_detail,
    ('POST', '/api/training/heartbeat'): _handle_training_heartbeat,
    ('POST', '/api/training/complete'): _handle_training_complete_module,
    ('GET', '/api/training/progress'): _handle_training_overview,
    ('GET', '/api/training/admin/modules'): _handle_training_admin_list_modules,
    ('POST', '/api/training/admin/modules'): _handle_training_admin_upsert_module,
    ('GET', '/api/training/admin/user-progress'): _handle_training_admin_user_progress,
    ('POST', '/api/training/admin/reset'): _handle_training_admin_reset,
    ('GET', '/api/exam/eligibility'): _handle_exam_eligibility,
    ('POST', '/api/exam/start'): _handle_exam_start,
    ('POST', '/api/exam/incident'): _handle_exam_incident,
    ('POST', '/api/exam/submit'): _handle_exam_submit,
    ('GET', '/api/exam/admin/attempts'): _handle_exam_admin_attempts,
    ('POST', '/api/exam/admin/override-cooldown'): _handle_exam_admin_override,
    ('GET', '/api/certificates/eligibility'): _handle_cert_eligibility,
    ('GET', '/api/certificates/agreement/template'): _handle_cert_agreement_template,
    ('POST', '/api/certificates/agreement/execute'): _handle_cert_agreement_execute,
    ('POST', '/api/certificates/issue'): _handle_cert_issue,
    ('GET', '/api/certificates/me'): _handle_cert_me,
    ('GET', '/api/certificates/admin/list'): _handle_cert_admin_list,
    ('POST', '/api/certificates/admin/revoke'): _handle_cert_admin_revoke,
    ('POST', '/api/notifications/dispatch'): _handle_notif_dispatch,
    ('GET', '/api/notifications/dispatched'): _handle_notif_dispatched_list,
    ('GET', '/api/audit/timeline'): _handle_audit_timeline,
    ('GET', '/api/compliance/audit-pack'): _handle_compliance_pack,
    ('POST', '/api/compliance/audit-pack'): _handle_compliance_pack,
    ('GET', '/api/verification'): _handle_verification,
    ('POST', '/api/qa/seed'): _handle_qa_seed,
    ('POST', '/api/qa/reset'): _handle_qa_reset,
    ('GET', '/api/dev/inbox'): _handle_dev_inbox,
    ('GET', '/api/auth/verify-email'): _handle_email_verify,
    ('POST', '/api/auth/verify-email'): _handle_email_verify,
    ('POST', '/api/analytics/events'): _handle_analytics_events,
    ('GET', '/api/analytics/dashboard'): _handle_analytics_dashboard,
}

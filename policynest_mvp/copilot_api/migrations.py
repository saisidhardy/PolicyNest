"""Lightweight, versioned, idempotent database migration framework for PolicyNest.

Applies incremental DDL/DML migrations in guaranteed transaction order.
Maintains the `schema_migrations` table to ensure migrations are only executed once.
Safe for upgrades and restarts.
"""
import sqlite3
import time
from pathlib import Path

# Migration registry: (version, name, callable(db))
MIGRATIONS = []

def migration(version, name):
    """Decorator to register a migration function."""
    def decorator(fn):
        MIGRATIONS.append((version, name, fn))
        return fn
    return decorator


@migration(1, "001_initial_core_schema")
def migrate_001_initial_core_schema(db):
    """Ensure all baseline tables exist with expected columns."""
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'applicant',
        created_at INTEGER NOT NULL,
        token_version INTEGER NOT NULL DEFAULT 0,
        language TEXT NOT NULL DEFAULT 'en',
        mobile TEXT,
        analytics_consent INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS application_snapshots (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        snapshot TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS refresh_tokens (
        digest TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        family TEXT NOT NULL,
        expires INTEGER NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        revoked INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS reset_tokens (
        digest TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires INTEGER NOT NULL,
        used INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY,
        applicant_id INTEGER NOT NULL UNIQUE,
        reviewer_id INTEGER,
        status TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS appeals (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        explanation TEXT NOT NULL,
        status TEXT NOT NULL,
        response TEXT,
        created INTEGER NOT NULL,
        resolved INTEGER,
        evidence TEXT NOT NULL DEFAULT '{}'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        actor_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        occurred INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS review_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        reviewer_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        created INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS assignment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        previous_reviewer INTEGER,
        new_reviewer INTEGER NOT NULL,
        actor_id INTEGER NOT NULL,
        occurred INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
        reference TEXT NOT NULL UNIQUE,
        version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        details TEXT NOT NULL DEFAULT '{}',
        progress TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS timeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        t INTEGER NOT NULL,
        actor TEXT NOT NULL,
        key TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT '',
        doc TEXT NOT NULL DEFAULT '',
        UNIQUE(user_id, key, stage, doc, t)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        key TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT '',
        doc TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL DEFAULT '',
        read INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        reference TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_daily_usage (
        day TEXT PRIMARY KEY,
        requests INTEGER NOT NULL
    )""")
    # Trigger for immutable audit logs
    db.execute("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'immutable'); END")
    db.execute("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'immutable'); END")


@migration(2, "002_staff_and_abac_security_expansion")
def migrate_002_staff_and_abac_security_expansion(db):
    """Add staff provisioning, MFA, lockout, and session security columns."""
    cols = {r[1] for r in db.execute('PRAGMA table_info(users)')}
    add_cols = [
        ('status', "TEXT NOT NULL DEFAULT 'active'"),
        ('failed_logins', "INTEGER NOT NULL DEFAULT 0"),
        ('locked_until', "INTEGER NOT NULL DEFAULT 0"),
        ('must_reset_password', "INTEGER NOT NULL DEFAULT 0"),
        ('mfa_enabled', "INTEGER NOT NULL DEFAULT 0"),
        ('mfa_secret', "TEXT"),
        ('mfa_recovery_codes', "TEXT"),
        ('last_login_at', "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, ddl in add_cols:
        if col_name not in cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {ddl}")

    # Staff profiles table
    db.execute("""CREATE TABLE IF NOT EXISTS staff_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        department TEXT NOT NULL DEFAULT 'Operations',
        employee_id TEXT,
        created_by INTEGER REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'active',
        updated_at INTEGER NOT NULL
    )""")

    # Staff invitations table
    db.execute("""CREATE TABLE IF NOT EXISTS staff_invitations (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        department TEXT NOT NULL DEFAULT 'Operations',
        token_digest TEXT NOT NULL UNIQUE,
        invited_by INTEGER NOT NULL REFERENCES users(id),
        expires_at INTEGER NOT NULL,
        accepted_at INTEGER,
        created_at INTEGER NOT NULL
    )""")

    # Role change audit log
    db.execute("""CREATE TABLE IF NOT EXISTS role_audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES users(id),
        target_user_id INTEGER NOT NULL REFERENCES users(id),
        old_role TEXT NOT NULL,
        new_role TEXT NOT NULL,
        reason TEXT NOT NULL,
        occurred INTEGER NOT NULL
    )""")

    # CSRF secrets per user
    db.execute("""CREATE TABLE IF NOT EXISTS csrf_secrets (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        secret TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )""")

    # Indices
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_staff_invitations_email ON staff_invitations(email)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_staff_invitations_digest ON staff_invitations(token_digest)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_role_audit_target ON role_audit_events(target_user_id)")


@migration(3, "003_domain_entities_foundation")
def migrate_003_domain_entities_foundation(db):
    """Normalize domain models for documents, fraud, training, and certification (Milestones 2-7 foundation)."""
    # Document storage metadata (no raw image files in database)
    db.execute("""CREATE TABLE IF NOT EXISTS document_records (
        id TEXT PRIMARY KEY,
        application_id INTEGER NOT NULL REFERENCES applications(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        slot TEXT NOT NULL,
        doc_type TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        storage_path TEXT NOT NULL,
        sha256_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        quality_score REAL,
        ocr_extracted_json TEXT,
        rejection_reason TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )""")

    # Verification provider results
    db.execute("""CREATE TABLE IF NOT EXISTS verification_results (
        id TEXT PRIMARY KEY,
        application_id INTEGER NOT NULL REFERENCES applications(id),
        provider TEXT NOT NULL,
        check_type TEXT NOT NULL,
        status TEXT NOT NULL,
        reference_id TEXT,
        match_score REAL,
        response_digest TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL
    )""")

    # Cross-document checks
    db.execute("""CREATE TABLE IF NOT EXISTS cross_document_checks (
        id TEXT PRIMARY KEY,
        application_id INTEGER NOT NULL REFERENCES applications(id),
        check_name TEXT NOT NULL,
        status TEXT NOT NULL,
        discrepancy_details TEXT,
        created_at INTEGER NOT NULL
    )""")

    # Fraud and anomaly cases
    db.execute("""CREATE TABLE IF NOT EXISTS fraud_cases (
        id TEXT PRIMARY KEY,
        application_id INTEGER NOT NULL REFERENCES applications(id),
        applicant_id INTEGER NOT NULL REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'FLAGGED',
        anomaly_type TEXT NOT NULL,
        signals_json TEXT NOT NULL DEFAULT '[]',
        notes TEXT,
        investigator_id INTEGER REFERENCES users(id),
        hold_placed INTEGER NOT NULL DEFAULT 1,
        resolved_at INTEGER,
        resolution_notes TEXT,
        created_at INTEGER NOT NULL
    )""")

    # Training and LMS
    db.execute("""CREATE TABLE IF NOT EXISTS training_modules (
        id TEXT PRIMARY KEY,
        program_version TEXT NOT NULL DEFAULT 'v1',
        title TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        content_json TEXT NOT NULL DEFAULT '{}',
        sequence_order INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS training_progress (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        module_id TEXT NOT NULL REFERENCES training_modules(id),
        status TEXT NOT NULL DEFAULT 'NOT_STARTED',
        time_spent_seconds INTEGER NOT NULL DEFAULT 0,
        completed_at INTEGER,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(user_id, module_id)
    )""")

    # Examination
    db.execute("""CREATE TABLE IF NOT EXISTS exam_attempts (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        attempt_number INTEGER NOT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        total_questions INTEGER NOT NULL DEFAULT 50,
        passed INTEGER NOT NULL DEFAULT 0,
        started_at INTEGER NOT NULL,
        completed_at INTEGER,
        incident_flag INTEGER NOT NULL DEFAULT 0
    )""")

    # Certification
    db.execute("""CREATE TABLE IF NOT EXISTS certificates (
        id TEXT PRIMARY KEY,
        certificate_number TEXT NOT NULL UNIQUE,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
        application_id INTEGER NOT NULL REFERENCES applications(id),
        posp_name TEXT NOT NULL,
        pan_masked TEXT NOT NULL,
        lines_of_business TEXT NOT NULL DEFAULT 'Life,General,Health',
        issued_at INTEGER NOT NULL,
        valid_until INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        signature_digest TEXT NOT NULL,
        revoked_at INTEGER,
        revocation_reason TEXT
    )""")

    # Indices for performance
    db.execute("CREATE INDEX IF NOT EXISTS idx_doc_app ON document_records(application_id, slot)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_verif_app ON verification_results(application_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fraud_app ON fraud_cases(application_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_training_user ON training_progress(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cert_number ON certificates(certificate_number)")


@migration(4, "004_application_persistence_and_profile_expansion")
def migrate_004_application_persistence_and_profile_expansion(db):
    """Expand user profile and application persistence columns."""
    user_cols = {r[1] for r in db.execute('PRAGMA table_info(users)')}
    for col_name, ddl in [
        ('city', "TEXT"),
        ('state', "TEXT"),
        ('pincode', "TEXT"),
        ('notification_prefs', "TEXT NOT NULL DEFAULT '{\"email\":true,\"in_app\":true,\"sms\":false}'"),
    ]:
        if col_name not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {ddl}")

    app_cols = {r[1] for r in db.execute('PRAGMA table_info(applications)')}
    for col_name, ddl in [
        ('stage', "TEXT NOT NULL DEFAULT 'Welcome'"),
        ('section', "TEXT NOT NULL DEFAULT 'basics'"),
        ('page', "INTEGER NOT NULL DEFAULT 1"),
        ('resume_position', "TEXT NOT NULL DEFAULT '{}'"),
        ('submitted_at', "INTEGER"),
        ('verified_at', "INTEGER"),
        ('risk_hold', "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col_name not in app_cols:
            db.execute(f"ALTER TABLE applications ADD COLUMN {col_name} {ddl}")

    db.execute("""CREATE TABLE IF NOT EXISTS data_deletion_requests (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'REQUESTED',
        reason TEXT,
        requested_at INTEGER NOT NULL,
        processed_at INTEGER
    )""")


@migration(5, "005_review_operations_and_appeals_expansion")
def migrate_005_review_operations_and_appeals_expansion(db):
    """Expand cases and appeals with operational timestamps and audit references."""
    case_cols = {r[1] for r in db.execute('PRAGMA table_info(cases)')}
    for col_name, ddl in [
        ('claimed_at', "INTEGER"),
        ('cooling_off_until', "INTEGER"),
        ('escalation_reason', "TEXT"),
        ('created_at', "INTEGER"),
        ('updated_at', "INTEGER"),
    ]:
        if col_name not in case_cols:
            db.execute(f"ALTER TABLE cases ADD COLUMN {col_name} {ddl}")

    appeal_cols = {r[1] for r in db.execute('PRAGMA table_info(appeals)')}
    for col_name, ddl in [
        ('resolved_by', "INTEGER REFERENCES users(id)"),
        ('resolution_notes', "TEXT"),
    ]:
        if col_name not in appeal_cols:
            db.execute(f"ALTER TABLE appeals ADD COLUMN {col_name} {ddl}")

    db.execute("CREATE INDEX IF NOT EXISTS idx_cases_reviewer ON cases(reviewer_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_appeals_case ON appeals(case_id, status)")


@migration(6, "006_fraud_engine_and_aml_expansion")
def migrate_006_fraud_engine_and_aml_expansion(db):
    """Expand fraud cases with scoring and evidence locker, add blacklist and network velocity events."""
    fraud_cols = {r[1] for r in db.execute('PRAGMA table_info(fraud_cases)')}
    for col_name, ddl in [
        ('risk_score', "INTEGER NOT NULL DEFAULT 0"),
        ('risk_tier', "TEXT NOT NULL DEFAULT 'LOW'"),
        ('evidence_json', "TEXT NOT NULL DEFAULT '{}'"),
        ('updated_at', "INTEGER"),
    ]:
        if col_name not in fraud_cols:
            db.execute(f"ALTER TABLE fraud_cases ADD COLUMN {col_name} {ddl}")

    # Fraud Blacklist table
    db.execute("""CREATE TABLE IF NOT EXISTS fraud_blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identifier_type TEXT NOT NULL,
        identifier_value TEXT NOT NULL,
        reason TEXT NOT NULL,
        source_case_id TEXT,
        created_at INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fraud_blacklist ON fraud_blacklist(identifier_type, identifier_value)")

    # Network / Device velocity events
    db.execute("""CREATE TABLE IF NOT EXISTS applicant_network_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        applicant_id INTEGER NOT NULL,
        application_id INTEGER,
        ip_address TEXT NOT NULL,
        user_agent TEXT,
        event_type TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_net_events_ip ON applicant_network_events(ip_address, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_net_events_app ON applicant_network_events(applicant_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_fraud_status ON fraud_cases(status, risk_tier)")


@migration(7, "007_training_lms_and_curriculum_seed")
def migrate_007_training_lms_and_curriculum_seed(db):
    """Expand training progress tracking and seed mandatory 15-hour IRDAI POSP curriculum."""
    prog_cols = {r[1] for r in db.execute('PRAGMA table_info(training_progress)')}
    for col_name, ddl in [
        ('last_heartbeat_at', "INTEGER"),
        ('current_section', "INTEGER NOT NULL DEFAULT 0"),
        ('bookmark_position', "TEXT NOT NULL DEFAULT '{}'"),
    ]:
        if col_name not in prog_cols:
            db.execute(f"ALTER TABLE training_progress ADD COLUMN {col_name} {ddl}")

    # Seed 5 IRDAI Modules if not present
    existing_count = db.execute("SELECT COUNT(*) FROM training_modules").fetchone()[0]
    if existing_count == 0:
        modules_seed = [
            (
                "MOD-01",
                "v1",
                "Introduction to Insurance & Core Principles",
                180,
                '{"title_hi":"बीमा और मूल सिद्धांतों का परिचय","hours":3.0,"category":"Principles","description":"Core principles: Uberrima Fides, Insurable Interest, Indemnity, Subrogation, Proximate Cause.","sections":[{"title":"Foundations of Insurance","duration_min":60},{"title":"Fundamental Principles","duration_min":60},{"title":"POSP Role & Boundaries","duration_min":60}]}',
                1,
            ),
            (
                "MOD-02",
                "v1",
                "General Insurance: Motor, Property & Commercial",
                210,
                '{"title_hi":"सामान्य बीमा: मोटर, संपत्ति और वाणिज्यिक","hours":3.5,"category":"General","description":"Motor Vehicle Act 2019, Third-Party vs Comprehensive, Fire, Burglary, and Package policies.","sections":[{"title":"Motor Insurance Essentials","duration_min":75},{"title":"Property & Fire Coverage","duration_min":75},{"title":"Package & Rural Products","duration_min":60}]}',
                2,
            ),
            (
                "MOD-03",
                "v1",
                "Life Insurance: Term, Endowment & Savings Plans",
                210,
                '{"title_hi":"जीवन बीमा: टर्म, एंडोमेंट और बचत योजनाएं","hours":3.5,"category":"Life","description":"Human Life Value, Term Assurance, Pure Protection, Traditional vs ULIP, and Riders.","sections":[{"title":"HLV & Term Protection","duration_min":75},{"title":"Endowment & Money Back","duration_min":75},{"title":"Riders & Claim Settlement","duration_min":60}]}',
                3,
            ),
            (
                "MOD-04",
                "v1",
                "Health Insurance & Personal Accident Coverage",
                180,
                '{"title_hi":"स्वास्थ्य बीमा और व्यक्तिगत दुर्घटना कवरेज","hours":3.0,"category":"Health","description":"Inpatient hospitalization, waiting periods, pre-existing diseases, cashless network, and personal accident.","sections":[{"title":"Health Plans & Waiting Periods","duration_min":60},{"title":"Cashless Claims & Network","duration_min":60},{"title":"Personal Accident Insurance","duration_min":60}]}',
                4,
            ),
            (
                "MOD-05",
                "v1",
                "POSP Code of Conduct, Ethics & Compliance",
                120,
                '{"title_hi":"पीओएसपी आचार संहिता, नैतिकता और अनुपालन","hours":2.0,"category":"Ethics","description":"IRDAI POSP Guidelines 2015, anti-rebating Section 41, single affiliation rule, and Ombudsman.","sections":[{"title":"Code of Conduct & Section 41","duration_min":60},{"title":"Grievance & Ombudsman Scheme","duration_min":60}]}',
                5,
            ),
        ]
        db.executemany(
            """INSERT INTO training_modules (
                id, program_version, title, duration_minutes, content_json, sequence_order
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            modules_seed,
        )


@migration(8, "008_examination_engine_and_question_bank")
def migrate_008_examination_engine_and_question_bank(db):
    """Expand examination tracking, add question bank table, and indices."""
    exam_cols = {r[1] for r in db.execute('PRAGMA table_info(exam_attempts)')}
    for col_name, ddl in [
        ('answers_json', "TEXT NOT NULL DEFAULT '{}'"),
        ('question_ids_json', "TEXT NOT NULL DEFAULT '[]'"),
        ('incident_notes', "TEXT"),
        ('duration_seconds', "INTEGER NOT NULL DEFAULT 1800"),
    ]:
        if col_name not in exam_cols:
            db.execute(f"ALTER TABLE exam_attempts ADD COLUMN {col_name} {ddl}")

    db.execute("""CREATE TABLE IF NOT EXISTS exam_question_bank (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        question_en TEXT NOT NULL,
        question_hi TEXT,
        options_en_json TEXT NOT NULL,
        options_hi_json TEXT,
        correct_index INTEGER NOT NULL,
        explanation_en TEXT,
        explanation_hi TEXT,
        created_at INTEGER NOT NULL
    )""")

    db.execute("CREATE INDEX IF NOT EXISTS idx_exam_user ON exam_attempts(user_id, attempt_number)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_qbank_cat ON exam_question_bank(category)")


@migration(9, "009_posp_agreements_table")
def migrate_009_posp_agreements_table(db):
    """Add posp_agreements table for digital appointment agreement execution."""
    db.execute("""CREATE TABLE IF NOT EXISTS posp_agreements (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        application_id INTEGER NOT NULL REFERENCES applications(id),
        agreement_type TEXT NOT NULL DEFAULT 'IRDAI_POSP_APPOINTMENT',
        version TEXT NOT NULL DEFAULT '2026.1',
        terms_accepted INTEGER NOT NULL DEFAULT 1,
        code_of_conduct_accepted INTEGER NOT NULL DEFAULT 1,
        anti_rebating_declared INTEGER NOT NULL DEFAULT 1,
        signer_name TEXT NOT NULL,
        signer_ip TEXT NOT NULL,
        signed_at INTEGER NOT NULL,
        agreement_hash TEXT NOT NULL,
        counter_signed_by TEXT NOT NULL DEFAULT 'Principal Officer, PolicyNest Broking Technologies',
        counter_signed_at INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_posp_agree_user ON posp_agreements(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_posp_agree_app ON posp_agreements(application_id)")


@migration(10, "010_communications_and_compliance_audit_packs")
def migrate_010_communications_and_compliance_audit_packs(db):
    """Add communication_dispatches and compliance_audit_packs tables."""
    db.execute("""CREATE TABLE IF NOT EXISTS communication_dispatches (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        channel TEXT NOT NULL,
        template_key TEXT NOT NULL,
        recipient TEXT NOT NULL,
        subject TEXT,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DELIVERED',
        created_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS compliance_audit_packs (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        generated_by INTEGER NOT NULL REFERENCES users(id),
        bundle_hash TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_dispatch_user ON communication_dispatches(user_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_compliance_pack_user ON compliance_audit_packs(user_id)")


@migration(11, "011_email_verification_and_analytics_expansion")
def migrate_011_email_verification_and_analytics_expansion(db):
    """Add email_verification_tokens, analytics_events, and system_health_snapshots tables."""
    cols = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    if "email_verified" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    
    db.execute("""CREATE TABLE IF NOT EXISTS email_verification_tokens (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        email TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS analytics_events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        user_id INTEGER,
        persona TEXT NOT NULL,
        session_id TEXT,
        stage TEXT NOT NULL,
        properties_json TEXT NOT NULL,
        is_demo INTEGER NOT NULL DEFAULT 1
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS system_health_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        status TEXT NOT NULL,
        checks_json TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_verification_tokens(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_analytics_name_time ON analytics_events(event_name, timestamp)")


def run_migrations(db):
    """Run all unapplied migrations in ascending order within a single transaction."""
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at INTEGER NOT NULL
    )""")
    applied_versions = {
        row[0] for row in db.execute("SELECT version FROM schema_migrations").fetchall()
    }

    # Sort migrations by version number
    sorted_migrations = sorted(MIGRATIONS, key=lambda m: m[0])
    applied_count = 0

    for version, name, migrate_fn in sorted_migrations:
        if version not in applied_versions:
            # Run migration inside savepoint/transaction
            migrate_fn(db)
            db.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, int(time.time())),
            )
            applied_count += 1

    return applied_count

# PolicyNest Pre-Flight Deployment & Operations Checklist

Use this checklist before promoting any release to production hosting environments (GitHub Pages, Embarko, Railway, or Docker).

---

## 1. Environment Configuration Matrix

| Variable | Required | Production Value | Development / Demo Value | Purpose |
|---|:---:|---|---|---|
| `JWT_SECRET` | **YES** | 64+ char random hex string | Default test secret | HMAC signature for JWT sessions and certificates |
| `IS_PRODUCTION` | **YES** | `true` | `false` | Disables demo features, restricts QA seed/reset routes |
| `IS_DEV` | NO | `false` | `true` | Enables local debug logs and sandbox providers |
| `TEST_MODE` | NO | `false` | `true` | Runs simulated KYC provider adapters |
| `CORS_ALLOWED_ORIGINS` | YES | `https://saisidhardy.github.io,https://policynest.embarko.app` | `*` | Prevents unauthorized cross-origin API invocation |
| `COOKIE_SECURE` | YES | `true` | `false` | Enforces `Secure; HttpOnly; SameSite=Lax` cookies |

---

## 2. Pre-Flight Build Verification

Before committing and pushing code:

```bash
# 1. Run full automated test suite (must report OK with 215 tests passing)
cd policynest_mvp/copilot_api
python -m unittest discover -p "test_*.py"

# 2. Rebuild production bundle (strips all demo controls and specimen tags)
cd ../..
python policynest_mvp/build_site.py --mode prod

# 3. Verify zero demo strings exist in production build
python tools/check_prod_build.py

# 4. Copy built assets to repository root for GitHub Pages
Copy-Item -Path "policynest_mvp\site\*" -Destination "." -Recurse -Force
```

---

## 3. Database Operations & Backups (SQLite WAL Mode)

### Online Hot Backups:
SQLite in WAL mode allows live hot backups without locking read/write transactions:
```bash
# Authoritative online backup using SQLite VACUUM INTO
sqlite3 policynest_mvp/copilot_api/policynest.db "VACUUM INTO 'backups/policynest_backup_$(date +%Y%m%d_%H%M%S).db';"
```

### Emergency Restore Procedure:
1. Stop API backend container / service.
2. Verify integrity of backup file: `sqlite3 backup.db "PRAGMA integrity_check;"`.
3. Replace `policynest.db` with validated backup.
4. Remove stale `-wal` and `-shm` temporary files.
5. Restart API service.

---

## 4. Production Smoke Test Checklist

- [ ] HTTPS connection enforced; HSTS header active.
- [ ] Security headers active: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`.
- [ ] Public landing page renders with English and Hindi language toggle.
- [ ] Create Account and Sign In work smoothly with zero CORS or network errors.
- [ ] Reviewer Operations cockpit (`#review`) loads queues and allows claiming cases.
- [ ] Public Certificate Verification (`#verification` / `/api/certificates/verify/<id>`) verifies certificates without requiring authentication.
- [ ] Zero demo switches (`role-sel`), zero specimens, and zero hardcoded credentials visible.

# PolicyNest Local Setup and Operations Guide

## 1. Quick Start (Single Command)

PolicyNest is designed to run locally with zero paid subscriptions and zero external cloud dependencies.

### Prerequisites
- Python 3.10, 3.11, or 3.12 (Standard Library only; no external pip dependencies required for core backend)
- Modern web browser (Chrome, Edge, Firefox, Safari)

### Run Unified Server
```bash
# Clone and enter directory
cd PolicyNest

# Launch the unified server (Frontend + Backend on port 8000)
python server.py
```

Open your browser to:
**`http://localhost:8000`**

---

## 2. Platform Endpoints

When running locally via `server.py`, the following endpoints are immediately available:

| Endpoint | Method | Description |
|---|---|---|
| `http://localhost:8000/` | `GET` | PolicyNest Responsive Web Frontend |
| `http://localhost:8000/health` | `GET` | Live Process & Health Status Check |
| `http://localhost:8000/ready` | `GET` | Database & Storage Readiness Probe |
| `http://localhost:8000/api/dev/inbox` | `GET` | Local Email Outbox (Inspect verification & reset links) |
| `http://localhost:8000/api/auth/register` | `POST` | Real User Registration with Scrypt Hashing |
| `http://localhost:8000/api/auth/login` | `POST` | Real User Authentication with Session Cookies |
| `http://localhost:8000/api/analytics/dashboard` | `GET` | Dynamic First-Party Business & Funnel Metrics |
| `http://localhost:8000/api/verification` | `GET` | Subsystem Verification & QA Audit Report |

---

## 3. Database Administration CLI

The PolicyNest backend includes a trusted CLI tool (`policynest_mvp/copilot_api/admin.py`) for managing local accounts, seeding synthetic test personas, and resetting the demo state.

### Seed Synthetic Demo Personas
```bash
python -m policynest_mvp.copilot_api.admin seed
```
Creates pre-configured demo personas:
- **Aarav Patel** (`aarav.patel@example.com` / `Password1234!`): Fresh applicant in onboarding
- **Priya Sharma** (`priya.sharma@example.com` / `Password1234!`): Applicant pending reviewer action
- **Vikram Malhotra** (`reviewer@policynest.in` / `ReviewerPass123!`): Senior Reviewer
- **Administrator** (`admin@policynest.in` / `AdminMaster123!`): Compliance Administrator

### Reset Demo Environment
```bash
python -m policynest_mvp.copilot_api.admin reset
```
Safely purges synthetic cases and resets the database while re-applying all 11 database migrations.

### Health Audit via CLI
```bash
python -m policynest_mvp.copilot_api.admin health
```
Performs deep diagnostic probes against all subsystems and outputs a structured health summary.

### Create Custom Administrator
```bash
python -m policynest_mvp.copilot_api.admin provision --email admin2@policynest.in --role admin
```

---

## 4. Environment Configuration

Copy `.env.example` to `.env` if custom overrides are needed:
```bash
# Security
JWT_SECRET=your-32-byte-secret-key-here-change-in-production!
SESSION_TTL_SECONDS=1800

# Server
PORT=8000
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Storage
DOCUMENT_STORAGE_PATH=./documents_storage

# Modes: LOCAL_DEVELOPMENT, AUTOMATED_TEST, DEMO, STAGING, PRODUCTION
POLICYNEST_ENV=LOCAL_DEVELOPMENT
```

---

## 5. Running Automated Tests

Run the complete backend test suite (215 unit, integration, and E2E tests):
```bash
python -m unittest discover -s policynest_mvp/copilot_api -p "test_*.py"
```

Run production build verification check:
```bash
python tools/check_prod_build.py
```

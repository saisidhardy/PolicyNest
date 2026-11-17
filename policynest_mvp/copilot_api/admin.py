"""Trusted local CLI: account provisioning, assignment, recovery, synthetic demo seeding, and system health."""
import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
try:
    from run_local import configure
    configure()
except Exception:
    pass

import auth
import workflows
import qa
import verification


def main():
    p = argparse.ArgumentParser(description="PolicyNest Administration and QA CLI")
    p.add_argument("action", choices=["provision", "create-admin", "seed", "reset", "health", "assign", "reset-password", "cases"])
    p.add_argument("--email", help="Account email address")
    p.add_argument("--password", help="Account password (optional; prompted securely if omitted)")
    p.add_argument("--name", help="Display name for account", default="Administrator")
    p.add_argument("--role", choices=["applicant", "reviewer", "admin", "ops"], default="admin")
    p.add_argument("--case", help="Case ID for assignment")
    p.add_argument("--reviewer", type=int, help="Reviewer user ID for assignment")
    a = p.parse_args()

    if a.action in ("provision", "create-admin"):
        email = a.email or input("Account email: ").strip()
        role = "admin" if a.action == "create-admin" else a.role
        pw = a.password or getpass.getpass("New account password (12+ characters): ")
        name = a.name or f"PolicyNest {role.capitalize()}"
        user = auth.register(email, pw, name)
        with auth._db() as db:
            db.execute("UPDATE users SET role=?, email_verified=1 WHERE id=?", (role, user["id"]))
        print(f"[SUCCESS] Account provisioned successfully.")
        print(f"  User ID: {user['id']}")
        print(f"  Email:   {email}")
        print(f"  Role:    {role}")

    elif a.action == "seed":
        print("[INFO] Seeding synthetic demo personas and test fixtures...")
        admin_actor = {"id": 1, "role": "admin", "email": "admin@policynest.in"}
        res = qa.seed_qa_environment(admin_actor)
        print(f"[SUCCESS] Synthetic demo data successfully seeded.")
        print("  Demo Personas Available:")
        print("    1. Aarav Patel       (aarav.patel@example.com / Password1234!)   - Applicant in Onboarding")
        print("    2. Priya Sharma      (priya.sharma@example.com / Password1234!)  - Pending Reviewer Action")
        print("    3. Vikram Malhotra   (reviewer@policynest.in / ReviewerPass123!) - Senior Reviewer")
        print("    4. Compliance Admin  (admin@policynest.in / AdminMaster123!)    - Compliance Administrator")

    elif a.action == "reset":
        print("[INFO] Purging synthetic test data and resetting demo environment...")
        admin_actor = {"id": 1, "role": "admin", "email": "admin@policynest.in"}
        res = qa.reset_qa_environment(admin_actor)
        print(f"[SUCCESS] Demo environment cleanly reset. Preserved real production accounts.")

    elif a.action == "health":
        print("[INFO] Auditing all PolicyNest subsystems...")
        rep = verification.get_system_verification_report()
        print(f"================================================================")
        print(f" PolicyNest Subsystem Verification Report (v{rep.get('application_version')})")
        print(f" Commit: {rep.get('commit_id')} | Build: {rep.get('build_timestamp')}")
        print(f" Database: {rep.get('database', {}).get('status')} | Storage: {rep.get('storage', {}).get('status')}")
        print(f"================================================================")
        subsystems = rep.get("subsystems", {})
        sub_items = subsystems.items() if isinstance(subsystems, dict) else [(s.get("name", "subsystem"), s) for s in subsystems]
        for key, s in sub_items:
            status = s.get("status", "UNKNOWN") if isinstance(s, dict) else str(s)
            title = (s.get("title") or key) if isinstance(s, dict) else key
            symbol = "✔" if status == "Verified" else "ℹ" if "Simulated" in status else "✖"
            print(f" [{symbol}] {title:<40} : {status}")
        print(f"================================================================")

    elif a.action == "assign":
        workflows.assign({"id": 0, "role": "admin"}, a.case, a.reviewer)
        print(f"[SUCCESS] Assignment recorded for case {a.case} -> reviewer {a.reviewer}.")

    elif a.action == "cases":
        workflows.init()
        with auth._db() as db:
            rows = db.execute("SELECT id, status, reviewer_id, created_at FROM cases").fetchall()
            print(f"Total Cases: {len(rows)}")
            for row in rows:
                print(dict(row))

    elif a.action == "reset-password":
        pw = a.password or getpass.getpass("Replacement password (12+ characters): ")
        token = auth.create_reset(a.email)
        if token:
            auth.reset_password(token, pw)
            print("[SUCCESS] Password updated successfully.")
        else:
            print("[INFO] Account recovery processed if account exists.")


if __name__ == "__main__":
    main()

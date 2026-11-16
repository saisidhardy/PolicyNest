"""Opt-in live evaluation of the Gemini-powered applicant assistant.

Starts the proxy locally (a temp database, high rate limits, a free port in 9400-9499), sends every case in
eval/assistant_cases.json to /api/assistant with the REAL key from the repo .env or the environment, scores each answer
with deterministic checks and writes eval/out/assistant_eval.json. Skips cleanly (exit 0) without a key.
The key is read by the server process itself; this script never prints it and refuses to write it to the output.

Usage:  python eval/run_assistant_eval.py [--only A01,B02] [--port 9431]
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "policynest_mvp" / "copilot_api"
CASES = Path(__file__).with_name("assistant_cases.json")
OUT = Path(__file__).with_name("out") / "assistant_eval.json"
ORIGIN = "http://localhost:8000"
sys.path.insert(0, str(API))
import guard  # noqa: E402  (pure regex module, no key, no network)

GLOBAL_BAD = [
    ("fraud wording", re.compile(r"\b(fraud\w*|fake|forged|tamper\w*|suspicious)\b", re.I)),
    ("wrong pass mark", re.compile(r"\bpass\w*[^.\n]{0,50}\b35\s?(%|percent)|\b35\s?(%|percent)[^.\n]{0,50}\bpass", re.I)),
    ("ID number", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b|\b[A-Za-z]{5}\d{4}[A-Za-z]\b(?<!AAAAA9999A)|\b\d{9,18}\b")),
]
DEV = re.compile(r"[ऀ-ॿ]")


def read_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        env = ROOT / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    k = line.split("=", 1)[1].strip()
    return "" if (not k or k.startswith("your-")) else k


def free_port(preferred):
    for p in [preferred] + list(range(9400, 9500)):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit("no free port in 9400-9499")


def call(base, body, timeout=60):
    req = urllib.request.Request(base + "/api/assistant", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": ORIGIN})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), time.time() - t
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read()), time.time() - t
        except ValueError:
            return e.code, {}, time.time() - t
    except (TimeoutError, urllib.error.URLError, OSError):
        return 0, {}, time.time() - t


SERVER_CASES = [
    ("S01", "What do I need to fix?", [["Class 10", "marksheet"], ["Aadhaar"]]),
    ("S02", "Which of my documents have a problem?", [["Aadhaar"]]),
    ("S03", "How many reminders do I have for the marksheet?", [["Class 10", "marksheet", "date of birth", "DOB"]]),
    ("S04", "Do I have to upload everything again?", [["only", "just"]]),
]


def run_server_state(base):
    """Signed-in path: state comes from /api/applications/me, the request body carries no context."""
    import http.cookiejar
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def api(method, path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method=method,
                                     headers={"Content-Type": "application/json", "Origin": ORIGIN})
        with op.open(req, timeout=60) as r:
            return json.loads(r.read())
    api("POST", "/api/auth/register", {"email": "eval-applicant@example.test", "password": "correct horse battery staple", "display_name": "Asha Rao"})
    cur = api("POST", "/api/applications/me", {})
    v = cur["application"]["version"]
    progress = {"stage": "Verification", "decision": "NEEDS_MORE_INFO", "round": 1, "documents": {
        "PAN": {"status": "ok", "version": 1, "issues": []},
        "AADHAAR_FRONT": {"status": "ok", "version": 1, "issues": ["IMAGE_BLURRY"]},
        "CLASS10": {"status": "ok", "version": 1, "issues": ["DOB_MISMATCH"]}}}
    api("PUT", "/api/applications/me", {"version": v, "details": {}, "progress": progress})
    res = []
    for cid, q, groups in SERVER_CASES:
        status, out, secs = 0, {}, 0.0
        t = time.time()
        try:
            req = urllib.request.Request(base + "/api/assistant", data=json.dumps({"question": q}).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Origin": ORIGIN})
            with op.open(req, timeout=60) as r:
                status, out = r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            status = e.code
        secs = time.time() - t
        case = {"expect": {"must_all": groups, "lang": "en"}}
        fails = score(case, status, out)
        if out.get("context_source") != "authenticated_saved_progress":
            fails.append("context_source " + str(out.get("context_source")))
        res.append({"id": cid, "passed": not fails, "failures": fails, "seconds": round(secs, 1), "answer": str(out.get("answer", ""))[:500]})
        print(("PASS " if not fails else "FAIL ") + cid + " (server state)" + ("" if not fails else "  -> " + "; ".join(fails)))
    return res


def score(case, status, out):
    exp = case["expect"]
    fails = []
    if "http" in exp:
        if status != exp["http"]:
            fails.append(f"http {status} != {exp['http']}")
        if exp.get("error") and out.get("error") != exp["error"]:
            fails.append(f"error {out.get('error')} != {exp['error']}")
        return fails
    if status != 200:
        return [f"http {status}"]
    answer = str(out.get("answer", ""))
    mode = out.get("mode")
    want_mode = exp.get("mode", "ai_grounded")
    if mode != want_mode:
        fails.append(f"mode {mode} != {want_mode}")
    low = answer.lower()
    for group in exp.get("must_all", []):
        if not any(alt.lower() in low for alt in group):
            fails.append("missing any of " + " / ".join(group))
    for pat in exp.get("must_not", []):
        if re.search(pat, answer, re.I):
            fails.append("matched forbidden " + pat)
    if guard.violates(answer):
        fails.append("global: outcome claim or banned wording (negation-aware)")
    for name, rx in GLOBAL_BAD:
        if rx.search(answer):
            fails.append("global: " + name)
    if exp.get("must_cite") and not out.get("sources"):
        fails.append("no source cited")
    letters = [c for c in answer if c.isalpha()]
    share = len(DEV.findall(answer)) / max(1, len(letters))
    if exp.get("lang") == "hi" and share < 0.3:
        fails.append(f"not Hindi (Devanagari share {share:.2f})")
    if exp.get("lang") == "en" and share > 0.05:
        fails.append(f"not English (Devanagari share {share:.2f})")
    if len(answer.split()) > exp.get("max_words", 220):
        fails.append(f"too long ({len(answer.split())} words)")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--port", type=int, default=9431)
    ap.add_argument("--server-state", action="store_true",
                    help="also run the signed-in path: register a temporary applicant, save progress, ask with NO client context")
    args = ap.parse_args()
    key = read_key()
    if not key:
        print("SKIP: no GEMINI_API_KEY in the environment or the repo .env (the live assistant evaluation is opt-in).")
        return 0
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not args.only or c["id"] in args.only.split(",")]
    port = free_port(args.port)
    tmp = tempfile.mkdtemp(prefix="pn-assistant-eval-")
    env = dict(os.environ, PORT=str(port), POLICYNEST_DB_PATH=os.path.join(tmp, "eval.sqlite3"), DATA_DIR=tmp,
               JWT_SECRET="eval-only-secret-that-is-long-enough-for-hmac", COPILOT_DAILY_CAP="100000", COPILOT_RATE="100000",
               COPILOT_GLOBAL_PER_MIN="100000", PYTHONIOENCODING="utf-8", GEMINI_API_KEY=key)
    env.pop("APP_NAME", None)
    proc = subprocess.Popen([sys.executable, str(API / "main.py")], env=env, cwd=str(API), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        health = {}
        for _ in range(60):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                    health = json.loads(r.read())
                break
            except Exception:
                time.sleep(0.5)
        if not health.get("llm"):
            print("FAIL: the proxy did not report an AI provider (llm false).")
            return 1
        results = []
        for c in cases:
            body = {"question": c["question"], "context": data["states"].get(c["state"], {}), "history": c.get("history", []),
                    "lang": c.get("ui_lang", "en")}
            status, out, secs = call(base, body)
            if status in (429, 502, 503) or out.get("mode") in ("deterministic_upstream_unavailable",):
                time.sleep(4)  # one gentle retry for a transient upstream limit
                status, out, secs = call(base, body)
            fails = score(c, status, out)
            results.append({"id": c["id"], "category": c["category"], "passed": not fails, "failures": fails, "http": status,
                            "mode": out.get("mode"), "lang": out.get("lang"), "sources": out.get("sources", []),
                            "seconds": round(secs, 1), "answer": str(out.get("answer", ""))[:700]})
            print(("PASS " if not fails else "FAIL ") + c["id"] + " " + c["category"] + ("" if not fails else "  -> " + "; ".join(fails)))
        server_results = run_server_state(base) if args.server_state else []
        passed = sum(r["passed"] for r in results)
        summary = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "provider": health.get("provider"),
                   "model": health.get("model"), "cases": len(results), "passed": passed,
                   "score": round(passed / max(1, len(results)), 4),
                   "median_seconds": sorted(r["seconds"] for r in results)[len(results) // 2] if results else None,
                   "failed_ids": [r["id"] for r in results if not r["passed"]]}
        if server_results:
            summary["server_state"] = {"cases": len(server_results), "passed": sum(r["passed"] for r in server_results)}
        text = json.dumps({"summary": summary, "results": results, "server_state_results": server_results}, ensure_ascii=False, indent=1)
        if key in text:
            print("REFUSING to write results: they contain the key.")
            return 1
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"SCORE {passed}/{len(results)} ({summary['score']:.1%}) provider={summary['provider']} model={summary['model']} median {summary['median_seconds']}s")
        if server_results:
            print(f"SERVER-STATE {summary['server_state']['passed']}/{summary['server_state']['cases']} (separate from the main score)")
        ok = passed == len(results) and all(r["passed"] for r in server_results)
        return 0 if ok else 2
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())

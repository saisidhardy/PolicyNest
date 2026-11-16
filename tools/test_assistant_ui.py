"""Browser test of the applicant-assistant drawer (typing state, quick questions per step, citation chips, Hindi,
error + retry, keyboard, mobile). Opt-in for the live part: with a Gemini key in the repo .env it also asks one real question.

Usage:  python tools/test_assistant_ui.py        (needs policynest_mvp/site-demo built; Python Playwright)
Starts the proxy on port 9420 (temporary database, high limits) and a static server on 9421. Both stop before exit.
The page talks to http://localhost:8787 on a local host, so the test redirects that to the proxy on 9420.
"""
import http.server
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "policynest_mvp", "site-demo")
API_PORT, SITE_PORT = 9420, 9421
SITE = "http://127.0.0.1:%d" % SITE_PORT
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:600]) if (detail and not ok) else ""), flush=True)


def has_key():
    k = os.environ.get("GEMINI_API_KEY", "")
    env = os.path.join(ROOT, ".env")
    if not k and os.path.isfile(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("GEMINI_API_KEY="):
                k = line.split("=", 1)[1].strip()
    return bool(k) and not k.startswith("your-")


def main():
    tmp = tempfile.mkdtemp(prefix="pn-ui-")
    live = has_key()
    env = dict(os.environ, PORT=str(API_PORT), POLICYNEST_DB_PATH=os.path.join(tmp, "t.sqlite3"), DATA_DIR=tmp,
               JWT_SECRET="ui-test-secret-that-is-long-enough-for-hmac", COPILOT_ORIGINS=SITE, COPILOT_DAILY_CAP="100000",
               COPILOT_RATE="100000", COPILOT_GLOBAL_PER_MIN="100000", PYTHONDONTWRITEBYTECODE="1")
    env.pop("APP_NAME", None)
    if not live:
        env["POLICYNEST_SKIP_DOTENV"] = "1"
        env["GEMINI_API_KEY"] = ""
        env["ANTHROPIC_API_KEY"] = ""
    api = subprocess.Popen([sys.executable, os.path.join(ROOT, "policynest_mvp", "copilot_api", "main.py")], env=env,
                           cwd=os.path.join(ROOT, "policynest_mvp", "copilot_api"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=SITE_DIR, **k)

        def log_message(self, *a):
            pass
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", SITE_PORT), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/health" % API_PORT, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = pw.chromium.launch(headless=True)
            for label, viewport in (("desktop", {"width": 1280, "height": 800}), ("phone", {"width": 390, "height": 844})):
                ctx = browser.new_context(viewport=viewport, is_mobile=(label == "phone"), has_touch=(label == "phone"))
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                state = {"mode": "ok", "delay": 0.0, "bodies": []}

                def handler(route):
                    req = route.request
                    if req.method == "POST":
                        state["bodies"].append(req.post_data or "")
                    if state["mode"] == "down" and req.method == "POST":
                        return route.fulfill(status=503, content_type="application/json", body='{"error":"upstream"}',
                                             headers={"Access-Control-Allow-Origin": SITE, "Access-Control-Allow-Credentials": "true"})
                    time.sleep(state["delay"])
                    url = req.url.replace("http://localhost:8787", "http://127.0.0.1:%d" % API_PORT)
                    return route.fulfill(response=route.fetch(url=url))
                page.route("http://localhost:8787/**", handler)
                page.goto(SITE + "/?demo=1#apply")
                page.wait_for_selector("#cp-fab")
                page.wait_for_timeout(1200)
                fab = page.locator("#cp-fab")
                check(label + ": launcher visible", fab.is_visible())
                box = fab.bounding_box()
                check(label + ": launcher on screen", box and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= viewport["width"] and box["y"] + box["height"] <= viewport["height"], box)
                fab.click()
                page.wait_for_selector("#cp:not([hidden])")
                check(label + ": greeting shown", "Hi " in page.locator("#cp-log").inner_text())
                chips = page.locator("#cp-quick button")
                check(label + ": step-aware quick questions (before start)", chips.count() >= 2 and "before I start" in chips.first.inner_text(), chips.all_inner_texts())
                check(label + ": quick question targets >= 44px", all(b["height"] >= 43.5 for b in [c.bounding_box() for c in chips.all()]))
                check(label + ": log is a labelled live region", page.locator("#cp-log").get_attribute("role") == "log" and page.locator("#cp-log").get_attribute("aria-label"))
                # keyboard: Escape closes, focus returns to the launcher
                page.keyboard.press("Escape")
                check(label + ": Escape closes and focus returns", page.locator("#cp").is_hidden() and page.evaluate("document.activeElement && document.activeElement.id") == "cp-fab")
                page.locator("#cp-fab").click()
                # typing indicator while the server is slow
                state["delay"] = 1.5
                page.locator("#cp-q").fill("Which documents do I need?")
                page.locator("#cp-form button").click()
                page.wait_for_selector(".cp-typing", timeout=3000)
                check(label + ": typing indicator while waiting", page.locator("#cp-log").get_attribute("aria-busy") == "true")
                page.wait_for_selector(".cp-typing", state="detached", timeout=60000)
                state["delay"] = 0
                answers = page.locator(".cp-m.a:not(.cp-typing)")
                last = answers.last.inner_text()
                check(label + ": an answer arrived", len(last) > 20, last)
                body = state["bodies"][-1] if state["bodies"] else ""
                check(label + ": request carries language and minimised context", '"lang":"en"' in body and '"context"' in body and "first_name" in body, body[:200])
                # error then retry
                state["mode"] = "down"
                page.locator("#cp-q").fill("How do I take a clear photo?")
                page.locator("#cp-form button").click()
                page.wait_for_selector(".cp-retry", timeout=10000)
                check(label + ": error shows an explanation and Try again", "couldn't reach" in page.locator("#cp-log").inner_text())
                check(label + ": sources shown as readable chips", page.locator(".cp-src li").count() >= 1)
                rb = page.locator(".cp-retry").bounding_box()
                check(label + ": retry target >= 44px", rb["height"] >= 43.5, rb)
                state["mode"] = "ok"
                n_before = page.locator(".cp-m.u").count()
                page.locator(".cp-retry").click()
                page.wait_for_function("document.querySelectorAll('.cp-retry').length===0 && !document.querySelector('.cp-typing')", timeout=60000)
                check(label + ": retry does not repeat the question", page.locator(".cp-m.u").count() == n_before)
                # Hindi UI
                page.locator("#cp .cp-tools").scroll_into_view_if_needed()
                page.keyboard.press("Escape")
                page.evaluate("document.querySelector('[data-ulang=\"hi\"]').click()")
                page.wait_for_timeout(400)
                page.locator("#cp-fab").click()
                page.wait_for_timeout(300)
                qs = page.locator("#cp-quick button").all_inner_texts()
                check(label + ": quick questions follow the UI language", any("दस्तावेज़" in q for q in qs), qs)
                check(label + ": placeholder and send are Hindi", "भेजें" in page.locator("#cp-form button").inner_text())
                if live:
                    state["delay"] = 0
                    page.locator("#cp-quick button").nth(1).click()
                    page.wait_for_function("!document.querySelector('.cp-typing')", timeout=60000)
                    page.wait_for_timeout(500)
                    text = page.locator(".cp-m.a:not(.cp-typing)").last.inner_text()
                    check(label + ": Hindi question gets a Hindi answer", sum(1 for ch in text if "ऀ" <= ch <= "ॿ") > 15, text[:200])
                page.screenshot(path=os.path.join(os.environ.get("PN_SHOT_DIR", tmp), label + ".png"))
                check(label + ": no page errors", not errors, errors)
                ctx.close()
            browser.close()
    finally:
        srv.shutdown()
        api.terminate()
        try:
            api.wait(5)
        except Exception:
            api.kill()
    ok = all(RESULTS)
    print("%d/%d checks passed" % (sum(RESULTS), len(RESULTS)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

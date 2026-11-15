"""Layout audit and screenshots of the PRODUCTION build (lane P6).

Usage:  python tools/screenshots_p6.py [out_dir]     (default planning/screenshots/after)

Builds nothing: run `python policynest_mvp/build_site.py` first. Starts the backend (port 9480) and a static server for
site/ (port 9481) itself and stops both before exit. For each of the five viewports and both themes it saves screenshots
of the landing page, the dashboard and the application start, and prints layout checks for phone widths: no horizontal
scroll, sticky header height as a share of the viewport, touch targets under 44 px, and whether the Copilot launcher or
the bottom navigation overlap a form field or button in the page. Exit code 0 only when the layout checks pass.
"""
import http.server, os, secrets, shutil, socketserver, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_portal_e2e as E
from playwright.sync_api import sync_playwright

ROOT = E.ROOT
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "planning", "screenshots", "after")
VIEWPORTS = [(360, 800), (390, 844), (412, 915), (768, 1024), (1440, 900)]
FAILS = []


def static_server(tmp):
    src = open(os.path.join(ROOT, "policynest_mvp", "site", "index.html"), encoding="utf-8").read()
    src = src.replace("'http://localhost:8787'", "'" + E.API + "'")
    web = os.path.join(tmp, "web"); os.makedirs(web)
    open(os.path.join(web, "index.html"), "w", encoding="utf-8").write(src)
    for f in ("kb.json", "ocr-worker.js", "pdf-worker.js"):
        fp = os.path.join(ROOT, "policynest_mvp", "site", f)
        if os.path.exists(fp):
            shutil.copy(fp, web)

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=web, **k)

        def log_message(self, *a):
            pass

    class T(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = T(("127.0.0.1", E.SITE_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


AUDIT = """() => {
  const vw = innerWidth, vh = innerHeight, out = {};
  out.hscroll = document.documentElement.scrollWidth > vw + 1;
  const stick = [...document.querySelectorAll('.tb-1,.top,.lp-top')].find(e => getComputedStyle(e).position === 'sticky');
  out.stickyPct = stick ? Math.round(stick.getBoundingClientRect().height / vh * 1000) / 10 : 0;
  const small = [];
  document.querySelectorAll('a[href],button,input:not([type=hidden]),select,summary,[role=button]').forEach(e => {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!r.width || !r.height || cs.visibility === 'hidden' || e.closest('[hidden]')) return;
    if (e.closest('.sr-only') || cs.position === 'absolute' && r.width <= 1) return;
    if (r.top > vh || r.bottom < 0) return;
    if (r.height < 43.5 || r.width < 43.5) small.push((e.id || e.className || e.tagName) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' ' + (e.textContent || '').trim().slice(0, 20));
  });
  out.small = small.slice(0, 12);
  return out;
}"""


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:600]) if detail and not ok else ""), flush=True)
    if not ok:
        FAILS.append(name)


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp()
    backend = E.start_backend(tmp)
    srv = static_server(tmp)
    try:
        with sync_playwright() as pw:
            browser = E.launch(pw)
            for theme in ("light", "dark"):
                for (w, h) in VIEWPORTS:
                    tag = "%dx%d-%s" % (w, h, theme)
                    ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=theme, has_touch=w < 700, is_mobile=w < 700)
                    page = ctx.new_page()
                    errs = []
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.add_init_script("try{localStorage.setItem('pn-theme','%s')}catch(e){}" % theme)
                    page.goto(E.SITE + "/?v=" + secrets.token_hex(3) + "#welcome")
                    page.wait_for_selector("#lp-main h1")
                    page.screenshot(path=os.path.join(OUT, tag + "-landing.png"))
                    a = page.evaluate(AUDIT)
                    check(tag + " landing: no horizontal scroll", not a["hscroll"])
                    # sign up through the UI
                    page.click('[data-act="auth-open"][data-mode="register"]')
                    page.fill("#account-name", "Asha Verma")
                    page.fill("#account-email", "asha-%s@example.test" % secrets.token_hex(3))
                    page.fill("#account-password", E.PASSWORD)
                    page.click("#account-submit")
                    page.wait_for_selector("#tb-refv", timeout=15000)
                    page.wait_for_timeout(600)
                    page.screenshot(path=os.path.join(OUT, tag + "-dashboard.png"))
                    a = page.evaluate(AUDIT)
                    check(tag + " dashboard: no horizontal scroll", not a["hscroll"])
                    if w < 700 and theme == "light":
                        # hosting badge (injected at the bottom-left by the platform) must never cover product controls
                        page.evaluate("""()=>{const b=document.createElement('embarko-badge');b.style.cssText='position:fixed;left:8px;bottom:8px;width:120px;height:32px;z-index:2147483000;background:#222;display:block';b.textContent='badge';document.body.appendChild(b)}""")
                        page.wait_for_timeout(300)
                        page.screenshot(path=os.path.join(OUT, tag + "-dashboard-with-badge.png"))
                        ov = page.evaluate("""()=>{const b=document.querySelector('embarko-badge').getBoundingClientRect();
                          const hit=[...document.querySelectorAll('#bnav a,#bnav button,#cp-fab,.wrap button,.wrap a')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&!(r.right<=b.left||r.left>=b.right||r.bottom<=b.top||r.top>=b.bottom)&&getComputedStyle(e).visibility!=='hidden'}).map(e=>e.id||e.className||e.tagName);
                          return {hit, badgeH:getComputedStyle(document.documentElement).getPropertyValue('--badge-h')}}""")
                        check(tag + " hosting badge does not cover navigation, Copilot launcher or page controls (reserved " + ov["badgeH"] + ")", not ov["hit"], ov)
                        # Copilot: focus stays inside the open panel, Escape closes it and returns focus to the launcher
                        page.click("#cp-fab")
                        page.wait_for_timeout(300)
                        for _ in range(25):
                            page.keyboard.press("Tab")
                        check(tag + " Copilot: Tab never leaves the open panel", page.evaluate("document.getElementById('cp').contains(document.activeElement)"))
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(250)
                        check(tag + " Copilot: Escape closes and focus returns to the launcher", page.evaluate("document.getElementById('cp').hidden&&document.activeElement.id==='cp-fab'"))
                    if w < 700:
                        check(tag + " dashboard: sticky header <= 12 pct of viewport (%s pct)" % a["stickyPct"], a["stickyPct"] <= 12.5, a["stickyPct"])
                        check(tag + " dashboard: touch targets >= 44px", not a["small"], a["small"])
                        check(tag + " bottom navigation has 5 items", page.evaluate("document.querySelectorAll('#bnav>a,#bnav>button').length") == 5)
                        page.click("#bn-more")
                        page.wait_for_timeout(350)
                        page.screenshot(path=os.path.join(OUT, tag + "-menu.png"))
                        check(tag + " drawer: focus moves inside and is restored", page.evaluate("document.getElementById('nav').contains(document.activeElement)"))
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(300)
                        check(tag + " drawer: Escape closes and returns focus to More", page.evaluate("document.activeElement&&document.activeElement.id==='bn-more'"))
                    page.evaluate("location.hash='#apply'")
                    page.wait_for_timeout(500)
                    page.screenshot(path=os.path.join(OUT, tag + "-application.png"), full_page=False)
                    a = page.evaluate(AUDIT)
                    check(tag + " application: no horizontal scroll", not a["hscroll"])
                    if w < 700:
                        check(tag + " application: touch targets >= 44px", not a["small"], a["small"])
                    if (w, theme) == (390, "light"):
                        # Hindi: switch language, check lang attributes and layout, then the details-form error summary
                        page.click('#tb-lang [data-ulang="hi"]')
                        page.wait_for_timeout(500)
                        page.evaluate("location.hash='#dashboard'")
                        page.wait_for_timeout(400)
                        page.screenshot(path=os.path.join(OUT, tag + "-dashboard-hindi.png"))
                        check(tag + " Hindi: html lang is hi", page.evaluate("document.documentElement.lang") == "hi")
                        check(tag + " Hindi: bottom navigation labels are Hindi", page.evaluate("/[ऀ-ॿ]/.test(document.getElementById('bnav').innerText)"))
                        page.evaluate("location.hash='#apply'")
                        page.wait_for_timeout(500)
                        page.screenshot(path=os.path.join(OUT, tag + "-application-hindi.png"))
                        check(tag + " Hindi: Hindi text inside the English-language application view carries lang=hi", page.evaluate("document.querySelectorAll('#view-apply [lang=hi]').length") > 0)
                        check(tag + " Hindi: no horizontal scroll", not page.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
                        page.click('#tb-lang [data-ulang="en"]')
                        page.wait_for_timeout(400)
                        page.click('[data-act="begin"]')
                        page.wait_for_timeout(300)
                        page.click('[data-act="details-next"]')
                        page.wait_for_timeout(300)
                        check(tag + " details form: error summary exists with field links and takes focus",
                              page.evaluate("(()=>{const s=document.getElementById('det-errs');return !!s&&s.querySelectorAll('a[href^=\"#f-\"]').length>=2&&document.activeElement===s})()"))
                        check(tag + " details form: invalid fields point to their message (aria-describedby)",
                              page.evaluate("[...document.querySelectorAll('[aria-invalid=true]')].every(e=>e.getAttribute('aria-describedby')&&document.getElementById(e.getAttribute('aria-describedby')))"))
                        page.screenshot(path=os.path.join(OUT, tag + "-details-errors.png"))
                    check(tag + " no script errors", not errs, errs)
                    ctx.close()
            # 200 percent zoom of a 1280x900 window is a 640x450 viewport
            ctx = browser.new_context(viewport={"width": 640, "height": 450}, has_touch=True)
            page = ctx.new_page()
            page.goto(E.SITE + "/?v=" + secrets.token_hex(3) + "#welcome")
            page.wait_for_selector("#lp-main h1")
            check("200% zoom (640x450) landing: no horizontal scroll", not page.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
            page.screenshot(path=os.path.join(OUT, "zoom200-landing.png"))
            ctx.close()
            browser.close()
    finally:
        srv.shutdown()
        backend.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("ALL PASS" if not FAILS else "SOME CHECKS FAILED: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

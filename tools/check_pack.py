"""Static check pack (PRD §16.2 items 1, 2, 7 plus a JS syntax check).

Run from the project root:  python tools/check_pack.py
Exit code 0 = all pass. Prints one line per check.
"""
import hashlib, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "policynest_mvp", "PolicyNest.html")
PINNED = "c206388747e8381e0ce21f7677cfb83594b51db9f6581b6aca3f1d1ed9824350"  # re-pinned 15 Nov: FR-27 wording in rejectReasons; 600 predictions identical

# FR-36 and RB §8: phrases that must not appear anywhere in the app source.
BANNED = [
    "About 2 minutes",
    "Many agents pass on their second try",
    "reply to this message",
]

def main():
    ok = True
    html = open(SRC, encoding="utf-8").read()

    # 1. Engine hash (ADR 0001): from "/* ENGINE:START" up to, not including, "/* ENGINE:END */", CRLF -> LF.
    a, b = html.find("/* ENGINE:START"), html.find("/* ENGINE:END */")
    block = html[a:b].replace("\r\n", "\n")
    h = hashlib.sha256(block.encode("utf-8")).hexdigest()
    same = h == PINNED
    print(("PASS" if same else "FAIL") + " engine hash " + h[:16] + ("" if same else " (pinned " + PINNED[:16] + "; the engine block changed: re-run the evaluation)"))
    ok &= same

    # 2. JS syntax: every inline <script> block must parse, in the demo build and in the production build
    # (the source holds both variants of demo-only code between DEMO:START / DEMO:ELSE / DEMO:END markers).
    mark = re.compile(r"(?:/\*|<!--)DEMO:START(?:\*/|-->)(.*?)(?:(?:/\*|<!--)DEMO:ELSE(?:\*/|-->)(.*?))?(?:/\*|<!--)DEMO:END(?:\*/|-->)", re.S)
    scripts = []
    for mode in ("demo", "prod"):
        built = mark.sub(lambda m: m.group(1) if mode == "demo" else (m.group(2) or ""), html)
        scripts += re.findall(r"<script>(.*?)</script>", built, flags=re.S)
    bad = 0
    for i, s in enumerate(scripts):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
            t.write(s)
            p = t.name
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
        os.unlink(p)
        if r.returncode:
            bad += 1
            print("FAIL js syntax in script " + str(i) + ": " + (r.stderr.strip().splitlines() or [""])[-1][:200])
            print("     " + "\n     ".join(r.stderr.strip().splitlines()[:4]))
    if not bad:
        print("PASS js syntax (" + str(len(scripts)) + " script blocks, demo and prod builds)")
    ok &= bad == 0

    # 3. Banned phrases (FR-36).
    hits = [p for p in BANNED if p.lower() in html.lower()]
    print(("PASS" if not hits else "FAIL") + " banned phrases" + ("" if not hits else ": " + "; ".join(hits)))
    ok &= not hits

    # 4. Build (key check, kb build).
    r = subprocess.run([sys.executable, os.path.join(ROOT, "policynest_mvp", "build_site.py")], capture_output=True, text=True, cwd=ROOT)
    print(("PASS" if r.returncode == 0 else "FAIL") + " build_site.py" + ("" if r.returncode == 0 else ": " + (r.stderr or r.stdout).strip()[-300:]))
    ok &= r.returncode == 0

    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

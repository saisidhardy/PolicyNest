"""Production build check: site/index.html must not contain demo, specimen or test-scenario wording or controls.

Run:  python tools/check_prod_build.py     (build first:  python policynest_mvp/build_site.py)
Exit code 0 only when none of the forbidden strings appears. Also checks that BUILD_MODE is "prod" and that the demo
build (site-demo/index.html, if present) still has its test controls, so the two builds really differ.
Honest disclosure of simulated external checks is allowed in production and is not on this list.
"""
import os, re, sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = [
    "demo controls", "demo environment", "this demo", "demo role", "demo only", "demo:", "(demo)", "demo fast",
    "demo pass", "demonstration", "view as", "view-as", "load sample", "sample applicant", "synthetic",
    "use specimen", "specimen", "test scenario", "scenario", "persona", "data-act=\"sample\"", "data-spec=",
    "role-sel", "role-box", "डेमो",
]

def main():
    ok = True
    path = os.path.join(ROOT, "policynest_mvp", "site", "index.html")
    html = open(path, encoding="utf-8").read()
    low = html.lower()
    # "personal" is ordinary wording (personal PAN, personal data); only whole-word "persona(s)" counts.
    hits = []
    for f in FORBIDDEN:
        if f == "persona":
            n = len(re.findall(r"\bpersonas?\b", low))
        else:
            n = low.count(f.lower())
        if n:
            hits.append("%s x%d" % (f, n))
    print(("PASS" if not hits else "FAIL") + " production build has no forbidden demo strings" + ("" if not hits else ": " + "; ".join(hits)))
    ok &= not hits
    m = re.search(r'var BUILD_MODE="(\w+)"', html)
    good = bool(m) and m.group(1) == "prod"
    print(("PASS" if good else "FAIL") + " production build BUILD_MODE is prod" + ("" if good else " (found %s)" % (m.group(1) if m else "none")))
    ok &= good
    dpath = os.path.join(ROOT, "policynest_mvp", "site-demo", "index.html")
    if os.path.isfile(dpath):
        d = open(dpath, encoding="utf-8").read()
        good = 'var BUILD_MODE="demo"' in d and "Demo controls" in d and 'data-act="spec-all"' in d
        print(("PASS" if good else "FAIL") + " demo build keeps its test controls")
        ok &= good
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

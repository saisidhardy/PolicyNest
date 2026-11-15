"""Rebuild site/index.html (the hosted copy) from PolicyNest.html (the source).

Run from anywhere:  python policynest_mvp/build_site.py
PolicyNest.html has no <html>/<head>/<body> tags (the claude.ai artifact viewer adds them),
so this wraps it into a standalone page and copies the two worker shim files.
"""
from pathlib import Path

here = Path(__file__).resolve().parent
src = (here / "PolicyNest.html").read_text(encoding="utf-8")
cut = src.index("</style>") + len("</style>")
page = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + src[:cut]
    + '\n</head>\n<body style="margin:0">\n'
    + src[cut:]
    + "\n</body>\n</html>\n"
)
site = here / "site"
site.mkdir(exist_ok=True)
vitals = here.parent / 'node_modules' / 'web-vitals' / 'dist' / 'web-vitals.iife.js'
if vitals.is_file():
    (site / 'web-vitals.iife.js').write_bytes(vitals.read_bytes())
(site / "index.html").write_text(page, encoding="utf-8")
for name in ("ocr-worker.js", "pdf-worker.js"):
    (site / name).write_text((here / name).read_text(encoding="utf-8"), encoding="utf-8")
# Tesseract core wasm, served same-origin: the small core build loads its .wasm from
# the worker's own folder (site root), avoiding the data: URL that Embarko's CSP blocks.
for wasm in (here / "vendor").glob("*.wasm"):
    (site / wasm.name).write_bytes(wasm.read_bytes())

# Onboarding Copilot knowledge base: heading-sized chunks of the rulebook and reference docs,
# searched in the browser (BM25). The PS-01 Bible is left out: it is pitch material, not rules.
import json, re
root = here.parent
CORPUS = [
    ("03_RULEBOOK_AND_REGULATIONS/PS-01_ONBOARDING_RULEBOOK_V3_2.md", "Rulebook"),
    ("08_REFERENCE_MATERIALS/IRDAI_REGULATORY_FRAMEWORK_REFERENCE.md", "IRDAI reference"),
    ("03_RULEBOOK_AND_REGULATIONS/REGULATORY_REQUIREMENTS_MATRIX.md", "Regulatory matrix"),
    ("05_SPECIMEN_DOCUMENTS/SPECIMEN_DEFECT_TAXONOMY_GUIDE.md", "Defect guide"),
    ("07_WORKFLOW_AND_BUSINESS_LOGIC/04_CONSOLIDATED_REWORK_ENGINE.md", "Rework spec"),
    ("07_WORKFLOW_AND_BUSINESS_LOGIC/02_NAME_MATCHING_AND_IDENTITY_TAXONOMY.md", "Name-matching spec"),
]
chunks = []
for rel, label in CORPUS:
    p = root / rel
    if not p.is_file():
        print("KB: missing", rel)
        continue
    head, buf = label, []
    def flush():
        text = "\n".join(buf).strip()
        # long sections are split at ~1600 characters on paragraph breaks
        while text:
            part = text[:1600]
            if len(text) > 1600 and "\n\n" in part:
                part = part[: part.rfind("\n\n")]
            text = text[len(part):].strip()
            if len(part) > 40:
                sec = re.match(r"#+\s*([\d.]+)", head)
                cite = f"{label} §{sec.group(1).rstrip('.')}" if sec else label
                chunks.append({"id": len(chunks), "src": rel, "cite": cite,
                               "head": re.sub(r"^#+\s*", "", head), "text": part})
    for line in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^#{1,3}\s", line):
            flush(); buf = []; head = line
        else:
            buf.append(line)
    flush()
# Applicants must never see fraud wording (rulebook §8, ADR 0002). Internal sentences and table rows
# (fraud-desk handling) are removed; a passage left too short is dropped. Only applicant-safe passages ship,
# to the site (offline rulebook answers) and to the proxy (which runs its own retrieval).
BANNED = re.compile(r"\b(fraud\w*|fake|forged|forgery|tamper\w*|suspicious)\b", re.I)
def applicant_text(text):
    out = []
    for line in text.splitlines():
        if not BANNED.search(line):
            out.append(line)
        elif not line.lstrip().startswith("|"):  # prose or list item: drop only the sentences that carry the term
            kept = [s for s in re.split(r"(?<=[.!?])\s+", line) if not BANNED.search(s)]
            if kept and re.sub(r"[\s\-*>#|:]", "", " ".join(kept)):
                out.append(" ".join(kept))
        # a table row with the term is dropped whole
    return "\n".join(out).strip()
safe, redacted = [], 0
for c in chunks:
    t = applicant_text(c["text"])
    if t != c["text"]:
        redacted += 1
    if len(t) > 40 and not BANNED.search(c["head"]):
        safe.append(dict(c, id=len(safe), text=t, audience="applicant"))
for c in safe:
    if BANNED.search(c["text"]) or BANNED.search(c["head"]):
        raise SystemExit(f"Refusing to build: banned wording left in passage {c['cite']}")
kb = json.dumps(safe, ensure_ascii=False)
(site / "kb.json").write_text(kb, encoding="utf-8")
(here / "copilot_api" / "kb.json").write_text(kb, encoding="utf-8")
print("KB:", len(safe), "applicant passages from", len(chunks), "chunks;", redacted, "had internal wording removed")

# Secrets never ship: the Copilot key lives only in .env / the proxy app's env vars.
env = root / ".env"
key = ""
if env.is_file():
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            key = line.split("=", 1)[1].strip()
for f in site.rglob("*"):
    if f.is_file() and f.suffix in (".html", ".js", ".json"):
        t = f.read_text(encoding="utf-8", errors="ignore")
        if "sk-ant-" in t or (key and not key.startswith("your-") and key in t):
            raise SystemExit(f"Refusing to build: an API key appears in {f}")
# FR-57: warn (never fail) when the engine block has changed since the evaluation was measured.
# Same canonicalisation as tools/check_pack.py: text from "/* ENGINE:START" up to "/* ENGINE:END */", CRLF -> LF.
import hashlib
import json as _json
a, b = src.find("/* ENGINE:START"), src.find("/* ENGINE:END */")
engine_now = hashlib.sha256(src[a:b].replace("\r\n", "\n").encode("utf-8")).hexdigest() if a >= 0 and b > a else ""
res_path = root / "eval" / "out" / "eval_results.json"
measured = ""
if res_path.is_file():
    measured = str(_json.loads(res_path.read_text(encoding="utf-8")).get("engine_sha256", ""))
if not engine_now:
    print("WARNING: engine block markers not found; evaluation hash not checked")
elif not measured:
    print("WARNING: eval/out/eval_results.json has no engine_sha256; evaluation hash not checked")
elif engine_now != measured:
    print("WARNING: engine hash " + engine_now[:12] + " differs from the evaluation's " + measured[:12] + ": the Evaluation page figures were measured on different code. Re-run eval/run_eval.js.")
else:
    print("Engine hash " + engine_now[:12] + " matches eval/out/eval_results.json")
print("Built", site / "index.html")

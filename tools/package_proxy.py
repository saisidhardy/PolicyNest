"""Build the deploy tarball for the policynest-copilot proxy and print its file list.

Excludes secrets, local state and tests: .env*, __pycache__, *.sqlite3*, test_*.py, .local, and anything
that looks like a key or token file. Usage:  python tools/package_proxy.py [output.tar.gz]
The default output is app.tar.gz in the system temp folder. It never uploads anything.
"""
import fnmatch
import os
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "policynest_mvp", "copilot_api")
EXCLUDE_DIRS = {"__pycache__", ".local", ".git", ".venv", "venv", "node_modules"}
EXCLUDE_FILES = [".env*", "*.sqlite3*", "*.sqlite", "*.db", "test_*.py", "*.pyc", "*.log", "*.pem", "*.key"]


def wanted(name):
    return not any(fnmatch.fnmatch(name, p) for p in EXCLUDE_FILES)


def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for f in sorted(filenames):
            if wanted(f):
                full = os.path.join(dirpath, f)
                files.append((full, os.path.relpath(full, SRC).replace(os.sep, "/")))
    return files


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "policynest-copilot.tar.gz")
    files = collect()
    with tarfile.open(out, "w:gz") as tar:
        for full, arc in files:
            tar.add(full, arcname=arc)
    bad = [a for _, a in files if not wanted(os.path.basename(a))]
    assert not bad, bad
    print("package:", out)
    for _, arc in files:
        print("  " + arc)
    print(len(files), "files,", os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()

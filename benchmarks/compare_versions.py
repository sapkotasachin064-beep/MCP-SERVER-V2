"""A/B correctness benchmark — compare this working tree against an older ref.

Runs every check in ``correctness_suite.py`` against two checkouts. Each check
runs in its OWN subprocess, so a crash (e.g. a matplotlib-in-thread SIGSEGV) is
recorded as a miss instead of taking down the whole run.

    python benchmarks/compare_versions.py                 # vs origin/main
    python benchmarks/compare_versions.py v1.0.0          # vs a tag/ref
    python benchmarks/compare_versions.py --json out.json # also dump JSON

The older ref is checked out into a throwaway git worktree, benchmarked, and
removed. The "new" side is always the current repository checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SUITE = os.path.join(HERE, "correctness_suite.py")
PY = sys.executable


def _run(cmd, cwd, repo_on_path):
    env = {**os.environ, "PYTHONPATH": repo_on_path}
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


def list_checks():
    out = _run([PY, SUITE, "--list"], REPO, REPO)
    checks = []
    for line in out.stdout.splitlines():
        if "\t" in line:
            name, cat = line.split("\t", 1)
            checks.append((name.strip(), cat.strip()))
    return checks


def run_one(repo, suite, name):
    try:
        r = subprocess.run(
            [PY, suite, name],
            cwd=repo,
            env={**os.environ, "PYTHONPATH": repo},
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    last = (r.stdout.strip().splitlines() or [""])[-1].strip()
    if r.returncode == 0 and last in ("PASS", "FAIL"):
        return "pass" if last == "PASS" else "fail"
    if r.returncode in (-11, 139):
        return "crash"
    return "miss"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ref = args[0] if args else "origin/main"
    json_out = None
    if "--json" in sys.argv:
        json_out = sys.argv[sys.argv.index("--json") + 1]

    checks = list_checks()
    wt = tempfile.mkdtemp(prefix="acadmcp_bench_")
    subprocess.run(["git", "-C", REPO, "worktree", "add", "--quiet", wt, ref], check=True)
    # The OLD worktree runs the CURRENT suite file (kept outside both trees on
    # PYTHONPATH would be cleaner, but the suite only imports `backends.*`, so we
    # pass an absolute suite path and point cwd/PYTHONPATH at the old repo).
    try:
        rows = []
        for name, cat in checks:
            o = run_one(wt, SUITE, name)
            n = run_one(REPO, SUITE, name)
            rows.append({"check": name, "category": cat, "old": o, "new": n})
    finally:
        subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", wt])

    total = len(rows)
    op = sum(r["old"] == "pass" for r in rows)
    npass = sum(r["new"] == "pass" for r in rows)
    summary = {
        "baseline_ref": ref,
        "total": total,
        "old_pass": op,
        "new_pass": npass,
        "old_pct": round(100 * op / total, 1),
        "new_pct": round(100 * npass / total, 1),
        "fixed": sum(r["old"] != "pass" and r["new"] == "pass" for r in rows),
        "regressed": sum(r["old"] == "pass" and r["new"] != "pass" for r in rows),
    }
    print(f"{'CHECK':<32} {'CATEGORY':<13} {'baseline':<8} {'current':<8}")
    print("-" * 66)
    for r in rows:
        mark = (
            " ->FIXED"
            if (r["old"] != "pass" and r["new"] == "pass")
            else (" !!REGRESS" if (r["old"] == "pass" and r["new"] != "pass") else "")
        )
        print(f"{r['check']:<32} {r['category']:<13} {r['old']:<8} {r['new']:<8}{mark}")
    print("-" * 66)
    print(
        f"baseline {ref}: {op}/{total} ({summary['old_pct']}%)   "
        f"current: {npass}/{total} ({summary['new_pct']}%)   "
        f"fixed: {summary['fixed']}  regressed: {summary['regressed']}"
    )
    if json_out:
        with open(json_out, "w") as fh:
            json.dump({"summary": summary, "rows": rows}, fh, indent=2)


if __name__ == "__main__":
    main()

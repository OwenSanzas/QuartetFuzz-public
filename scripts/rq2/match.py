#!/usr/bin/env python3
"""RQ2 entry-selection match (paper, RQ2).

    python3 scripts/rq2/match.py work/rq2/<model>

A gold target g matches a set of functions E iff some e in E has the same
base name as g (namespace and template arguments stripped), or e is a direct
callee of g in the project's call graph (benchmark/callgraphs/).

    LG       E = the LG's entry functions
    Harness  E = the functions called in the first-draft harness

Prints the table per prompt group (w/ target, w/o target, all) and writes
<dir>/match.json.
"""
from __future__ import annotations

import json
import lzma
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from harness.checker.callgraph import CallGraph, short_name  # noqa: E402

CG_DIR = REPO / "benchmark" / "callgraphs"
_CALL = re.compile(r"([A-Za-z_][\w:]*)\s*(?:<[^;(){}]*>)?\s*\(")
_TMP = Path(tempfile.mkdtemp(prefix="rq2cg-"))
_graphs: dict[str, CallGraph | None] = {}


def graph(case_id: str) -> CallGraph | None:
    index = json.loads((CG_DIR / "index.json").read_text())
    name = index.get(case_id)
    if not name:
        return None
    if name not in _graphs:
        xz = CG_DIR / (name + ".xz")
        db = _TMP / name
        if xz.exists():
            with lzma.open(xz) as s, open(db, "wb") as d:
                shutil.copyfileobj(s, d)
            _graphs[name] = CallGraph(db)
        else:
            _graphs[name] = None
    return _graphs[name]


def callee_names(g: CallGraph | None, target: str) -> set[str]:
    if g is None:
        return set()
    return {g.funcs[c].name for f in g.resolve(target) for c in g.callees.get(f.id, ())}


def matches(target: str, funcs: set[str], callees: set[str]) -> bool:
    names = {short_name(f) for f in funcs if f}
    return short_name(target) in names or bool(names & callees)


def main() -> int:
    d = Path(sys.argv[1])
    rows = []
    for f in sorted(d.glob("*/result.json")):
        r = json.loads(f.read_text())
        cal = callee_names(graph(r["case_id"]), r["target_function"])
        h = f.parent / "harness.txt"
        called = set(_CALL.findall(h.read_text())) if h.exists() else set()
        r["lg_match"] = matches(r["target_function"], set(r["lg_entries"]), cal)
        r["harness_match"] = bool(called) and matches(r["target_function"], called, cal)
        rows.append(r)
    out = {}
    print(f"{'Stage':8} {'Prompt':12} {'match':>8}")
    for stage in ("lg", "harness"):
        for grp, label in (("with", "w/ target"), ("without", "w/o target"), (None, "All")):
            sel = [r for r in rows if grp is None or r["group"] == grp]
            n = sum(r[f"{stage}_match"] for r in sel)
            out[f"{stage}/{label}"] = [n, len(sel)]
            print(f"{stage:8} {label:12} {n:>4}/{len(sel)}")
    (d / "match.json").write_text(json.dumps({"summary": out, "cases": rows}, indent=1) + "\n")
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

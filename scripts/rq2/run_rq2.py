#!/usr/bin/env python3
"""RQ2 (target selection): Logic Group + first-draft harness for one task.

    python3 scripts/rq2/run_rq2.py <task> [--model claude-sonnet-5] [--out work/rq2]

The functionality prompt comes from benchmark/rq2_prompts.jsonl: 60 tasks
name the target function, 40 describe the feature only.  The LG agent gets
only that prompt (no target function, Mode A) and explores the task's source
tree with code_view and static_analysis tools; the generator then writes a
first-draft harness from the prompt and the LG.  Nothing is built or fuzzed.

Writes <out>/<model>/<task>/{lg.json, harness.txt, result.json}.  Run
scripts/setup_case.py <task> first (reproduce_rq2.sh does).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from run_qf_case import QF_WORK, load_case  # noqa: E402

PROMPTS = REPO / "benchmark" / "rq2_prompts.jsonl"

GEN_SYSTEM = """You write libFuzzer harnesses for C/C++ libraries.
Given a functionality request and a Logic Group (the entry functions chosen
for it), write one harness that defines
LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) and drives the entry
functions with data derived from the fuzz input.  Output the harness source
only, in one code block."""


def prompt_for(task: str) -> dict:
    for line in PROMPTS.read_text().splitlines():
        r = json.loads(line)
        if r["task"] == task:
            return r
    raise SystemExit(f"{task}: not in {PROMPTS}")


async def run(task: str, model: str, out: Path) -> dict:
    from agent.llm_client import LLMClient
    from harness.checker.callgraph import CallGraph
    from harness.checker.lg_agent import LogicGroupAgent
    from harness.checker.static import StaticIndex
    from harness.checker.tools.context import CheckerContext

    p = prompt_for(task)
    case = load_case(task)
    oss_project = case["oss_fuzz_project"]
    src_root = QF_WORK / "src" / oss_project
    upstream = case["bench"]["version_pins"]["upstream_path"]
    project_path = src_root / upstream.removeprefix("/src/")
    if not project_path.is_dir():
        raise SystemExit(f"{project_path} missing: run scripts/setup_case.py {task}")

    ctx = CheckerContext(
        project=case["project"],
        project_path=project_path,
        oss_fuzz_project_dir=QF_WORK / "ossfuzz_view" / oss_project,
        allowed_roots=[src_root],
        static_index=StaticIndex.load(case["project"]),
        callgraph=CallGraph.load(case["case_id"], case["project"]),
        dynamic_runner=None,
        llm_model=model,
    )

    # Stage 1: Logic Group from the functionality prompt alone.
    lg_agent = LogicGroupAgent(ctx=ctx, functionality_prompt=p["prompt"])
    lg_agent.model = model
    lg_result = await lg_agent.run()
    lg = lg_result.parsed
    out.mkdir(parents=True, exist_ok=True)
    if lg_result.trajectory:
        lg_result.save_trajectory(out / "lg_trajectory.jsonl")
    entries = list(lg.entries) if lg else []
    if lg is not None:
        lg.save_json(out / "lg.json")

    # Stage 2: first-draft harness (no build).
    harness = ""
    gen_cost = 0.0
    if lg is not None:
        user = (f"{p['prompt']}\n\n## Logic Group\nName: {lg.name}\n"
                f"Description: {lg.description}\n"
                f"Entry functions: {', '.join(lg.entries)}\n")
        if lg.core:
            user += f"Core functions: {', '.join(lg.core[:20])}\n"
        resp = await LLMClient().create(model=model, system=GEN_SYSTEM,
                                        messages=[{"role": "user", "content": user}],
                                        max_tokens=8192)
        m = re.search(r"```[a-zA-Z+]*\n(.*?)```", resp.content, re.S)
        harness = m.group(1) if m else resp.content
        (out / "harness.txt").write_text(harness)

    result = {
        "task": task, "case_id": case["case_id"], "group": p["group"], "model": model,
        "target_function": p["target_function"], "lg_entries": entries,
        "lg_ok": lg is not None, "harness_ok": bool(harness),
        "lg_cost": getattr(lg_result, "estimated_cost", 0.0),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--model", default=os.environ.get("RQ2_MODEL", "claude-sonnet-5"))
    ap.add_argument("--out", type=Path, default=QF_WORK / "rq2")
    a = ap.parse_args()
    d = a.out / a.model.replace("/", "_") / a.task
    r = asyncio.run(run(a.task, a.model, d))
    print(f"{a.task}: LG entries {r['lg_entries']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

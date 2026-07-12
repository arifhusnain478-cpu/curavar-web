"""
CuraVar command-line interface.

  python -m curavar list
  python -m curavar run <case.json> [--report out.html] [--live]
  python -m curavar run --all --report-dir reports/

By default runs in offline replay mode using the cassettes bundled in each case
file. Pass --live to use the Anthropic API (needs ANTHROPIC_API_KEY); a live run
also re-records the cassettes so the case stays reproducible afterward.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from .io_utils import read_json, write_json, write_text
from .llm import LLMClient
from .pipeline import CuraVarPipeline
from .report import render_report
from .sources import BundledSourceProvider

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _run_case(case_path: str, mode: str, strict: bool = False) -> "tuple":
    prov = BundledSourceProvider(case_path)
    cassettes = prov.cassettes if mode == "replay" else None
    llm = LLMClient(mode=mode, cassettes=cassettes)
    result = CuraVarPipeline(source=prov, llm=llm).run(
        prov.variant, pvs1_features=prov.pvs1_features, strict=strict)

    # If live, persist freshly recorded cassettes back into the case file.
    if mode == "live" and llm.recorded_cassettes:
        case = read_json(case_path)
        case["cassettes"] = llm.recorded_cassettes
        write_json(case_path, case)
    return prov, result


def _print_result(result) -> None:
    s = result.summary()
    print(f"\n  {s['variant']}")
    print(f"  -> {s['classification']}   "
          f"(rules: {s['rule_based']} | points: {s['points_based']} "
          f"[{s['points_score']:+d}])")
    if not s["methods_agree"]:
        print(f"  ~~ {s['reconciliation']}")
    for c in s["activated_criteria"]:
        print(f"     {c['code']:5s} {c['justification']}  [{', '.join(c['evidence'])}]")
    mark = "verified" if s["ledger_verified"] else "FAILED"
    print(f"  ledger: {s['ledger_entries']} entries, integrity {mark}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="curavar", description="Auditable variant curation")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list bundled demo cases")

    b = sub.add_parser("benchmark", help="validate the engine against the truth set")
    b.add_argument("--truth", default=os.path.join(DATA_DIR, "truth_set.json"),
                   help="path to a truth-set JSON")

    t = sub.add_parser("triage", help="triage all bundled cases into a worklist")
    t.add_argument("--report", help="write an HTML triage dashboard here")
    t.add_argument("--live", action="store_true", help="use the Anthropic API")

    r = sub.add_parser("run", help="run a case (or all)")
    r.add_argument("case", nargs="?", help="path to a case JSON")
    r.add_argument("--all", action="store_true", help="run every bundled case")
    r.add_argument("--report", help="write an HTML report to this path")
    r.add_argument("--report-dir", help="with --all, write one report per case here")
    r.add_argument("--export-ledger", help="write the provenance ledger JSON to this path")
    r.add_argument("--strict", action="store_true", help="exclude circular criteria (PP5/BP6)")
    r.add_argument("--live", action="store_true", help="use the Anthropic API")

    args = p.parse_args(argv)
    mode = "live" if getattr(args, "live", False) else "replay"

    if args.cmd == "triage":
        from .triage import triage_cases, summary_counts
        from .triage_report import render_triage
        paths = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
        paths = [p for p in paths if os.path.basename(p) != "truth_set.json"]
        items = triage_cases(paths, mode=mode)
        counts = summary_counts(items)
        print(f"\n  Triaged {len(items)} variants: "
              f"{counts['REVIEW']} need review, {counts['ACT']} actionable, "
              f"{counts['CLEAR']} auto-clear\n")
        for it in items:
            print(f"  [{it.bucket:6s}] {it.variant:34s} {it.headline.value:22s} "
                  f"({it.points:+d})  {it.reason}")
        if args.report:
            write_text(args.report, render_triage(items))
            print(f"\n  dashboard -> {args.report}")
        return 0

    if args.cmd == "benchmark":
        from .benchmark import run_benchmark, format_report
        print(format_report(run_benchmark(args.truth)))
        return 0

    if args.cmd == "list":
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
            case = read_json(path)
            v = case["variant"]
            print(f"  {os.path.basename(path):32s} {v['gene']} {v['hgvs_c']}")
        return 0

    if args.cmd == "run":
        if args.all:
            paths = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
        elif args.case:
            paths = [args.case]
        else:
            print("error: provide a case path or --all", file=sys.stderr)
            return 2

        for path in paths:
            prov, result = _run_case(path, mode, strict=getattr(args, "strict", False))
            _print_result(result)
            if args.export_ledger:
                write_text(args.export_ledger, result.ledger.to_json())
                print(f"  ledger -> {args.export_ledger}")
            if args.report_dir:
                os.makedirs(args.report_dir, exist_ok=True)
                out = os.path.join(args.report_dir,
                                   f"report_{prov.variant.gene}_{prov.variant.hgvs_c}.html"
                                   .replace(">", "to").replace(" ", "_"))
                write_text(out, render_report(result))
                print(f"  report -> {out}")
            elif args.report:
                write_text(args.report, render_report(result))
                print(f"  report -> {args.report}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line: ``pid run <project>`` and friends."""

from __future__ import annotations

import argparse
import sys

from . import review as rv
from .pipeline import SourceChanged, load_policy_for, load_project, load_working, run_all, stage_enrich
from .topology_io import save_topology


def _print_run(res) -> None:  # noqa: ANN001
    t = res.topology
    pending = sum(1 for o in t.objects().values() if o.provenance.origin == "generated" and o.provenance.status == "pending_review")
    if res.extraction_check is not None:
        ne = sum(1 for x in res.extraction_check if x[0] == "error")
        print(f"extraction check: {ne} errors, {len(res.extraction_check) - ne} warnings (reports/extraction_check.md)")
    print(f"validation      : {'PASS' if res.validation.ok else 'FAIL'} ({len(res.validation.errors)} errors, {len(res.validation.warnings)} warnings)")
    print(f"enrichment      : idempotent={res.idempotent}, {pending} proposals pending review")
    print(f"proteus xml     : round trip {'PASS' if res.roundtrip.ok else 'FAIL'} ({len(res.roundtrip.checks)} checks)")
    if res.onesheet is not None:
        print(f"one-sheet P&ID  : A0, {len(res.onesheet.zones)} plant areas, scale {res.sheet_scale:.2f}, {len(res.sheet_qa or [])} geometric problems")
        g = res.graphics or {}
        print(f"dexpi graphics  : {g.get('placed', 0)} symbols ({g.get('shapes', 0)} catalogue shapes), {g.get('centerlines', 0)} routed pipes, {g.get('labels', 0)} labels")
    bad = sum(len(v) for v in res.qa.values())
    print(f"review pack     : {len(res.layout.sheets)} A3 sheets, {bad} geometric problems")
    if res.register is not None:
        r = res.register
        print(f"decisions       : {len(r.holds)} holds + {len(r.rules)} rule approvals ({len(r.datasheet)} datasheet items)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pid", description="Draft P&IDs from engineering specifications.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="enrich, validate, export, verify, lay out and render a project")
    r.add_argument("project")
    r.add_argument("--rebuild", action="store_true", help="discard working_topology.json and start again from the source snapshot")
    r.add_argument("--no-pdf", action="store_true")
    v = sub.add_parser("review", help="approve or reject proposed additions")
    v.add_argument("project")
    v.add_argument("--list", action="store_true", help="list pending proposals")
    v.add_argument("--approve", nargs="*", metavar="ID")
    v.add_argument("--approve-rule", metavar="RULE")
    v.add_argument("--approve-all", action="store_true")
    v.add_argument("--reject", nargs="*", metavar="ID")
    s = sub.add_parser("status", help="counts of proposals and open points")
    s.add_argument("project")
    n = sub.add_parser("new", help="set up projects/<name> for a new specification (copies it, splits it into page texts, writes templates)")
    n.add_argument("name")
    n.add_argument("spec", help="the specification (PDF with a text layer, .txt or .md)")
    n.add_argument("--language", default="fr")
    n.add_argument("--force", action="store_true")
    c = sub.add_parser("check", help="check an extraction: validation, verbatim quotes, open-point triage - with the fix for each problem")
    c.add_argument("project")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "new":
            from .scaffold import new_project

            root = new_project(args.name, args.spec, language=args.language, force=args.force)
            pages = sorted((root / "source" / "pages").glob("page_*.txt"))
            print(f"created {root}\n  {len(pages)} page texts in source/pages/ - read them all")
            print(f"next: write extraction/extract_{args.name}.py, run it, then: pid check {root} ; pid run {root}")
            return 0
        if args.cmd == "check":
            from .scaffold import check_project

            proj = load_project(args.project)
            probs = check_project(proj.root)
            for lvl, what, fix in probs:
                print(f"{lvl.upper():7} {what}\n        fix: {fix}")
            n_err = sum(1 for p in probs if p[0] == "error")
            print(f"{n_err} error(s), {len(probs) - n_err} warning(s)")
            return 1 if n_err else 0
        if args.cmd == "run":
            res = run_all(args.project, rebuild=args.rebuild, render=not args.no_pdf)
            _print_run(res)
            proj = load_project(args.project)
            files = [proj.sheet_path, proj.xml_path, proj.lists_path, proj.reports / "decision_register.md", proj.svg_path, proj.pdf_path]
            print("\nwrote " + "\n      ".join(str(f) for f in files if f.exists()))
            return 0 if (res.validation.ok and res.roundtrip.ok) else 1
        proj = load_project(args.project)
        topo = load_working(proj)
        if args.cmd == "status":
            pend = rv.pending_ids(topo)
            print(f"{len(pend)} pending proposals; "
                  f"{sum(1 for u in topo.unresolved_requirements if u.status == 'open')} open points")
            return 0
        if args.cmd == "review":
            if args.list:
                for oid in rv.pending_ids(topo):
                    print(oid)
                return 0
            changed = False
            if args.reject:
                res = rv.reject(topo, args.reject)
                for oid, why in res.skipped:
                    print(f"cannot reject {oid}: {why}")
                print(f"rejected {len(res.rejected)}")
                changed = changed or bool(res.rejected)
            if args.approve is not None or args.approve_rule or args.approve_all:
                ids = args.approve if args.approve else None
                res = rv.approve(topo, ids=ids, rule=args.approve_rule)
                for oid, why in res.skipped:
                    print(f"cannot approve {oid}: {why}")
                print(f"approved {len(res.approved)}")
                changed = changed or bool(res.approved)
            if changed:
                save_topology(topo, proj.p("working_topology"))
                print("saved working_topology.json - run `pid run` again to regenerate PDF, XML and reports")
            return 0
    except SourceChanged as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

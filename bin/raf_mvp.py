#!/usr/bin/env python3
"""RAF_ValChecks MVP: recursive contract engine, no external Python packages."""
import argparse
import json
import sys
from pathlib import Path

# Git-audit mode requires a clean checkout; avoid creating bytecode as a side effect.
sys.dont_write_bytecode = True

# Run even when invoked via an absolute path in a consumer checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rafvalchecks.core.contract import Violation, canonical, read_json_document, typed_void
from rafvalchecks.core.graph import build
from rafvalchecks.core.impact import analyze
from rafvalchecks.core.git_coverage import audit_git
from rafvalchecks.core.engine import execute, write_once
from rafvalchecks.core.temporal import analyze_file


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail-closed recursive validation MVP")
    parser.add_argument("command", choices=["plan", "impact", "git-impact", "run", "temporal"])
    parser.add_argument("--topology", help="JSON-only recursive topology")
    parser.add_argument("--base", help="Exact ancestor commit SHA for read-only Git comparison")
    parser.add_argument("--head", help="Exact checked-out HEAD SHA for read-only Git comparison")
    parser.add_argument("--routes", help="Repository-local versioned exact/prefix path-to-scope rules")
    parser.add_argument("--manifest", default=".raf/validation.yml", help="V1 manifest, YAML subset or JSON")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--prior", help="Previous externally trusted local receipt")
    parser.add_argument("--prior-sha256", help="Independently verified raw receipt SHA256")
    parser.add_argument("--changed", action="append", default=[], help="Scope changed; repeat for multiple")
    parser.add_argument("--ttl-hours", type=int, default=24)
    parser.add_argument("--rollback-ref", help="Rollback locator, documented only; not executed")
    parser.add_argument("--output", help="Receipt JSON path, create-only; never overwrites")
    parser.add_argument("--events", help="JSON event observations for read-only temporal audit")
    parser.add_argument("--events-sha256", help="Optional pinned SHA-256 of event input; not producer authentication")
    args = parser.parse_args(argv)
    try:
        if args.command == "temporal":
            if not args.events:
                raise Violation("EVENT_INPUT_REQUIRED")
            data = analyze_file(args.workspace, args.events, args.events_sha256)
        else:
            if not args.topology:
                raise Violation("TOPOLOGY_INPUT_REQUIRED")
            spec, _ = read_json_document(args.topology)
            graph = build(spec)
            data = None
        if args.command == "git-impact":
            data = audit_git(graph, workspace=args.workspace, base=args.base, head=args.head, routes_file=args.routes)
        elif args.command in ("plan", "impact"):
            data = {"version": "raf-valchecks-mvp/1", "result": "PLAN_ONLY", "claim_allowed": False,
                    "graph_sha256": graph["graph_hash"], "root_id": graph["root"]["id"],
                    "order": graph["order"], "dependencies": graph["dependencies"],
                    "slot_count": graph["slot_count"], "extensions": graph["extension_count"],
                    "executions": 0, "impact_advisory": analyze(graph, args.changed)}
        elif args.command == "run":
            data = execute(spec, args.manifest, workspace=args.workspace,
                           prior=args.prior, prior_hash=args.prior_sha256,
                           changed_scopes=args.changed, ttl_hours=args.ttl_hours,
                           rollback_ref=args.rollback_ref)
        serialized = canonical(data) + b"\n"
        if args.output:
            write_once(args.output, serialized)
        sys.stdout.buffer.write(serialized)
        return 0 if data.get("result", data.get("status")) in ("PLAN_ONLY", "PASS_SCOPED", "OBSERVATION_ONLY") else 1
    except Violation as e:
        response = {"version": "raf-valchecks-mvp/1", "result": "BLOCKED",
                    "claim_allowed": False, "token": e.token,
                    "typed_void": typed_void("engine", e.token, "validated_contract", "repair_inputs_and_rerun")}
        sys.stdout.buffer.write(canonical(response) + b"\n")
        return 1
    except (OSError, RuntimeError, ValueError):
        response = {"version": "raf-valchecks-mvp/1", "result": "BLOCKED",
                    "claim_allowed": False, "token": "IO_OR_RUNTIME_ERROR"}
        sys.stdout.buffer.write(canonical(response) + b"\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

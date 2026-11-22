"""Fail-closed scoped graph engine with typed gaps and externally trusted replay.

No arbitrary shell plugins, dynamic imports, network, secrets, or writes are
performed by a specialist. A previous receipt digest is an externally asserted
trust anchor, not a cryptographic signature or independent provenance proof.
"""
import datetime as dt
import hashlib
from pathlib import Path
from .contract import (VERSION, SHA256, canonical, demand, digest, outcome,
                       read_json_document, typed_void, Violation)
from .graph import build
from .impact import analyze
from rafvalchecks.modules import REGISTRY

UTC = dt.timezone.utc


def parse_time(s):
    try:
        demand(isinstance(s, str) and s.endswith("Z"), "RECEIPT_TIME_INVALID")
        date = dt.datetime.fromisoformat(s[:-1] + "+00:00")
        demand(date.utcoffset() == dt.timedelta(0), "RECEIPT_TIME_INVALID")
        return date
    except ValueError:
        raise Violation("RECEIPT_TIME_INVALID")


def trusted_prior(path, trusted_hash):
    if path is None:
        demand(not trusted_hash, "PRIOR_DIGEST_WITHOUT_RECEIPT")
        return None, None
    demand(isinstance(trusted_hash, str) and SHA256.fullmatch(trusted_hash), "PRIOR_UNTRUSTED")
    rawdoc, raw = read_json_document(path)
    demand(hashlib.sha256(raw).hexdigest() == trusted_hash, "PRIOR_HASH_MISMATCH")
    demand(isinstance(rawdoc, dict) and rawdoc.get("version") == VERSION and rawdoc.get("claim_allowed") is False,
           "PRIOR_CONTRACT_INVALID")
    nodes = rawdoc.get("nodes")
    demand(isinstance(nodes, list) and all(isinstance(n, dict) for n in nodes), "PRIOR_NODES_INVALID")
    demand(isinstance(rawdoc.get("manifest_sha256"), str) and SHA256.fullmatch(rawdoc["manifest_sha256"]),
           "PRIOR_MANIFEST_INVALID")
    demand(isinstance(rawdoc.get("source_commit"), str) and len(rawdoc["source_commit"]) == 40,
           "PRIOR_SOURCE_INVALID")
    demand(rawdoc.get("result") == "PASS_SCOPED", "PRIOR_NOT_SUCCESSFUL")
    issued = parse_time(rawdoc.get("issued_at"))
    until = parse_time(rawdoc.get("expires_at"))
    now = dt.datetime.now(UTC)
    demand(issued <= now < until and issued < until, "PRIOR_EXPIRED_OR_FUTURE")
    demand(isinstance(rawdoc.get("receipt_id"), str) and rawdoc["receipt_id"] == digest({k: v for k, v in rawdoc.items() if k != "receipt_id"}),
           "PRIOR_ID_INVALID")
    ids = [n.get("id") for n in nodes]
    demand(len(ids) == len(set(ids)) and all(isinstance(x, str) for x in ids), "PRIOR_DUPLICATE_NODE")
    return rawdoc, trusted_hash


def _node_fingerprint(node, deps, context):
    # Include engine version and manifest source identity. A new source commit
    # invalidates prior assertions; this is intentional conservative behavior.
    local = {k: v for k, v in node.items() if not k.startswith("_") and k != "children"}
    if node["kind"] == "slot":
        local["applied_extensions"] = [
            {"mode": item["mode"], "reason": item["reason"], "module_id": item["module"]["id"]}
            for item in node["_filled"]]
    return digest({"version": VERSION, "node": local,
                   "source_commit": context["source_commit"],
                   "manifest_sha256": context["manifest_sha256"],
                   "deps": {d: deps[d]["fingerprint"] for d in sorted(deps)}})


def execute(spec, manifest_path, *, workspace=".", prior=None, prior_hash=None,
            changed_scopes=None, ttl_hours=24, rollback_ref=None):
    demand(type(ttl_hours) is int and 1 <= ttl_hours <= 24*30, "TTL_INVALID")
    graph = build(spec)
    path = Path(manifest_path)
    demand(path.is_file() and path.stat().st_size <= 1024*1024, "MANIFEST_MISSING_OR_LARGE")
    raw_manifest = path.read_bytes()
    # Fingerprints of the raw manifest follow V1 receipt semantics.
    manifest_hash = hashlib.sha256(raw_manifest).hexdigest()
    # A lightweight index of the declared source; no claim that it is verified.
    # Parsing/verification is the responsibility of the 'manifest' + 'source' leaves.
    try:
        from bin import raf_valcheck as legacy
        declaration, _ = legacy.read_manifest(path)
        legacy.validate_manifest(declaration)
    except (legacy.Invalid, OSError, UnicodeError) as e:
        raise Violation("MANIFEST_PREFLIGHT_INVALID") from e
    source_commit = declaration["project"]["source_commit"]
    previous, prior_digest = trusted_prior(prior, prior_hash)
    if previous:
        demand(previous.get("source_commit") == source_commit and previous.get("manifest_sha256") == manifest_hash,
               "PRIOR_SOURCE_MISMATCH")
    changes = set(changed_scopes or [])
    impact = analyze(graph, list(changes))
    previous_index = {x["id"]: x for x in previous["nodes"]} if previous else {}
    records = {}
    context = {"manifest_path": path, "workspace": Path(workspace), "source_commit": source_commit,
               "manifest_sha256": manifest_hash}
    for nid in graph["order"]:
        node = graph["nodes"][nid]
        required = node.get("required", True)
        deps = {k: records[k] for k in graph["dependencies"][nid]}
        fingerprint = _node_fingerprint(node, deps, context)
        # Hard gate: optional invalid/void children do not erase required gates.
        invalid = [k for k, v in deps.items() if v["result"] in ("BLOCKED", "TOKEN_VAZIO") and graph["nodes"][k].get("required", True)]
        if invalid:
            result = outcome(nid, "BLOCKED", token="REQUIRED_DEPENDENCY_UNMET", details={"dependencies": invalid})
        elif node["kind"] == "slot":
            filled = node["_filled"]
            if not filled:
                token = "REQUIRED_SLOT_UNFILLED" if required or node.get("fallback") == "BLOCKED" else "OPTIONAL_SLOT_UNFILLED"
                result = outcome(nid, "BLOCKED" if required or node.get("fallback") == "BLOCKED" else "TOKEN_VAZIO",
                                 token=token, void=typed_void(nid, token, node["accepts"], "fill_or_compose_in_versioned_extension"))
            else:
                children = [records[item["module"]["id"]] for item in filled]
                blocked = [r["id"] for r in children if r["result"] in ("BLOCKED", "TOKEN_VAZIO")]
                if blocked:
                    result = outcome(nid, "BLOCKED", token="SLOT_MODULE_FAILED", details={"failed": blocked})
                else:
                    result = outcome(nid, "PASS_SCOPED", evidence="DOCUMENTED", details={
                        "scope": "slot_composition_only", "filled_by": [r["id"] for r in children],
                        "override_guard": "never_replaces_required_gate"})
        elif node["kind"] == "group":
            children = [records[c["id"]] for c in node["children"]]
            hard = [r["id"] for r in children if r["result"] == "BLOCKED" or
                    (r["result"] == "TOKEN_VAZIO" and graph["nodes"][r["id"]].get("required", True))]
            if hard:
                result = outcome(nid, "BLOCKED", token="REQUIRED_CHILD_UNMET", details={"children": hard})
            else:
                effective = [r for r in children if r["result"] in ("PASS_SCOPED", "REUSED_VALID_RECEIPT")]
                result = outcome(nid, "PASS_SCOPED" if effective else "TOKEN_VAZIO", evidence="DOCUMENTED" if effective else "TOKEN_VAZIO",
                                 details={"scope": "aggregation_only", "children": [r["id"] for r in children],
                                          "optional_gaps": [r["id"] for r in children if r["result"] == "TOKEN_VAZIO"]},
                                 void=None if effective else typed_void(nid, "NO_COMPLETED_CHILD", "at_least_one_verified_child"))
        else:
            old = previous_index.get(nid)
            scope = node.get("scope", [])
            cache_eligible = (previous and old and node["kind"] not in ("manifest", "source", "receipt", "file_sha256")
                              and old.get("fingerprint") == fingerprint
                              and old.get("result") == "PASS_SCOPED"
                              and old.get("claim_allowed") is False and isinstance(old.get("details"), dict)
                              and nid in impact["unaffected_candidates"] and not changes.intersection(scope))
            if cache_eligible:
                result = outcome(nid, "REUSED_VALID_RECEIPT", evidence="REUSED_EXTERNAL_ASSERTION",
                                 details={"scope": "prior_claim_only", "prior_receipt_id": previous["receipt_id"],
                                          "prior_node": nid, "validity": "caller_supplied_trusted_digest"})
            else:
                result = REGISTRY[node["kind"]](context, node)
        result["fingerprint"] = fingerprint
        result["required"] = required
        result["scope"] = node.get("scope", [])
        if "_extension_point" in node:
            result["extension_point"] = node["_extension_point"]
        if "rollback_ref" in node:
            result["rollback_ref"] = node["rollback_ref"]
        records[nid] = result
    root_record = records[graph["root"]["id"]]
    required_all = [r for r in records.values() if (r["required"] and r["result"] == "TOKEN_VAZIO") or r["result"] == "BLOCKED"]
    status = "PASS_SCOPED" if root_record["result"] == "PASS_SCOPED" and not required_all else "BLOCKED"
    gaps = [r.get("void") for r in records.values() if "void" in r]
    now = dt.datetime.now(UTC)
    expires = now + dt.timedelta(hours=ttl_hours)
    receipt = {"version": VERSION, "claim_allowed": False, "result": status,
               "evidence": "LOCAL_GRAPH_EXECUTION_ONLY", "root_id": graph["root"]["id"],
               "graph_sha256": graph["graph_hash"], "manifest_sha256": manifest_hash,
               "source_commit": source_commit, "source_identity_verified": any(r["evidence"] == "GIT_CHECKOUT_HEAD" for nid, r in records.items() if graph["nodes"][nid]["kind"] == "source"),
               "issued_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
               "expires_at": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
               "predecessor_ref": prior_digest if previous else None,
               "rollback_ref": rollback_ref,
               "changed_scopes_declared": sorted(changes), "impact_advisory": impact, "external_trust_verified": False,
               "nodes": [records[n] for n in graph["order"]], "typed_voids": gaps,
               "counts": {"nodes": len(records), "slots": graph["slot_count"], "extensions": graph["extension_count"],
                          "passed": sum(r["result"] == "PASS_SCOPED" for r in records.values()),
                          "reused": sum(r["result"] == "REUSED_VALID_RECEIPT" for r in records.values()),
                          "blocked": sum(r["result"] == "BLOCKED" for r in records.values()),
                          "void": sum(r["result"] == "TOKEN_VAZIO" for r in records.values())}}
    receipt["receipt_id"] = digest(receipt)
    return receipt


def write_once(path, data):
    """Create-only output: no truncation/overwrite, even on a path collision."""
    import os
    p = Path(path)
    demand(p.parent.is_dir(), "OUTPUT_PARENT_MISSING")
    try:
        with p.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        raise Violation("OUTPUT_ALREADY_EXISTS")
    except OSError:
        raise Violation("OUTPUT_WRITE_FAILED")
    return p

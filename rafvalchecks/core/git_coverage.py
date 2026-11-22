"""Verified local Git change-set coverage; no claim of causal completeness.

A checked-out Git commit and its ancestor are *source evidence*. Path-to-scope
routes are a versioned hypothesis about impact, NOT independent causal proof.
Unmapped, control-plane, unknown-scope or empty changes fail closed to an
all-node advisory with explicit typed gaps. This code only reads local objects.
"""
import hashlib
from pathlib import Path
import re
import subprocess

from .contract import Violation, demand, read_json_document, keys, typed_void, digest
from .impact import analyze

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_CHANGED_PATHS = 4096
MAX_DIFF_BYTES = 1024 * 1024
MAX_ROUTES = 512
# Safety-relevant source changes always require broader revalidation. Rules
# provided by the producer may extend, but cannot narrow this allowlist.
CRITICAL_EXACT = frozenset({"action.yml", "bin/raf_mvp.py", "bin/raf-valcheck.sh"})
CRITICAL_PREFIXES = (".github/workflows/", "rafvalchecks/", "schemas/")


def _git(cwd, *args, allow_nonzero=False):
    try:
        result = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Violation("GIT_INSPECTION_UNAVAILABLE")
    if result.returncode != 0 and not allow_nonzero:
        raise Violation("GIT_INSPECTION_FAILED")
    return result


def _safe_relpath(raw, field, prefix=False):
    demand(isinstance(raw, str) and raw and len(raw) <= 512 and
           not raw.startswith(("/", "./")) and "\\" not in raw and
           "\x00" not in raw and not any(ord(c) < 32 for c in raw), "ROUTE_PATH_INVALID", field)
    pieces = raw.split("/")
    if prefix:
        demand(raw.endswith("/") and all(x not in ("", ".", "..") for x in pieces[:-1]),
               "ROUTE_PREFIX_INVALID", field)
    else:
        demand(all(x not in ("", ".", "..") for x in pieces), "ROUTE_PATH_INVALID", field)
    demand(pieces[0] != ".git", "ROUTE_PATH_INVALID", field)
    return raw


def _read_routes(workspace, route_path, known):
    rel = _safe_relpath(route_path, "routes_file")
    file = workspace / rel
    demand(file.resolve().is_relative_to(workspace) and file.is_file() and not file.is_symlink() and file.stat().st_size <= 1_048_576,
           "ROUTE_FILE_UNAVAILABLE")
    document, data = read_json_document(file)
    keys(document, ["version", "routes"], ["version", "routes"], "routes")
    demand(type(document["version"]) is int and document["version"] == 1,
           "ROUTE_VERSION_UNSUPPORTED")
    routes = document["routes"]
    demand(isinstance(routes, list) and 1 <= len(routes) <= MAX_ROUTES, "ROUTE_COUNT_INVALID")
    normalized = []
    used = set()
    for i, rule in enumerate(routes):
        keys(rule, ["scopes"], ["scopes", "path", "prefix"], f"route[{i}]")
        demand(("path" in rule) != ("prefix" in rule), "ROUTE_SELECTOR_INVALID", str(i))
        kind = "path" if "path" in rule else "prefix"
        match = _safe_relpath(rule[kind], kind, prefix=kind == "prefix")
        demand((kind, match) not in used, "ROUTE_DUPLICATE_SELECTOR", match)
        used.add((kind, match))
        scopes = rule["scopes"]
        demand(isinstance(scopes, list) and bool(scopes) and all(
            isinstance(x, str) and x and len(x) <= 128 for x in scopes) and
            len(scopes) == len(set(scopes)), "ROUTE_SCOPES_INVALID", match)
        normalized.append({"kind": kind, "match": match, "scopes": scopes})
    return normalized, hashlib.sha256(data).hexdigest(), rel, known


def audit_git(graph, *, workspace, base, head, routes_file):
    """Return a read-only, source-verified change coverage and impact *advisory*.

    Git object existence, ancestry and exact clean HEAD are checked locally.
    This does not verify signatures, remote provider ownership, or the accuracy
    of path-to-scope routing. No automatic CI skipping is ever allowed.
    """
    root = Path(workspace).resolve()
    demand(root.is_dir(), "WORKSPACE_NOT_DIRECTORY")
    for val in (base, head):
        demand(isinstance(val, str) and COMMIT.fullmatch(val) and val != "0"*40,
               "GIT_COMMIT_REF_INVALID")
    top = _git(root, "rev-parse", "--show-toplevel").stdout.decode("utf-8", "strict").strip()
    demand(Path(top).resolve() == root, "GIT_WORKSPACE_MISMATCH")
    current = _git(root, "rev-parse", "HEAD").stdout.decode("ascii", "strict").strip()
    demand(current == head, "GIT_HEAD_MISMATCH")
    for sha in (base, head):
        _git(root, "cat-file", "-e", sha + "^{commit}")
    demand(_git(root, "merge-base", "--is-ancestor", base, head, allow_nonzero=True).returncode == 0,
           "GIT_BASE_NOT_ANCESTOR")
    # Local modifications, including untracked changes, invalidate the scoped
    # diff as a description of the current workspace. Ignore only git-ignored
    # files (never use this plan to authorize skipping their security checks).
    demand(not _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout,
           "GIT_WORKSPACE_DIRTY")
    diff = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                "--ignore-submodules=none", "--name-only", "-z", base, head, "--").stdout
    demand(len(diff) <= MAX_DIFF_BYTES, "GIT_DIFF_TOO_LARGE")
    try:
        paths = sorted(set(x.decode("utf-8", "strict") for x in diff.split(b"\x00") if x))
    except UnicodeDecodeError:
        raise Violation("GIT_NON_UTF8_PATH")
    demand(len(paths) <= MAX_CHANGED_PATHS, "GIT_TOO_MANY_CHANGED_PATHS")
    for path in paths:
        _safe_relpath(path, "git_path")
    known = {s for node in graph["nodes"].values() for s in node.get("scope", [])}
    routes, routes_sha256, routes_relpath, _ = _read_routes(root, routes_file, known)
    scopes = set()
    unmatched = []
    matched = []
    for path in paths:
        hits = [r for r in routes if (path == r["match"] if r["kind"] == "path" else
                                  path.startswith(r["match"]))]
        if not hits:
            unmatched.append(path)
        else:
            matched.append(path)
            for r in hits:
                scopes.update(r["scopes"])
    critical = [p for p in paths if p in CRITICAL_EXACT or
                any(p.startswith(q) for q in CRITICAL_PREFIXES) or p == routes_relpath]
    unknown = sorted(scopes - known)
    anomalies = []
    if unmatched:
        anomalies.append("UNMAPPED_GIT_PATH")
    if unknown:
        anomalies.append("UNKNOWN_MAPPED_SCOPE")
    if critical:
        anomalies.append("CONTROL_PLANE_CHANGED")
    if not paths:
        anomalies.append("NO_CHANGED_PATHS_TO_ATTRIBUTE")
    if anomalies:
        plan = analyze(graph, [])
        plan["typed_void"] = typed_void("impact", anomalies[0],
                                         "reviewed_scope_coverage_and_dependency_evidence",
                                         "map_and_review_unknowns_before_reuse")
    else:
        plan = analyze(graph, sorted(scopes))
    plan["change_source_verified"] = True
    plan["scope_mapping_verified"] = False
    # Candidate = only reviewed hypothesis, never a proof of lack of impact.
    plan["runtime_skipping_authorized"] = False
    audit = {
        "result": "TOKEN_VAZIO" if anomalies else "PLAN_ONLY",
        "status": "TOKEN_VAZIO" if anomalies else "PLAN_ONLY",
        "evidence": "LOCAL_GIT_DIFF_OBJECTS_AND_RULES_ONLY",
        "claim_allowed": False,
        "base": base, "head": head,
        "comparison": "ANCESTOR_TO_EXACT_CLEAN_HEAD",
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
        "routes_file": routes_relpath, "routes_sha256": routes_sha256,
        "changed_paths": paths, "mapped_paths": matched,
        "unmapped_paths": unmatched, "critical_paths": critical,
        "mapped_scopes": sorted(scopes), "unknown_mapped_scopes": unknown,
        "coverage": {"changed_paths": len(paths), "matched_paths": len(matched),
                     "unmatched_paths": len(unmatched), "critical_paths": len(critical)},
        "anomaly_tokens": anomalies,
        "hypotheses": [{"path": p, "type": "UNKNOWN_DEPENDENCY_CANDIDATE",
                        "evidence": "TOKEN_VAZIO", "claim_allowed": False}
                       for p in unmatched],
        "impact_advisory": plan,
        "independent_route_authority_verified": False,
        "remote_provenance_verified": False,
        "runtime_skipping_authorized": False,
    }
    audit["audit_id"] = digest(audit)  # deterministic reference, never a signature
    return audit

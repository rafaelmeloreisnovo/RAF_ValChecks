"""Conservative topology impact analysis, NOT a CI scheduler or proof of no change.

Inputs are caller declarations; no source diff is independently inspected here.
Unknown or absent scope declarations intentionally produce a typed uncertainty
and disallow deterministic receipt reuse. Required identity gates always run.
"""
from collections import defaultdict, deque
from .contract import demand, typed_void


def analyze(graph, changed_scopes):
    demand(isinstance(changed_scopes, (list, tuple, set)) and all(
        isinstance(s, str) and bool(s) and len(s) <= 128 for s in changed_scopes),
        "CHANGED_SCOPE_INVALID")
    changes = sorted(set(changed_scopes))
    nodes = graph["nodes"]
    known_scopes = sorted({s for node in nodes.values() for s in node.get("scope", [])})
    unknown = sorted(set(changes) - set(known_scopes))
    missing = not changes

    reverse = defaultdict(list)
    for node, deps in graph["dependencies"].items():
        for dep in deps:
            reverse[dep].append(node)

    reasons = defaultdict(set)
    if missing or unknown:
        for nid in nodes:
            reasons[nid].add("CHANGESET_UNSPECIFIED" if missing else "UNKNOWN_SCOPE_CONSERVATIVE")
    else:
        for nid, node in nodes.items():
            if node["kind"] in ("manifest", "source"):
                reasons[nid].add("MANDATORY_IDENTITY_GATE")
            if set(node.get("scope", [])) & set(changes):
                reasons[nid].add("SCOPE_CHANGED")
            # A leaf without declared scope cannot be proven unaffected.
            if node["kind"] not in ("group", "slot", "manifest", "source") and not node.get("scope"):
                reasons[nid].add("UNSCOPED_SPECIALIST")
        pending = deque(sorted(reasons))
        while pending:
            dep = pending.popleft()
            for nid in sorted(reverse[dep]):
                if nid not in reasons:
                    reasons[nid].add("DEPENDENCY_IMPACT")
                    pending.append(nid)
    affected = [nid for nid in graph["order"] if nid in reasons]
    unaffected = [nid for nid in graph["order"] if nid not in reasons]
    uncertain = missing or bool(unknown)
    return {
        "status": "TOKEN_VAZIO" if uncertain else "PLAN_ONLY",
        "evidence": "TOPOLOGY_ANALYSIS_ONLY",
        "claim_allowed": False,
        "change_source_verified": False,
        "runtime_skipping_authorized": False,
        "known_scopes": known_scopes,
        "declared_changes": changes,
        "unknown_scopes": unknown,
        "affected": affected,
        "unaffected_candidates": [] if uncertain else unaffected,
        "reasons": {nid: sorted(reasons[nid]) for nid in affected},
        "typed_void": typed_void("impact", "CHANGESET_UNSPECIFIED" if missing else "UNKNOWN_SCOPE_DECLARED",
                                 "independently_verified_change_set", "supply_authoritative_diff_and_scopes") if uncertain else None,
    }

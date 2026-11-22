"""Bounded, deterministic, read-only observation and falsifier-candidate engine.

No inference of causality, no network, no device access, no clock synchronization,
no claims about external trust. Bad observations are retained as typed anomaly
counts and excluded from candidate formation; they never become zero or PASS.
"""
from collections import Counter, defaultdict
import hashlib
from pathlib import Path

from .contract import Violation, demand, read_json_document, keys, digest, typed_void, SHA256

MAX_EVENTS = 512
MAX_CHANNELS = 16
MAX_WINDOW_MS = 86_400_000
MAX_OCCURRENCE_MS = 4_102_444_800_000  # year 2100 (no remote clock authority)


def _text(s, at):
    demand(isinstance(s, str) and 1 <= len(s) <= 128 and
           all(c.isalnum() or c in "_.:-/" for c in s), "EVENT_IDENTITY_INVALID", at)
    return s


def _match_greedy(a, b, window):
    """One-to-one time-ordered matches, so one effect cannot support N triggers."""
    used = set()
    lags = []
    for x in a:
        for j, y in enumerate(b):
            if j not in used and 0 < y[0] - x[0] <= window:
                used.add(j)
                lags.append(y[0] - x[0])
                break
    return lags


def analyze_temporal(document, *, dataset_sha256=None, digest_verified=False):
    keys(document, ["version", "events", "window_ms", "min_support"],
         ["version", "events", "window_ms", "min_support"], "observations")
    demand(type(document["version"]) is int and document["version"] == 1, "EVENT_VERSION_UNSUPPORTED")
    events = document["events"]
    demand(isinstance(events, list) and len(events) <= MAX_EVENTS, "EVENT_CAPACITY_EXCEEDED")
    window = document["window_ms"]
    support = document["min_support"]
    demand(type(window) is int and 0 < window <= MAX_WINDOW_MS, "EVENT_WINDOW_INVALID")
    demand(type(support) is int and 2 <= support <= 32, "EVENT_MIN_SUPPORT_INVALID")

    channels = set()
    ids = Counter()
    parsed = []
    for item in events:
        keys(item, ["id", "channel", "occurred_ms", "observed_ms", "source_ref", "quality"],
             ["id", "channel", "occurred_ms", "observed_ms", "source_ref", "receipt_ref", "quality", "value", "parent"],
             "event")
        eid = _text(item["id"], "event.id")
        channel = _text(item["channel"], "event.channel")
        _text(item["source_ref"], "event.source_ref")
        if "receipt_ref" in item:
            _text(item["receipt_ref"], "event.receipt_ref")
        if "parent" in item:
            _text(item["parent"], "event.parent")
        demand(item["quality"] in ("good", "suspect", "missing"), "EVENT_QUALITY_INVALID")
        for field in ("occurred_ms", "observed_ms"):
            v = item[field]
            demand(type(v) is int and 0 <= v <= MAX_OCCURRENCE_MS, "EVENT_TIME_INVALID", field)
        if item["quality"] == "missing":
            demand("value" not in item or item["value"] is None, "MISSING_NOT_ZERO")
        elif "value" in item:
            demand(type(item["value"]) is int and abs(item["value"]) <= 10**12,
                   "EVENT_VALUE_INVALID")
        ids[eid] += 1
        channels.add(channel)
        parsed.append(item)
    demand(len(channels) <= MAX_CHANNELS, "EVENT_CHANNEL_CAPACITY_EXCEEDED")

    anomalies = Counter()
    eligible = defaultdict(list)
    good_count = 0
    for e in parsed:
        reasons = []
        if ids[e["id"]] != 1:
            reasons.append("DUPLICATE_EVENT_ID")
        if e["quality"] != "good":
            reasons.append("SUSPECT_OR_MISSING_OBSERVATION")
        if "receipt_ref" not in e:
            reasons.append("RECEIPT_REFERENCE_MISSING")
        if e["observed_ms"] < e["occurred_ms"]:
            reasons.append("OBSERVED_BEFORE_OCCURRED_CLOCK_OR_DATA")
        if "parent" in e and e["parent"] not in ids:
            reasons.append("UNRESOLVED_PREDECESSOR")
        if reasons:
            anomalies.update(reasons)
        else:
            good_count += 1
            eligible[e["channel"]].append((e["occurred_ms"], e["id"]))
    for ch in eligible:
        eligible[ch].sort()

    hypotheses = []
    names = sorted(eligible)
    for src in names:
        for dst in names:
            if src == dst:
                continue
            lags = _match_greedy(eligible[src], eligible[dst], window)
            if len(lags) < support:
                continue
            backwards = _match_greedy(eligible[dst], eligible[src], window)
            hypotheses.append({
                "from_channel": src, "to_channel": dst,
                "type": "LAGGED_ASSOCIATION_CANDIDATE",
                "distinct_pairs": len(lags), "reverse_order_pairs": len(backwards),
                "median_lag_ms": sorted(lags)[len(lags)//2],
                "ambiguity": "BIDIRECTIONAL_ORDER" if len(backwards) >= support else "UNTESTED_ALTERNATIVE_CAUSES",
                "causality_verified": False, "statistical_significance_verified": False,
                "negative_controls_passed": False,
                "falsifier": "compare_against_shuffled_or_independent_holdout_and_clock_drift"
            })
    hypotheses.sort(key=lambda h:(h["from_channel"], h["to_channel"]))
    # A two-edge path is a higher-level hypothesis, not proof of mediation.
    edges={(h["from_channel"],h["to_channel"]) for h in hypotheses}
    cascades=sorted({(a,b,c) for a,b in edges for x,c in edges if b==x and a!=c and a!=b})
    no_evidence = good_count < support*2
    gaps = []
    if no_evidence:
        gaps.append(typed_void("temporal", "INSUFFICIENT_ELIGIBLE_EVENTS", "independently_observed_repeated_events"))
    if anomalies:
        gaps.append(typed_void("temporal", "EVIDENCE_COVERAGE_GAPS", sorted(anomalies),
                               "reconcile_inputs_without_discarding_bad_observations"))
    gaps.append(typed_void("temporal", "EXTERNAL_SOURCE_TRUST_UNVERIFIED", "independent_source_receipt"))
    result = {
        "version": "raf-valchecks-temporal/1", "status": "TOKEN_VAZIO" if no_evidence or anomalies else "OBSERVATION_ONLY",
        "claim_allowed": False, "causal_claim_allowed": False, "runtime_skipping_authorized": False,
        "input_digest_sha256": dataset_sha256,
        "input_digest_checked": digest_verified,
        "external_source_trust_verified": False,
        "coverage": {"events":len(events), "eligible":good_count,"quarantined":len(events)-good_count,
                     "channels":len(channels),"duplicate_identity_count":sum(n-1 for n in ids.values() if n>1)},
        "anomaly_counts": dict(sorted(anomalies.items())),
        "hypotheses": hypotheses, "cascade_candidates": [list(c) for c in cascades],
        "typed_voids": gaps,
        "evidence": "DETERMINISTIC_LOCAL_EVENT_ORDERING_ONLY"
    }
    result["analysis_id"] = digest(result)
    return result


def analyze_file(workspace, relative_path, expected_sha256=None):
    demand(isinstance(relative_path, str) and relative_path and not relative_path.startswith(("/", "./"))
           and "\\" not in relative_path and all(x not in ("", ".", "..") for x in relative_path.split("/")),
           "EVENT_PATH_INVALID")
    root = Path(workspace).resolve()
    path = root / relative_path
    demand(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink(), "EVENT_FILE_UNAVAILABLE")
    document, raw = read_json_document(path, max_bytes=1_048_576)
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        demand(isinstance(expected_sha256, str) and SHA256.fullmatch(expected_sha256),"EVENT_DIGEST_INVALID")
        demand(sha == expected_sha256, "EVENT_DIGEST_MISMATCH")
    return analyze_temporal(document,dataset_sha256=sha,digest_verified=(expected_sha256 is not None))

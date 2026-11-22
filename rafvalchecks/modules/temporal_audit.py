"""Allowlisted, read-only temporal evidence specialist (candidate hypotheses only)."""
from rafvalchecks.core.contract import demand, outcome, typed_void
from rafvalchecks.core.temporal import analyze_file


def check(context, node):
    cfg = node.get("config", {})
    demand(set(cfg) == {"path", "sha256"}, "TEMPORAL_SPECIALIST_CONFIG_INVALID")
    result = analyze_file(context["workspace"], cfg["path"], cfg["sha256"])
    if result["status"] == "TOKEN_VAZIO":
        return outcome(node["id"], "TOKEN_VAZIO", token="TEMPORAL_EVIDENCE_INSUFFICIENT",
                       details=result, void=typed_void(node["id"], "TEMPORAL_EVIDENCE_INSUFFICIENT", "eligible_temporal_events"))
    return outcome(node["id"], "PASS_SCOPED", evidence="EXECUTED_LOCAL", details=result)

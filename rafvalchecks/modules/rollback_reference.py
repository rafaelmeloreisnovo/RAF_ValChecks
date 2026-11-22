"""Specialist: assert a rollback locator exists; does NOT execute rollback."""
from rafvalchecks.core.contract import outcome


def check(ctx, node):
    locator = node.get("config", {}).get("ref") or node.get("rollback_ref")
    if not isinstance(locator, str) or not locator or len(locator) > 512:
        return outcome(node["id"], "BLOCKED", token="ROLLBACK_REFERENCE_MISSING")
    return outcome(node["id"], "PASS_SCOPED", evidence="DOCUMENTED",
                   details={"scope": "rollback_locator_declared_only", "ref": locator,
                            "rollback_executed": False})

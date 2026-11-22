"""Specialist: strict structural manifest verification (not CI checks)."""
import hashlib
from bin import raf_valcheck as legacy
from rafvalchecks.core.contract import outcome


def check(ctx, node):
    try:
        m, raw = legacy.read_manifest(ctx["manifest_path"])
        legacy.validate_manifest(m)
        ctx["manifest"] = m
        ctx["manifest_bytes"] = raw
        return outcome(node["id"], "PASS_SCOPED", evidence="EXECUTED_LOCAL", details={
            "scope": "manifest_contract_only", "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "declared_checks": m["checks"], "checked_project": m["project"]["name"]})
    except legacy.Invalid as exc:
        return outcome(node["id"], "BLOCKED", token=str(exc))
    except OSError:
        return outcome(node["id"], "BLOCKED", token="MANIFEST_IO_ERROR")

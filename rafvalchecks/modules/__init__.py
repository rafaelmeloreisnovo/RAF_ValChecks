"""Specialists expose check(context, node) and must never execute external code."""
from . import file_sha256, identity, manifest, pair_relation, receipt, rollback_reference, temporal_audit

REGISTRY = {
    "manifest": manifest.check,
    "source": identity.check,
    "receipt": receipt.check,
    "file_sha256": file_sha256.check,
    "pair_relation": pair_relation.check,
    "rollback_reference": rollback_reference.check,
    "temporal_audit": temporal_audit.check,
}

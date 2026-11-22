"""Specialist: match declared source to checkout SHA, not an arbitrary string."""
from bin import raf_valcheck as legacy
from rafvalchecks.core.contract import outcome
import os


def check(ctx, node):
    m = ctx.get("manifest")
    if m is None:
        return outcome(node["id"], "BLOCKED", token="MANIFEST_NOT_VERIFIED")
    try:
        head, basis = legacy.get_expected_head()
        if head.lower() != m["project"]["source_commit"].lower():
            raise legacy.Invalid("SOURCE_COMMIT_MISMATCH")
        repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        if repo and repo.lower() != m["project"]["repository"].lower():
            raise legacy.Invalid("SOURCE_REPOSITORY_MISMATCH")
        return outcome(node["id"], "PASS_SCOPED", evidence=("ASSERTED_LOCAL_TEST" if basis == "ASSERTED_LOCAL_TEST" else "GIT_CHECKOUT_HEAD"),
                       details={"scope": "source_identity_only", "basis": basis, "head": head})
    except legacy.Invalid as exc:
        return outcome(node["id"], "BLOCKED", token=str(exc))

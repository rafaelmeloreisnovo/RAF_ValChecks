"""Specialist: digest one local file from a bounded workspace; no network."""
import hashlib
from pathlib import Path
from rafvalchecks.core.contract import outcome, SHA256


def check(ctx, node):
    config = node.get("config", {})
    rel, expected = config.get("path"), config.get("sha256")
    if not isinstance(rel, str) or not rel or rel.startswith("/") or '\\' in rel or not isinstance(expected, str) or not SHA256.fullmatch(expected):
        return outcome(node["id"], "BLOCKED", token="FILE_DIGEST_INPUT_INVALID")
    base = ctx["workspace"].resolve()
    target = base / rel
    try:
        if any(part == ".." for part in Path(rel).parts) or not target.resolve().is_relative_to(base):
            return outcome(node["id"], "BLOCKED", token="PATH_OUTSIDE_WORKSPACE")
        if not target.is_file() or any(p.is_symlink() for p in (target, *target.parents) if p != base and base in p.parents):
            return outcome(node["id"], "BLOCKED", token="FILE_NOT_REGULAR")
        if target.stat().st_size > 32 * 1024 * 1024:
            return outcome(node["id"], "BLOCKED", token="FILE_TOO_LARGE")
        h = hashlib.sha256()
        with target.open("rb") as stream:
            while block := stream.read(65536):
                h.update(block)
        actual = h.hexdigest()
    except (OSError, RuntimeError):
        return outcome(node["id"], "BLOCKED", token="FILE_IO_ERROR")
    if actual != expected:
        return outcome(node["id"], "BLOCKED", token="FILE_HASH_MISMATCH", details={"actual": actual})
    return outcome(node["id"], "PASS_SCOPED", evidence="EXECUTED_LOCAL",
                   details={"scope": "one_file_sha256_only", "sha256": actual, "path": rel})

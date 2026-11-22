"""Specialist: V1 receipt assertion validator; producer authenticity is external."""
from bin import raf_valcheck as legacy
from rafvalchecks.core.contract import outcome
from pathlib import Path
import os


def check(ctx, node):
    path = node.get("config", {}).get("path") or os.environ.get("RAF_RECEIPT", "")
    if not path:
        return outcome(node["id"], "BLOCKED", token="RECEIPT_PATH_MISSING")
    m, raw = ctx.get("manifest"), ctx.get("manifest_bytes")
    if not m:
        return outcome(node["id"], "BLOCKED", token="MANIFEST_NOT_VERIFIED")
    try:
        data = Path(path).read_bytes()
        if len(data) > 1048576:
            raise legacy.Invalid("RECEIPT_TOO_LARGE")
        receipt = legacy.read_json(data.decode("utf-8"))
        legacy.validate_receipt(receipt, data, m, raw)
        return outcome(node["id"], "PASS_SCOPED", evidence="REUSED_EXTERNAL_ASSERTION",
                       details={"scope": "receipt_assertion_contract_only", "receipt_id": receipt["receipt_id"]})
    except (OSError, UnicodeError):
        return outcome(node["id"], "BLOCKED", token="RECEIPT_IO_OR_ENCODING_ERROR")
    except legacy.Invalid as exc:
        return outcome(node["id"], "BLOCKED", token=str(exc))

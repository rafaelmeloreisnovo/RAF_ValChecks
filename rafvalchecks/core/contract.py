"""Small, dependency-free typed evidence primitives for RAF_ValChecks MVP.

An empty observation is never silently converted to zero, success or false.
"""
import hashlib
import json
import re

VERSION = "raf-valchecks-mvp/1"
RESULTS = frozenset({"PASS_SCOPED", "REUSED_VALID_RECEIPT", "BLOCKED", "TOKEN_VAZIO"})
EVIDENCE = frozenset({"EXECUTED_LOCAL", "GIT_CHECKOUT_HEAD", "ASSERTED_LOCAL_TEST", "DOCUMENTED", "REUSED_EXTERNAL_ASSERTION", "TOKEN_VAZIO"})
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class Violation(Exception):
    """A contract is invalid and must fail closed."""
    def __init__(self, token, at=""):
        super().__init__(token)
        self.token = token
        self.at = at


def demand(condition, token, at=""):
    if not condition:
        raise Violation(token, at)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique_pairs(pairs):
    value = {}
    for k, v in pairs:
        demand(k not in value, "DUPLICATE_KEY", k)
        value[k] = v
    return value


def read_json_document(path, max_bytes=1_048_576):
    try:
        from pathlib import Path
        file = Path(path)
        demand(file.is_file(), "DOCUMENT_MISSING", str(file))
        demand(file.stat().st_size <= max_bytes, "DOCUMENT_TOO_LARGE", str(file))
        raw = file.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(Violation("JSON_NONFINITE_NUMBER")))
        return document, raw
    except Violation:
        raise
    except (ValueError, UnicodeError):
        raise Violation("INVALID_JSON", str(path))
    except OSError:
        raise Violation("DOCUMENT_IO_ERROR", str(path))


def keys(value, required, allowed, at):
    demand(isinstance(value, dict), "OBJECT_REQUIRED", at)
    demand(set(required) <= set(value) <= set(allowed), "FIELDS_INVALID", at)


def label(value, at=""):
    demand(isinstance(value, str) and ID.fullmatch(value) is not None, "IDENTIFIER_INVALID", at)
    return value


def typed_void(node_id, reason, expected, recover_by="provide_verifiable_evidence"):
    return {"kind": "TOKEN_VAZIO", "node": node_id, "reason": reason,
            "expected": expected, "recover_by": recover_by, "value": None}


def outcome(node_id, result, *, evidence="TOKEN_VAZIO", token=None, details=None, void=None):
    demand(result in RESULTS and evidence in EVIDENCE, "OUTPUT_CONTRACT_INVALID", node_id)
    record = {"id": node_id, "result": result, "evidence": evidence, "claim_allowed": False,
              "details": details or {}}
    if token is not None:
        record["token"] = token
    if void is not None:
        record["void"] = void
    return record

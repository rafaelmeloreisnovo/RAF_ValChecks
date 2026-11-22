#!/usr/bin/env python3
"""RAF_ValChecks: dependency-free, fail-closed manifest and pinned-receipt preflight.

The parser intentionally supports a conservative YAML subset. Unrecognized YAML
constructs fail closed; there is no implicit code execution or network access.
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEX40 = re.compile(r"[0-9a-fA-F]{40}\Z")
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*\Z")


class Invalid(Exception):
    pass


def stop(code):
    raise Invalid(code)


def pairs_unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            stop("DUPLICATE_KEY")
        out[key] = value
    return out


def parse_scalar(value):
    value = value.strip()
    if not value:
        stop("YAML_EMPTY_SCALAR")
    if value in ("[]", "{}"):
        return [] if value == "[]" else {}
    if value == "true":
        return True
    if value == "false":
        return False
    if value in ("null", "~"):
        return None
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        return int(value)
    if value.startswith('"'):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            stop("YAML_INVALID_QUOTED_SCALAR")
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if value[0] in "[{!&*|>" or value.startswith("<<") or value.endswith(":"):
        stop("UNSUPPORTED_YAML_FEATURE")
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if " #" in value or "\t" in value or value.startswith("-") or "\n" in value:
        stop("UNSUPPORTED_YAML_FEATURE")
    return value


def yaml_subset(source):
    lines = []
    for number, line in enumerate(source.splitlines(), 1):
        if "\t" in line or "\x00" in line:
            stop("UNSUPPORTED_YAML_FEATURE")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("---", "..."):
            stop("UNSUPPORTED_YAML_FEATURE")
        indent = len(line) - len(line.lstrip(" "))
        lines.append((indent, stripped, number))
    if not lines or lines[0][0] != 0:
        stop("YAML_ROOT_INVALID")

    def key_value(part):
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_\-]*):(?:[ ](.*))?", part)
        if not match:
            stop("YAML_INVALID_MAPPING")
        return match.group(1), match.group(2)

    def block(index, indent):
        if index >= len(lines) or lines[index][0] != indent:
            stop("YAML_INDENTATION_INVALID")
        sequence = lines[index][1] == "-" or lines[index][1].startswith("- ")
        result = [] if sequence else {}
        while index < len(lines) and lines[index][0] == indent:
            entry = lines[index][1]
            if sequence:
                if not (entry == "-" or entry.startswith("- ")):
                    stop("YAML_MIXED_COLLECTION")
                rest = entry[1:].strip()
                index += 1
                if not rest:
                    if index >= len(lines) or lines[index][0] <= indent:
                        stop("YAML_MISSING_VALUE")
                    item, index = block(index, lines[index][0])
                elif re.match(r"[A-Za-z_][A-Za-z0-9_\-]*:($| )", rest):
                    key, raw = key_value(rest)
                    obj = {}
                    if raw is None or not raw.strip():
                        if index >= len(lines) or lines[index][0] <= indent:
                            stop("YAML_MISSING_VALUE")
                        val, index = block(index, lines[index][0])
                    else:
                        val = parse_scalar(raw)
                    obj[key] = val
                    if index < len(lines) and lines[index][0] > indent:
                        other, index = block(index, lines[index][0])
                        if not isinstance(other, dict) or any(k in obj for k in other):
                            stop("YAML_INVALID_SEQUENCE_MAPPING")
                        obj.update(other)
                    item = obj
                else:
                    item = parse_scalar(rest)
                    if index < len(lines) and lines[index][0] > indent:
                        stop("YAML_INVALID_SCALAR_CHILD")
                result.append(item)
            else:
                key, raw = key_value(entry)
                if key in result:
                    stop("DUPLICATE_KEY")
                index += 1
                if raw is None or not raw.strip():
                    if index >= len(lines) or lines[index][0] <= indent:
                        stop("YAML_MISSING_VALUE")
                    value, index = block(index, lines[index][0])
                else:
                    value = parse_scalar(raw)
                    if index < len(lines) and lines[index][0] > indent:
                        stop("YAML_INVALID_SCALAR_CHILD")
                result[key] = value
        return result, index

    obj, end = block(0, 0)
    if end != len(lines):
        stop("YAML_INDENTATION_INVALID")
    return obj


def read_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs_unique, parse_constant=lambda _: stop("JSON_INVALID_NUMBER"))
    except (ValueError, UnicodeError):
        stop("INVALID_JSON")


def read_manifest(path):
    if path.suffix.lower() not in (".json", ".yml", ".yaml"):
        stop("UNSUPPORTED_MANIFEST_FORMAT")
    if not path.is_file():
        stop("MANIFEST_MISSING")
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        stop("MANIFEST_TOO_LARGE")
    try:
        content = raw.decode("utf-8")
    except UnicodeError:
        stop("INVALID_UTF8")
    manifest = read_json(content) if path.suffix.lower() == ".json" else yaml_subset(content)
    return manifest, raw


def fields(obj, required, allowed, code):
    if not isinstance(obj, dict) or not required <= obj.keys() or not obj.keys() <= allowed:
        stop(code)


def text_value(value):
    return isinstance(value, str) and len(value) > 0 and len(value) <= 512


def is_sha(value, bits=40):
    return isinstance(value, str) and (HEX40 if bits == 40 else HEX64).fullmatch(value) is not None and any(c != '0' for c in value)


def unique_nonempty_strings(items):
    return isinstance(items, list) and all(text_value(i) for i in items) and len(set(items)) == len(items)


def validate_manifest(m):
    fields(m, {"project", "dependencies", "checks", "policy"}, {"project", "dependencies", "checks", "policy"}, "MANIFEST_FIELDS_INVALID")
    project = m["project"]
    fields(project, {"name", "repository", "source_commit"}, {"name", "repository", "source_commit"}, "PROJECT_FIELDS_INVALID")
    if not text_value(project["name"]) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", project["repository"]):
        stop("PROJECT_IDENTITY_INVALID")
    if not is_sha(project["source_commit"]):
        stop("SOURCE_COMMIT_INVALID")
    dependencies = m["dependencies"]
    if not isinstance(dependencies, list):
        stop("DEPENDENCIES_INVALID")
    names = set()
    for dep in dependencies:
        fields(dep, {"name", "repository", "commit"}, {"name", "repository", "commit", "approved"}, "DEPENDENCY_FIELDS_INVALID")
        if not text_value(dep["name"]) or not text_value(dep["repository"]) or not is_sha(dep["commit"]):
            stop("DEPENDENCY_INVALID")
        if dep["name"] in names:
            stop("DEPENDENCY_DUPLICATE")
        names.add(dep["name"])
        if "approved" in dep and not isinstance(dep["approved"], bool):
            stop("DEPENDENCY_APPROVAL_INVALID")
        if dep.get("approved") is not True:
            stop("DEPENDENCY_NOT_APPROVED")
    if not unique_nonempty_strings(m["checks"]) or not m["checks"]:
        stop("CHECKS_INVALID")
    policy = m["policy"]
    fields(policy, {"updates", "claim_allowed", "reuse_receipts", "recompute", "impact_scope"}, {"updates", "claim_allowed", "reuse_receipts", "artifact_retention_days", "recompute", "impact_scope"}, "POLICY_FIELDS_INVALID")
    if policy["updates"] != "observe_only" or policy["claim_allowed"] is not False or not isinstance(policy["reuse_receipts"], bool):
        stop("POLICY_INVALID")
    if policy["recompute"] not in ("impact_cone_only", "full") or not unique_nonempty_strings(policy["impact_scope"]) or not policy["impact_scope"]:
        stop("IMPACT_SCOPE_INVALID")
    if "artifact_retention_days" in policy and (type(policy["artifact_retention_days"]) is not int or policy["artifact_retention_days"] < 1):
        stop("RETENTION_POLICY_INVALID")


def get_expected_head():
    # Test-only assertion: never accept a caller-supplied SHA on GitHub Actions.
    explicit = os.environ.get("RAF_EXPECTED_COMMIT", "").strip()
    if explicit and os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        if not is_sha(explicit):
            stop("EXPECTED_COMMIT_INVALID")
        return explicit, "ASSERTED_LOCAL_TEST"
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        stop("SOURCE_COMMIT_UNVERIFIED")
    head = result.stdout.strip()
    if not is_sha(head):
        stop("SOURCE_COMMIT_UNVERIFIED")
    return head, "GIT_CHECKOUT_HEAD"


def timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        stop("RECEIPT_TIMESTAMP_INVALID")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        stop("RECEIPT_TIMESTAMP_INVALID")
    return parsed


def validate_receipt(r, data, m, raw_manifest):
    if not m["policy"]["reuse_receipts"]:
        stop("RECEIPT_REUSE_DISABLED")
    digest = os.environ.get("RAF_TRUSTED_RECEIPT_SHA256", "").lower()
    if not HEX64.fullmatch(digest) or not any(x != "0" for x in digest):
        stop("RECEIPT_TRUST_UNVERIFIED")
    if hashlib.sha256(data).hexdigest() != digest:
        stop("RECEIPT_TRUST_HASH_MISMATCH")
    fields(r, {"receipt_id", "source", "result", "evidence", "claim_allowed", "validated_checks", "impact_scope", "issued_at", "expires_at", "rollback_ref", "predecessor_ref", "falsifiers"}, {"receipt_id", "source", "result", "evidence", "claim_allowed", "validated_checks", "impact_scope", "issued_at", "expires_at", "rollback_ref", "predecessor_ref", "falsifiers"}, "RECEIPT_FIELDS_INVALID")
    src = r["source"]
    fields(src, {"repository", "commit", "manifest_hash"}, {"repository", "commit", "manifest_hash", "dependency_commits"}, "RECEIPT_SOURCE_INVALID")
    if r["claim_allowed"] is not False or r["result"] != "PASS_SCOPED" or r["evidence"] not in ("EXECUTED", "REPRODUCED"):
        stop("RECEIPT_EVIDENCE_INSUFFICIENT")
    if not text_value(r["receipt_id"]) or not text_value(r["rollback_ref"]) or not text_value(r["predecessor_ref"]):
        stop("RECEIPT_LINEAGE_INVALID")
    if src["repository"] != m["project"]["repository"] or src["commit"].lower() != m["project"]["source_commit"].lower():
        stop("RECEIPT_SOURCE_MISMATCH")
    if not is_sha(src["manifest_hash"], 64) or src["manifest_hash"].lower() != hashlib.sha256(raw_manifest).hexdigest():
        stop("RECEIPT_MANIFEST_HASH_MISMATCH")
    if not unique_nonempty_strings(r["validated_checks"]) or not set(m["checks"]) <= set(r["validated_checks"]):
        stop("RECEIPT_CHECK_SCOPE_MISMATCH")
    if not unique_nonempty_strings(r["impact_scope"]) or set(r["impact_scope"]) != set(m["policy"]["impact_scope"]):
        stop("RECEIPT_IMPACT_SCOPE_MISMATCH")
    if not unique_nonempty_strings(r["falsifiers"]) or not r["falsifiers"]:
        stop("RECEIPT_FALSIFIERS_MISSING")
    now = dt.datetime.now(dt.timezone.utc)
    issued, expires = timestamp(r["issued_at"]), timestamp(r["expires_at"])
    if issued > now or expires <= issued or expires <= now:
        stop("RECEIPT_EXPIRED_OR_FUTURE")
    deps = src.get("dependency_commits")
    expected_deps = {dep["name"]: dep["commit"].lower() for dep in m["dependencies"]}
    if not isinstance(deps, dict) or deps != expected_deps:
        stop("RECEIPT_DEPENDENCY_SCOPE_MISMATCH")


def main():
    manifest_path = Path(os.environ.get("RAF_MANIFEST", ".raf/validation.yml"))
    receipt_path = os.environ.get("RAF_RECEIPT", "")
    try:
        m, raw = read_manifest(manifest_path)
        validate_manifest(m)
        expected_head, source_identity = get_expected_head()
        if expected_head.lower() != m["project"]["source_commit"].lower():
            stop("SOURCE_COMMIT_MISMATCH")
        repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        if repo and repo.lower() != m["project"]["repository"].lower():
            stop("SOURCE_REPOSITORY_MISMATCH")
        if receipt_path:
            path = Path(receipt_path)
            if not path.is_file():
                stop("RECEIPT_PATH_MISSING")
            data = path.read_bytes()
            if len(data) > 1024 * 1024:
                stop("RECEIPT_TOO_LARGE")
            try:
                r = read_json(data.decode("utf-8"))
            except UnicodeError:
                stop("RECEIPT_INVALID_UTF8")
            validate_receipt(r, data, m, raw)
            print("result=REUSED_VALID_RECEIPT")
            print("scope=PINNED_MANIFEST_AND_RECEIPT_ASSERTIONS")
        else:
            print("result=PASS_SCOPED")
            print("scope=MANIFEST_STRUCTURE_AND_SOURCE_IDENTITY_ONLY")
        print("evidence=EXECUTED_VALIDATOR_ONLY")
        print("source_identity_basis=" + source_identity)
        print("checks_executed_by_validator=manifest_schema,source_identity" + (",receipt_contract" if receipt_path else ""))
        print("claim_allowed=false")
        print("recompute=NOT_COMPUTED")
        return 0
    except (OSError, Invalid) as exc:
        token = str(exc) if isinstance(exc, Invalid) else "IO_ERROR"
        print("result=BLOCKED")
        print("token=" + token)
        print("claim_allowed=false")
        return 1


if __name__ == "__main__":
    sys.exit(main())

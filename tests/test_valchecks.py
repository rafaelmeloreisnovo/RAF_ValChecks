"""Negative contract tests, with no network, external dependency or GitHub token."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "raf_valcheck.py"
SH = ROOT / "bin" / "raf-valcheck.sh"
COMMIT = "7e420be73925c133d77f2e894ea1ae62b8a70d63"
REPO = "rafaelmeloreisnovo/RAF_ValChecks"


def valid():
    return {"project": {"name": "example", "repository": REPO, "source_commit": COMMIT},
            "dependencies": [], "checks": ["provenance", "receipt_integrity"],
            "policy": {"updates": "observe_only", "claim_allowed": False,
                       "reuse_receipts": True, "impact_scope": ["example"],
                       "recompute": "impact_cone_only", "artifact_retention_days": 90}}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "manifest.json"
        self.path.write_text(json.dumps(valid()), encoding="utf-8")

    def invoke(self, *, receipt=None, trusted=None, script=SCRIPT, expected=COMMIT, repo=REPO):
        env = os.environ.copy()
        env.update(RAF_MANIFEST=str(self.path), RAF_EXPECTED_COMMIT=expected, GITHUB_REPOSITORY=repo)
        env.pop("GITHUB_ACTIONS", None)  # Tests use an asserted HEAD, not a cloned repository.
        env.pop("RAF_RECEIPT", None)
        env.pop("RAF_TRUSTED_RECEIPT_SHA256", None)
        if receipt is not None:
            env["RAF_RECEIPT"] = str(receipt)
        if trusted is not None:
            env["RAF_TRUSTED_RECEIPT_SHA256"] = trusted
        command = ["sh", str(script)] if script.suffix == ".sh" else [sys.executable, str(script)]
        p = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout

    def set_manifest(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def assert_block(self, token):
        code, out = self.invoke()
        self.assertEqual(code, 1, out)
        self.assertIn("result=BLOCKED", out)
        self.assertIn("token=" + token, out)
        self.assertNotIn("result=PASS_SCOPED", out)

    def test_json_ok_scoped(self):
        code, out = self.invoke()
        self.assertEqual(code, 0, out)
        self.assertIn("scope=MANIFEST_STRUCTURE_AND_SOURCE_IDENTITY_ONLY", out)
        self.assertIn("checks_executed_by_validator=manifest_schema,source_identity", out)
        self.assertIn("claim_allowed=false", out)

    def test_wrapper_does_not_need_executable_bit(self):
        self.assertEqual(self.invoke(script=SH)[0], 0)

    def test_example_yaml(self):
        self.path = ROOT / "examples" / "validation.yml"
        self.assertEqual(self.invoke()[0], 0)

    def test_missing_manifest(self):
        self.path.unlink()
        self.assert_block("MANIFEST_MISSING")

    def test_missing_required(self):
        m = valid(); del m["project"]["repository"]; self.set_manifest(m)
        self.assert_block("PROJECT_FIELDS_INVALID")

    def test_reject_zero_commit(self):
        m=valid();m["project"]["source_commit"]="0"*40;self.set_manifest(m)
        self.assert_block("SOURCE_COMMIT_INVALID")

    def test_reject_fake_commit(self):
        m=valid();m["project"]["source_commit"]="a"*40;self.set_manifest(m)
        self.assert_block("SOURCE_COMMIT_MISMATCH")

    def test_reject_wrong_repo(self):
        code, out = self.invoke(repo="someone/other")
        self.assertEqual(code, 1);self.assertIn("SOURCE_REPOSITORY_MISMATCH", out)

    def test_reject_dependency_not_approved(self):
        m=valid();m["dependencies"]=[{"name":"lib", "repository":"x/y", "commit":"a"*40}];self.set_manifest(m)
        self.assert_block("DEPENDENCY_NOT_APPROVED")

    def test_reject_policy_true(self):
        m=valid();m["policy"]["claim_allowed"]=True;self.set_manifest(m)
        self.assert_block("POLICY_INVALID")

    def test_reject_duplicate_checks(self):
        m=valid();m["checks"]=["a","a"];self.set_manifest(m)
        self.assert_block("CHECKS_INVALID")

    def test_reject_unknown_fields(self):
        m=valid();m["secret"]="ignore";self.set_manifest(m)
        self.assert_block("MANIFEST_FIELDS_INVALID")

    def test_reject_malformed_json_with_substrings(self):
        self.path.write_text('"source_commit":"'+COMMIT+'", "updates":"observe_only"',encoding="utf-8")
        self.assert_block("INVALID_JSON")

    def test_reject_duplicate_json_key(self):
        self.path.write_text('{"project":{},"project":{}}', encoding="utf-8")
        self.assert_block("DUPLICATE_KEY")

    def test_reject_yaml_anchors(self):
        self.path = Path(self.tmp.name)/"bad.yml"
        self.path.write_text("project: &anchor\n  name: example", encoding="utf-8")
        self.assert_block("UNSUPPORTED_YAML_FEATURE")

    def test_reject_yaml_duplicate_key(self):
        self.path = Path(self.tmp.name)/"bad.yml"
        self.path.write_text("project: hello\nproject: again\n", encoding="utf-8")
        self.assert_block("DUPLICATE_KEY")

    def test_reject_unsupported_manifest_extension(self):
        self.path = Path(self.tmp.name)/"manifest.txt"
        self.path.write_text(json.dumps(valid()), encoding="utf-8")
        self.assert_block("UNSUPPORTED_MANIFEST_FORMAT")

    def test_reject_receipt_missing(self):
        code, out = self.invoke(receipt=Path(self.tmp.name)/"missing.json")
        self.assertEqual(code, 1);self.assertIn("RECEIPT_PATH_MISSING", out)

    def sample_receipt(self):
        now=dt.datetime.now(dt.timezone.utc)
        return {"receipt_id":"r1", "source":{"repository":REPO,"commit":COMMIT,
                  "manifest_hash":hashlib.sha256(self.path.read_bytes()).hexdigest(),"dependency_commits":{}},
                "result":"PASS_SCOPED", "evidence":"EXECUTED", "claim_allowed":False,
                "validated_checks":["provenance","receipt_integrity"], "impact_scope":["example"],
                "issued_at":(now-dt.timedelta(minutes=1)).isoformat().replace("+00:00","Z"),
                "expires_at":(now+dt.timedelta(days=1)).isoformat().replace("+00:00","Z"),
                "rollback_ref":"rollback-test", "predecessor_ref":"parent-test", "falsifiers":["invalid-manifest"]}

    def receipt_run(self, receipt, *, trusted=True):
        path=Path(self.tmp.name)/"receipt.json"
        data=json.dumps(receipt, separators=(",", ":")).encode("utf-8")
        path.write_bytes(data)
        digest=hashlib.sha256(data).hexdigest() if trusted else None
        return self.invoke(receipt=path, trusted=digest)

    def test_receipt_reuse_with_trusted_digest(self):
        code, out=self.receipt_run(self.sample_receipt())
        self.assertEqual(code,0,out);self.assertIn("result=REUSED_VALID_RECEIPT",out)
        self.assertIn("recompute=NOT_COMPUTED",out)

    def test_receipt_missing_trust(self):
        code,out=self.receipt_run(self.sample_receipt(),trusted=False)
        self.assertEqual(code,1);self.assertIn("RECEIPT_TRUST_UNVERIFIED",out)

    def test_receipt_incorrect_digest(self):
        path=Path(self.tmp.name)/"receipt.json";path.write_text(json.dumps(self.sample_receipt()))
        code,out=self.invoke(receipt=path,trusted="a"*64)
        self.assertEqual(code,1);self.assertIn("RECEIPT_TRUST_HASH_MISMATCH",out)

    def test_receipt_mismatched_manifest(self):
        r=self.sample_receipt();r["source"]["manifest_hash"]="a"*64
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_MANIFEST_HASH_MISMATCH",out)

    def test_receipt_expired(self):
        r=self.sample_receipt();r["expires_at"]="2020-01-01T00:00:00Z"
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_EXPIRED_OR_FUTURE",out)

    def test_receipt_scope_mismatch(self):
        r=self.sample_receipt();r["impact_scope"]=["other"]
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_IMPACT_SCOPE_MISMATCH",out)

    def test_receipt_check_missing(self):
        r=self.sample_receipt();r["validated_checks"]=["provenance"]
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_CHECK_SCOPE_MISMATCH",out)

    def test_receipt_wrong_source(self):
        r=self.sample_receipt();r["source"]["commit"]="a"*40
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_SOURCE_MISMATCH",out)

    def test_receipt_fake_evidence(self):
        r=self.sample_receipt();r["evidence"]="DOCUMENTED"
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_EVIDENCE_INSUFFICIENT",out)

    def test_receipt_no_predecessor(self):
        r=self.sample_receipt();r["predecessor_ref"]=""
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_LINEAGE_INVALID",out)

    def test_receipt_reuse_off(self):
        r=self.sample_receipt()
        m=valid();m["policy"]["reuse_receipts"]=False;self.set_manifest(m)
        code,out=self.receipt_run(r);self.assertEqual(code,1);self.assertIn("RECEIPT_REUSE_DISABLED",out)

    def test_receipt_invalid_format(self):
        p=Path(self.tmp.name)/"receipt.json";p.write_text("{not json")
        code,out=self.invoke(receipt=p,trusted=hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(code,1);self.assertIn("INVALID_JSON",out)

    def test_receipt_duplicate_key(self):
        p=Path(self.tmp.name)/"receipt.json";p.write_text('{"receipt_id":"a","receipt_id":"b"}')
        code,out=self.invoke(receipt=p,trusted=hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(code,1);self.assertIn("DUPLICATE_KEY",out)


if __name__ == "__main__":
    unittest.main()

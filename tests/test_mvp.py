"""Offline adversarial tests for recursive typed-void MVP."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rafvalchecks.core.contract import Violation, canonical, digest
from rafvalchecks.core.graph import build
from rafvalchecks.core.impact import analyze
from rafvalchecks.core.engine import execute, write_once

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "examples/topology.mvp.json").read_text())
COMMIT = "7e420be73925c133d77f2e894ea1ae62b8a70d63"
REPO = "rafaelmeloreisnovo/RAF_ValChecks"


def topo():
    return copy.deepcopy(EXAMPLE)


class MVPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name)
        self.manifest = self.ws / "manifest.json"
        m = {"project": {"name": "mvp-test", "repository": REPO, "source_commit": COMMIT},
             "dependencies": [], "checks": ["mvp"],
             "policy": {"updates": "observe_only", "claim_allowed": False,
                        "reuse_receipts": True, "impact_scope": ["mvp"], "recompute": "impact_cone_only"}}
        self.manifest.write_text(json.dumps(m))
        self.env = patch.dict(os.environ, {"RAF_EXPECTED_COMMIT": COMMIT, "GITHUB_REPOSITORY": REPO}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.previous_github_actions = os.environ.pop("GITHUB_ACTIONS", None)
        self.addCleanup(self.restore_github_actions)

    def restore_github_actions(self):
        if self.previous_github_actions is not None:
            os.environ["GITHUB_ACTIONS"] = self.previous_github_actions

    def go(self, spec=None, **opts):
        return execute(spec or topo(), self.manifest, workspace=self.ws, **opts)

    def test_plan_recursive_order(self):
        g = build(topo())
        self.assertIn("root", g["order"])
        self.assertTrue(g["order"].index("manifest") < g["order"].index("source"))
        self.assertEqual(g["slot_count"], 7)

    def test_run_keeps_optional_void_typed(self):
        r = self.go()
        self.assertEqual(r["result"], "PASS_SCOPED")
        self.assertFalse(r["claim_allowed"])
        self.assertEqual(r["counts"]["void"], 7)
        self.assertEqual(r["typed_voids"][0]["value"], None)
        self.assertTrue(any(v["node"] == "evidence-slot" for v in r["typed_voids"]))
        self.assertFalse(r["source_identity_verified"])

    def test_every_specialist_has_extensible_typed_gap(self):
        graph = build(topo())
        for nid in ("root", "manifest", "source", "rollback", "knowledge", "relative"):
            self.assertIn(nid + ".__void", graph["nodes"])
        t = topo()
        t["extensions"] = [{"slot": "relative.__void", "mode": "fill", "reason": "specialize relative module", "module": {
            "id": "relative-specialist", "kind": "rollback_reference", "config": {"ref": "git:optional-reverse"}}}]
        r = self.go(t)
        self.assertEqual(r["result"], "PASS_SCOPED")
        port = next(n for n in r["nodes"] if n["id"] == "relative.__void")
        self.assertEqual(port["result"], "PASS_SCOPED")

    def test_relative_pair_has_explicit_frame(self):
        r = self.go()
        comparison = next(n for n in r["nodes"] if n["id"] == "relative")
        self.assertEqual(comparison["details"]["relation"], "smaller")
        self.assertEqual(comparison["details"]["frame"], "illustrative_scaled_model")

    def test_required_slot_without_fill_blocks(self):
        t = topo()
        t["root"]["children"][-1]["children"][-1]["required"] = True
        r = self.go(t)
        self.assertEqual(r["result"], "BLOCKED")
        self.assertIn("REQUIRED_SLOT_UNFILLED", [n.get("token") for n in r["nodes"]])

    def test_fill_optional_slot_with_nested_group(self):
        t = topo()
        t["extensions"].append({"slot": "evidence-slot", "mode": "fill", "reason": "provide bounded evidence", "module": {
            "id": "provider-group", "kind": "group", "children": [
                {"id": "ref-check", "kind": "rollback_reference", "config": {"ref": "git:reviewed-pr"}},
                {"id": "later", "kind": "slot", "required": False, "accepts": ["file_sha256"], "fallback": "TOKEN_VAZIO"}]}})
        r = self.go(t)
        self.assertEqual(r["result"], "PASS_SCOPED")
        self.assertEqual(r["counts"]["extensions"], 1)
        self.assertGreater(r["counts"]["void"], 1)
        self.assertEqual(next(n for n in r["nodes"] if n["id"] == "evidence-slot")["result"], "PASS_SCOPED")

    def test_compose_two_specialists(self):
        t = topo()
        for i in range(2):
            t["extensions"].append({"slot": "evidence-slot", "mode": "compose", "reason": "independent typed contract", "module": {
                "id": f"pair-{i}", "kind": "pair_relation", "config": {"frame": "model", "assumption": "synthetic sample",
                    "left": {"value": "2", "unit": "cm"}, "right": {"value": "1", "unit": "m"}}}})
        r = self.go(t)
        self.assertEqual(r["result"], "PASS_SCOPED")
        self.assertEqual(r["counts"]["extensions"], 2)

    def test_override_of_gate_rejected(self):
        t = topo()
        t["extensions"] = [{"slot": "manifest", "mode": "fill", "reason": "forbidden replacement", "module": {"id":"fake", "kind":"rollback_reference"}}]
        with self.assertRaisesRegex(Violation, "SLOT_UNKNOWN"):
            build(t)

    def test_slot_wrong_type_rejected(self):
        t = topo()
        t["extensions"] = [{"slot": "evidence-slot", "mode": "fill", "reason": "incompatible type", "module": {"id":"mod", "kind":"source"}}]
        with self.assertRaisesRegex(Violation, "SLOT_TYPE_MISMATCH"):
            build(t)

    def test_duplicate_module_id_fails(self):
        t = topo()
        t["root"]["children"].append({"id":"source", "kind":"rollback_reference"})
        with self.assertRaisesRegex(Violation, "MODULE_ID_DUPLICATE"):
            build(t)

    def test_cycle_fails(self):
        t = topo()
        t["root"]["children"][0]["depends_on"] = ["source"]
        with self.assertRaisesRegex(Violation, "MODULE_CYCLE"):
            build(t)

    def test_source_gate_not_optional(self):
        t = topo(); t["root"]["children"][1]["required"] = False
        with self.assertRaisesRegex(Violation, "MANDATORY_GATE_OPTIONAL"):
            build(t)

    def test_source_must_depend_on_manifest(self):
        t = topo(); del t["root"]["children"][1]["depends_on"]
        with self.assertRaisesRegex(Violation, "SOURCE_MUST_DEPEND_ON_MANIFEST"):
            build(t)

    def test_group_cannot_pass_if_optional_child_fails(self):
        t=topo()
        t["extensions"] = [{"slot":"evidence-slot", "mode":"fill", "reason":"attempt an invalid module", "module": {
            "id":"bad", "kind":"pair_relation", "required":False,
            "config":{"frame":"x", "assumption":"x", "left":{"value":"1", "unit":"m"}, "right":{"value":"1", "unit":"bytes"}}}}]
        self.assertEqual(self.go(t)["result"], "BLOCKED")

    def test_file_sha256_good(self):
        self._fill_file("file", "proof.txt", hashlib.sha256(b"unit test").hexdigest())
        (self.ws / "proof.txt").write_bytes(b"unit test")
        self.assertEqual(self.go(self.t)["result"], "PASS_SCOPED")

    def test_file_sha256_mismatch(self):
        self._fill_file("file", "proof.txt", "a"*64)
        (self.ws / "proof.txt").write_bytes(b"unit test")
        self.assertEqual(self.go(self.t)["result"], "BLOCKED")

    def test_file_path_traversal_blocked(self):
        self._fill_file("file", "../escape.txt", "a"*64)
        self.assertEqual(self.go(self.t)["result"], "BLOCKED")

    def _fill_file(self, nid, filename, sha):
        self.t = topo()
        self.t["extensions"] = [{"slot":"evidence-slot", "mode":"fill", "reason":"bound the file hash", "module": {
            "id":nid, "kind":"file_sha256", "config":{"path": filename,"sha256": sha}}}]

    def test_prior_without_digest_blocked(self):
        previous = self.go()
        p = self.ws / "old.json"; p.write_bytes(canonical(previous))
        with self.assertRaisesRegex(Violation, "PRIOR_UNTRUSTED"):
            self.go(prior=p)

    def test_prior_digest_mismatch_blocked(self):
        previous = self.go()
        p = self.ws / "old.json"; p.write_bytes(canonical(previous))
        with self.assertRaisesRegex(Violation, "PRIOR_HASH_MISMATCH"):
            self.go(prior=p, prior_hash="a"*64)

    def test_prior_selective_reuse(self):
        previous = self.go()
        p = self.ws / "old.json"; p.write_bytes(canonical(previous))
        digest_raw = hashlib.sha256(p.read_bytes()).hexdigest()
        again = self.go(prior=p, prior_hash=digest_raw, changed_scopes=["rollback"])
        relation = next(n for n in again["nodes"] if n["id"] == "relative")
        self.assertEqual(relation["result"], "REUSED_VALID_RECEIPT")
        self.assertEqual(again["result"], "PASS_SCOPED")
        self.assertEqual(again["counts"]["reused"], 1)
        self.assertFalse(again["external_trust_verified"])
        now_changed = self.go(prior=p, prior_hash=digest_raw, changed_scopes=["model"])
        self.assertEqual(next(n for n in now_changed["nodes"] if n["id"] == "relative")["result"], "PASS_SCOPED")

    def test_prior_changed_source_fails(self):
        previous = self.go()
        p = self.ws / "old.json"; p.write_bytes(canonical(previous))
        new_manifest = json.loads(self.manifest.read_text())
        new_manifest["project"]["source_commit"] = "b"*40
        self.manifest.write_text(json.dumps(new_manifest))
        with self.assertRaisesRegex(Violation, "PRIOR_SOURCE_MISMATCH"):
            self.go(prior=p, prior_hash=hashlib.sha256(p.read_bytes()).hexdigest())

    def test_predecessor_and_rollback_locator(self):
        prev = self.go()
        p = self.ws / "prior.json"; p.write_bytes(canonical(prev))
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        r = self.go(prior=p, prior_hash=h, rollback_ref="git:reviewed-revert-pr")
        self.assertEqual(r["predecessor_ref"], h)
        self.assertEqual(r["rollback_ref"], "git:reviewed-revert-pr")

    def test_impact_cone_known_scope_propagates(self):
        plan = analyze(build(topo()), ["model"])
        self.assertEqual(plan["status"], "PLAN_ONLY")
        self.assertIn("relative", plan["affected"])
        self.assertIn("knowledge", plan["affected"])
        self.assertIn("root", plan["affected"])
        self.assertIn("manifest", plan["affected"])  # mandatory identity revalidation
        self.assertIn("source", plan["affected"])
        self.assertIn("rollback", plan["unaffected_candidates"])
        self.assertFalse(plan["runtime_skipping_authorized"])
        self.assertFalse(plan["change_source_verified"])

    def test_impact_unknown_scope_fails_open_to_no_reuse_never(self):
        plan = analyze(build(topo()), ["undocumented_new_scope"])
        self.assertEqual(plan["status"], "TOKEN_VAZIO")
        self.assertEqual(plan["unaffected_candidates"], [])
        self.assertEqual(plan["unknown_scopes"], ["undocumented_new_scope"])
        self.assertEqual(plan["typed_void"]["value"], None)
        self.assertEqual(len(plan["affected"]), len(build(topo())["nodes"]))

    def test_impact_missing_changes_is_uncertain(self):
        plan = analyze(build(topo()), [])
        self.assertEqual(plan["status"], "TOKEN_VAZIO")
        self.assertEqual(plan["unaffected_candidates"], [])
        self.assertEqual(plan["typed_void"]["reason"], "CHANGESET_UNSPECIFIED")

    def test_impact_scope_propagates_through_filled_slot(self):
        t = topo()
        t["extensions"] = [{"slot":"evidence-slot", "mode":"fill", "reason":"specialize impact analysis", "module": {
            "id":"ext-model", "kind":"pair_relation", "scope":["new_specialty"],
            "config":{"frame":"model", "assumption":"synthetic", "left":{"value":"3", "unit":"mm"}, "right":{"value":"5", "unit":"mm"}}}}]
        plan = analyze(build(t), ["new_specialty"])
        for nid in ("ext-model", "evidence-slot", "knowledge", "root"):
            self.assertIn(nid, plan["affected"])

    def test_impact_unknown_or_missing_scope_disables_receipt_reuse(self):
        previous = self.go()
        p = self.ws / "old-impact.json"; p.write_bytes(canonical(previous))
        d = hashlib.sha256(p.read_bytes()).hexdigest()
        for changes in ([], ["not_declared"]):
            again = self.go(prior=p, prior_hash=d, changed_scopes=changes)
            self.assertEqual(again["counts"]["reused"], 0)
            self.assertEqual(again["impact_advisory"]["status"], "TOKEN_VAZIO")
            self.assertFalse(again["claim_allowed"])

    def test_impact_cli_is_read_only_and_explicit(self):
        p = subprocess.run([sys.executable, str(ROOT/"bin"/"raf_mvp.py"), "impact", "--topology",
                            str(ROOT/"examples"/"topology.mvp.json"), "--changed", "model"],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["result"], "PLAN_ONLY")
        self.assertEqual(data["executions"], 0)
        self.assertIn("relative", data["impact_advisory"]["affected"])
        self.assertFalse(data["claim_allowed"])

    def test_invalid_impact_scopes_block(self):
        with self.assertRaisesRegex(Violation, "CHANGED_SCOPE_INVALID"):
            analyze(build(topo()), [42])

    def test_excessive_module_graph_rejected_not_truncated(self):
        t = topo()
        t["root"]["children"].extend({"id":f"bounded{i}", "kind":"rollback_reference", "config":{"ref":"git:readonly"}}
                                     for i in range(300))
        with self.assertRaisesRegex(Violation, "MAX_MODULES_EXCEEDED"):
            build(t)

    def test_excessive_extensions_rejected_without_execution(self):
        t = topo()
        t["extensions"] = [{"slot":"evidence-slot", "mode":"compose", "reason":"bounded extension example",
                             "module":{"id":f"module{i}","kind":"rollback_reference", "config":{"ref":"git:x"}}}
                            for i in range(129)]
        with self.assertRaisesRegex(Violation, "EXTENSIONS_INVALID"):
            build(t)

    def test_output_append_only_refuses_overwrite(self):
        out = self.ws / "receipt.json"
        write_once(out, canonical(self.go()))
        original = out.read_bytes()
        with self.assertRaisesRegex(Violation, "OUTPUT_ALREADY_EXISTS"):
            write_once(out, b"junk")
        self.assertEqual(out.read_bytes(), original)

    def test_command_line_emits_parseable_json(self):
        p = subprocess.run([sys.executable, str(ROOT/"bin"/"raf_mvp.py"), "plan", "--topology", str(ROOT/"examples"/"topology.mvp.json")],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["result"], "PLAN_ONLY")


if __name__ == "__main__":
    unittest.main()

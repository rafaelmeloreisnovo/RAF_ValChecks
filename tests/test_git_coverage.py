"""Adversarial local Git-object coverage tests: no network or provider state."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from rafvalchecks.core.contract import Violation
from rafvalchecks.core.git_coverage import audit_git
from rafvalchecks.core.graph import build

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = json.loads((ROOT / "examples/topology.mvp.json").read_text())
ROUTES = json.loads((ROOT / "examples/change-routes.v1.json").read_text())


class GitCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Unit test")
        self.git("config", "user.email", "test@example.invalid")
        self.write("examples/base.txt", "one")
        self.write("examples/change-routes.v1.json", json.dumps(ROUTES))
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.graph = build(copy.deepcopy(TOPOLOGY))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.ws, text=True, stderr=subprocess.PIPE)

    def write(self, path, content):
        target = self.ws / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self, path="examples/new.txt", content="new"):
        self.write(path, content)
        self.git("add", "-A")
        self.git("commit", "-qm", "next")
        return self.git("rev-parse", "HEAD").strip()

    def analyze(self, head, **opts):
        return audit_git(self.graph, workspace=self.ws, base=opts.get("base", self.base),
                         head=head, routes_file=opts.get("routes_file", "examples/change-routes.v1.json"))

    def test_verified_git_objects_route_expected_scope_without_skip(self):
        head = self.commit()
        p = self.analyze(head)
        self.assertEqual(p["status"], "PLAN_ONLY")
        self.assertEqual(p["mapped_scopes"], ["model"])
        self.assertEqual(p["unmapped_paths"], [])
        self.assertEqual(p["critical_paths"], [])
        self.assertEqual(p["changed_paths"], ["examples/new.txt"])
        self.assertEqual(p["coverage"]["matched_paths"], 1)
        self.assertEqual(p["impact_advisory"]["status"], "PLAN_ONLY")
        self.assertIn("relative", p["impact_advisory"]["affected"])
        self.assertIn("rollback", p["impact_advisory"]["unaffected_candidates"])
        self.assertTrue(p["impact_advisory"]["change_source_verified"])
        self.assertFalse(p["impact_advisory"]["runtime_skipping_authorized"])
        self.assertFalse(p["independent_route_authority_verified"])
        self.assertFalse(p["claim_allowed"])
        self.assertEqual(len(p["audit_id"]), 64)
        self.assertEqual(p["audit_id"], self.analyze(head)["audit_id"])

    def test_unmapped_path_appears_as_candidate_never_silent(self):
        head = self.commit("untracked-in-graph/novel.py")
        p = self.analyze(head)
        self.assertEqual(p["status"], "TOKEN_VAZIO")
        self.assertEqual(p["anomaly_tokens"], ["UNMAPPED_GIT_PATH"])
        self.assertEqual(p["unmapped_paths"], ["untracked-in-graph/novel.py"])
        self.assertEqual(p["hypotheses"][0]["type"], "UNKNOWN_DEPENDENCY_CANDIDATE")
        self.assertEqual(p["impact_advisory"]["unaffected_candidates"], [])
        self.assertEqual(len(p["impact_advisory"]["affected"]), len(self.graph["nodes"]))

    def test_control_plane_change_is_conservatively_all_impacted(self):
        head = self.commit("rafvalchecks/core/engine.py")
        p = self.analyze(head)
        self.assertIn("CONTROL_PLANE_CHANGED", p["anomaly_tokens"])
        self.assertIn("rafvalchecks/core/engine.py", p["critical_paths"])
        self.assertEqual(p["impact_advisory"]["unaffected_candidates"], [])

    def test_routes_self_change_invalidates_scoping(self):
        updated = copy.deepcopy(ROUTES)
        updated["routes"].append({"prefix": "new-dir/", "scopes": ["model"]})
        head = self.commit("examples/change-routes.v1.json", json.dumps(updated))
        p = self.analyze(head)
        self.assertEqual(p["critical_paths"], ["examples/change-routes.v1.json"])
        self.assertEqual(p["status"], "TOKEN_VAZIO")

    def test_unknown_mapped_scope_blocks_all_safe_caching(self):
        updated = copy.deepcopy(ROUTES)
        updated["routes"].append({"prefix": "custom/", "scopes": ["new_unknown_scope"]})
        self.write("examples/change-routes.v1.json", json.dumps(updated))
        self.git("add", ".")
        self.git("commit", "-qm", "routes")
        self.base = self.git("rev-parse", "HEAD").strip()
        head = self.commit("custom/new.txt")
        p = self.analyze(head)
        self.assertEqual(p["unknown_mapped_scopes"], ["new_unknown_scope"])
        self.assertIn("UNKNOWN_MAPPED_SCOPE", p["anomaly_tokens"])
        self.assertEqual(p["impact_advisory"]["unaffected_candidates"], [])

    def test_dirty_workspace_is_rejected(self):
        head = self.commit()
        self.write("local-untracked.txt", "not part of commit")
        with self.assertRaisesRegex(Violation, "GIT_WORKSPACE_DIRTY"):
            self.analyze(head)

    def test_head_mismatch_rejected(self):
        self.commit()
        with self.assertRaisesRegex(Violation, "GIT_HEAD_MISMATCH"):
            self.analyze(self.base)

    def test_non_ancestor_ref_rejected(self):
        self.git("checkout", "-qb", "side", self.base)
        side = self.commit("side.txt")
        self.git("checkout", "-q", "main")
        main = self.commit("main.txt")
        with self.assertRaisesRegex(Violation, "GIT_BASE_NOT_ANCESTOR"):
            self.analyze(main, base=side)

    def test_empty_git_delta_is_not_reuse_authorization(self):
        self.git("commit", "--allow-empty", "-qm", "empty")
        head = self.git("rev-parse", "HEAD").strip()
        p = self.analyze(head)
        self.assertEqual(p["changed_paths"], [])
        self.assertEqual(p["anomaly_tokens"], ["NO_CHANGED_PATHS_TO_ATTRIBUTE"])
        self.assertEqual(p["status"], "TOKEN_VAZIO")

    def test_bad_route_duplicated_selector_rejected(self):
        altered = copy.deepcopy(ROUTES)
        altered["routes"].append(copy.deepcopy(altered["routes"][0]))
        self.write("examples/change-routes.v1.json", json.dumps(altered))
        self.git("add", ".")
        self.git("commit", "-qm", "bad policy")
        self.base = self.git("rev-parse", "HEAD").strip()
        head = self.commit("examples/next.txt")
        with self.assertRaisesRegex(Violation, "ROUTE_DUPLICATE_SELECTOR"):
            self.analyze(head)

    def test_prefix_does_not_match_sibling(self):
        head = self.commit("examples-sibling/file.txt")
        p = self.analyze(head)
        self.assertEqual(p["unmapped_paths"], ["examples-sibling/file.txt"])

    def test_git_rename_counts_both_paths(self):
        self.git("mv", "examples/base.txt", "examples/renamed.txt")
        self.git("commit", "-qm", "rename")
        head = self.git("rev-parse", "HEAD").strip()
        p = self.analyze(head)
        self.assertEqual(p["changed_paths"], ["examples/base.txt", "examples/renamed.txt"])
        self.assertEqual(p["coverage"]["changed_paths"], 2)

    def test_cli_emits_source_verified_advisory_with_no_exec(self):
        head = self.commit()
        p = subprocess.run([sys.executable, str(ROOT / "bin/raf_mvp.py"), "git-impact",
                            "--topology", str(ROOT / "examples/topology.mvp.json"),
                            "--workspace", str(self.ws), "--base", self.base, "--head", head,
                            "--routes", "examples/change-routes.v1.json"],
                           text=True, capture_output=True, timeout=8)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertEqual(result["head"], head)
        self.assertFalse(result["runtime_skipping_authorized"])

    def test_malformed_selector_traversal_rejected(self):
        altered = copy.deepcopy(ROUTES)
        altered["routes"][0]["prefix"] = "../"
        self.write("examples/change-routes.v1.json", json.dumps(altered))
        self.git("add", ".")
        self.git("commit", "-qm", "bad route")
        self.base = self.git("rev-parse", "HEAD").strip()
        head = self.commit()
        with self.assertRaisesRegex(Violation, "ROUTE_PREFIX_INVALID"):
            self.analyze(head)

    def test_changes_do_not_require_network(self):
        # The test repo has no remote configured; verified audit succeeds.
        head = self.commit()
        self.assertEqual(self.analyze(head)["status"], "PLAN_ONLY")
        self.assertFalse(self.analyze(head)["remote_provenance_verified"])


if __name__ == "__main__":
    unittest.main()

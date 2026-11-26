"""Dependency continuity falsifiers: exact Git source, no silent promotion."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rafvalchecks.core.graph import build
from rafvalchecks.core.contract import Violation
from rafvalchecks.core.dependency_continuity import audit_dependency_continuity

ROOT = Path(__file__).resolve().parents[1]
GRAPH = build(json.loads((ROOT / 'examples/topology.mvp.json').read_text()))
ROUTES = json.loads((ROOT / 'examples/change-routes.v1.json').read_text())


def snapshot(version, digest='a' * 64, edge=False):
    return {'schema': 1, 'resolution': 'FULL_TRANSITIVE_RESOLVED',
            'components': [{'id': 'lib:core', 'version': version, 'sha256': digest}],
            'edges': ([{'consumer': 'app', 'dependency': 'lib:core'}] if edge else [])}


def perf(runtime='JVM', metric=12, workload='a', env='device-id'):
    return {'schema': 1, 'runtime': runtime, 'workload_id': workload,
            'environment_id': env, 'samples': 8,
            'metrics': {'alloc_bytes_per_op': metric, 'gc_pause_p99_ms': 2.5}}


class DependencyContinuityTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.write('examples/change-routes.v1.json', ROUTES)
        self.write('build.gradle', 'implementation "lib:core:1.0"')
        self.write('observed/graph.json', snapshot('1.0'))
        self.write('observed/perf.json', perf())
        self.git('add', '.')
        self.git('commit', '-qm', 'stable base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.r = copy.deepcopy(ROUTES)
        self.r['routes'].append({'path':'build.gradle', 'scopes':['model']})
        self.r['routes'].append({'prefix':'observed/', 'scopes':['model']})
        self.write('examples/change-routes.v1.json', self.r)
        self.git('add', '.')
        self.git('commit', '-qm', 'routes pinned')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.PIPE)

    def write(self, name, content):
        f = self.root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(content) if isinstance(content, dict) else content)

    def commit(self, name='build.gradle', content='implementation "lib:core:2.0"'):
        self.write(name, content)
        self.git('add', '.')
        self.git('commit', '-qm', 'candidate')
        return self.git('rev-parse', 'HEAD').strip()

    def audit(self, head, **params):
        return audit_dependency_continuity(GRAPH, workspace=self.root, base=params.get('base', self.base),
            head=head, routes_file='examples/change-routes.v1.json',
            dependency_graph_path=params.get('dep_graph'), perf_snapshot_path=params.get('perf'))

    def tokens(self, r):
        return {x['reason'] for x in r['typed_gaps']}

    def test_modification_alert_and_hold_without_graph(self):
        head = self.commit()
        a = self.audit(head)
        self.assertIn('!!! DEPENDENCY', a['visual_alert'])
        self.assertEqual(a['status'], 'TOKEN_VAZIO')
        self.assertIn('TRANSITIVE_DEPENDENCY_GRAPH_NOT_SUPPLIED', self.tokens(a))
        self.assertIn('GC_ALLOCATION_FRICTION_BASELINE_NOT_SUPPLIED', self.tokens(a))
        self.assertFalse(a['promote_dependency_update_authorized'])
        self.assertFalse(a['runtime_skipping_authorized'])

    def test_asserted_graph_change_retains_unknown_provenance(self):
        self.write('observed/graph.json', snapshot('2.0', 'b' * 64, True))
        head = self.commit()
        a = self.audit(head, dep_graph='observed/graph.json')
        self.assertEqual(a['transitive_graph']['changed'], ['lib:core'])
        self.assertEqual(a['transitive_graph']['edges_added'], [['app', 'lib:core']])
        self.assertFalse(a['transitive_graph']['verified_transitive_graph'])
        self.assertIn('INDEPENDENT_TRANSITIVE_RESOLUTION_NOT_VERIFIED', self.tokens(a))

    def test_gc_allocation_comparable_but_not_performance_claim(self):
        self.write('observed/perf.json', perf(metric=30))
        head = self.commit()
        a = self.audit(head, perf='observed/perf.json')
        self.assertEqual(a['runtime_metrics']['ratios']['alloc_bytes_per_op'], 2.5)
        self.assertIn('PERFORMANCE_REGRESSION_THRESHOLDS_NOT_APPROVED', self.tokens(a))
        self.assertFalse(a['performance_claim_allowed'])

    def test_reused_old_benchmark_is_not_fresh_evidence(self):
        head = self.commit()  # Perf file unchanged in Git object.
        a = self.audit(head, perf='observed/perf.json')
        self.assertIn('PERF_SNAPSHOT_UNCHANGED_FOR_DEPENDENCY_DELTA', self.tokens(a))
        self.assertNotIn('ratios', a['runtime_metrics'])

    def test_partial_gc_coverage_is_gap_even_with_matching_workload(self):
        self.write('observed/perf.json', perf(metric=24))
        head = self.commit()
        a = self.audit(head, perf='observed/perf.json')
        self.assertIn('GC_AND_ALLOCATION_METRIC_COVERAGE_INCOMPLETE', self.tokens(a))
        self.assertFalse(a['performance_claim_allowed'])

    def test_incomparable_hardware_not_silently_accepted(self):
        self.write('observed/perf.json', perf(env='different-device'))
        head = self.commit()
        self.assertIn('PERF_COMPARISON_INCOMPARABLE', self.tokens(self.audit(head, perf='observed/perf.json')))

    def test_snapshot_missing_at_base_is_void(self):
        head = self.commit('build.gradle')
        self.assertIn('TRANSITIVE_SNAPSHOT_MISSING_AT_PINNED_COMMIT',
                      self.tokens(self.audit(head, dep_graph='missing/file.json')))

    def test_no_dependency_metadata_changed_does_not_trigger_false_positive(self):
        head = self.commit('examples/only-code.txt', 'change')
        a = self.audit(head)
        self.assertEqual(a['changed_dependency_paths'], [])
        self.assertEqual(a['priority'], 'NOT_CLASSIFIED')
        self.assertNotIn('TRANSITIVE_DEPENDENCY_GRAPH_NOT_SUPPLIED', self.tokens(a))
        self.assertFalse(a['promote_dependency_update_authorized'])

    def test_boolean_metric_rejected_instead_of_zero(self):
        invalid = perf()
        invalid['metrics']['alloc_bytes_per_op'] = False
        self.write('observed/perf.json', invalid)
        head = self.commit()
        with self.assertRaisesRegex(Violation, 'PERF_METRIC_VALUE_INVALID'):
            self.audit(head, perf='observed/perf.json')

    def test_invalid_digest_in_graph_rejected(self):
        bad = snapshot('2.0')
        bad['components'][0]['sha256'] = 'abc'
        self.write('observed/graph.json', bad)
        head = self.commit()
        with self.assertRaisesRegex(Violation, 'DEPENDENCY_COMPONENT_DIGEST_INVALID'):
            self.audit(head, dep_graph='observed/graph.json')

    def test_mismatched_head_blocked(self):
        self.commit()
        with self.assertRaisesRegex(Violation, 'GIT_HEAD_MISMATCH'):
            self.audit(self.base)

    def test_dirty_checkout_blocked(self):
        head = self.commit()
        self.write('not_committed', 'bad')
        with self.assertRaisesRegex(Violation, 'GIT_WORKSPACE_DIRTY'):
            self.audit(head)

    def test_unmapped_dependency_path_keeps_all_nodes_affected(self):
        head = self.commit('nested/pkg/package-lock.json', '{}')
        a = self.audit(head)
        self.assertIn('nested/pkg/package-lock.json', a['changed_dependency_paths'])
        self.assertIn('UNMAPPED_GIT_PATH', self.tokens(a))
        self.assertEqual(a['git_impact_advisory']['impact_advisory']['unaffected_candidates'], [])

    def test_cli_exit_nonzero_and_loud_alert(self):
        head = self.commit()
        cmd=[sys.executable, str(ROOT/'bin'/'raf_mvp.py'), 'dependency-guard',
             '--topology', str(ROOT/'examples'/'topology.mvp.json'),
             '--workspace', str(self.root), '--routes', 'examples/change-routes.v1.json',
             '--base', self.base, '--head', head]
        p=subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn('!!! DEPENDENCY', json.loads(p.stdout)['visual_alert'])

if __name__ == '__main__':
    unittest.main()

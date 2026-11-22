"""Conservative dependency/GC continuity audit over pinned local Git commits.

A changed build descriptor is a *signal*, not proof of changed resolved deps.
Snapshots are producer assertions, not independent artifacts or trusted metrics.
No build, network call, CI skip, merge, release or performance claim occurs here.
"""
import hashlib
import json
import math
from pathlib import Path

from .contract import Violation, demand, digest, typed_void
from .git_coverage import _git, _safe_relpath, audit_git

MAX_SNAPSHOT_BYTES = 1_048_576
MAX_COMPONENTS = 2048
MAX_EDGES = 8192
MAX_METRICS = 64
JVM_MINIMUM_METRICS = frozenset({'alloc_bytes_per_op', 'gc_pause_p99_ms',
                                 'gc_events_per_1000_ops', 'cpu_ms_per_op', 'peak_rss_bytes'})
NATIVE_MINIMUM_METRICS = frozenset({'alloc_bytes_per_op', 'cpu_ms_per_op', 'peak_rss_bytes'})
DEPENDENCY_NAMES = frozenset({
    'build.gradle', 'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts',
    'gradle.properties', 'gradle.lockfile', 'gradle-wrapper.properties',
    'pom.xml', 'package.json', 'package-lock.json', 'npm-shrinkwrap.json',
    'yarn.lock', 'pnpm-lock.yaml', 'Cargo.toml', 'Cargo.lock',
    'go.mod', 'go.sum', 'pyproject.toml', 'poetry.lock', 'Pipfile.lock',
    'requirements.txt', 'requirements.lock', 'Gemfile.lock',
    'libs.versions.toml', 'dependabot.yml', 'dependabot.yaml',
})
DEPENDENCY_PREFIXES = ('gradle/', '.github/workflows/', '.github/actions/')


def _dependency_metadata(path):
    name = path.rsplit('/', 1)[-1]
    return (name in DEPENDENCY_NAMES or name.startswith('requirements-') and name.endswith('.txt')
            or any(path.startswith(p) for p in DEPENDENCY_PREFIXES))


def _read_git_json(root, sha, relpath):
    """Read a *committed* JSON snapshot, never workspace/untracked bytes."""
    _safe_relpath(relpath, 'snapshot_path')
    out = _git(root, 'show', f'{sha}:{relpath}', allow_nonzero=True)
    if out.returncode:
        return None, None
    raw = out.stdout
    demand(len(raw) <= MAX_SNAPSHOT_BYTES, 'SNAPSHOT_TOO_LARGE')
    try:
        value = json.loads(raw.decode('utf-8', 'strict'))
    except (UnicodeError, ValueError):
        raise Violation('SNAPSHOT_INVALID_JSON')
    demand(isinstance(value, dict), 'SNAPSHOT_NOT_OBJECT')
    return value, hashlib.sha256(raw).hexdigest()


def _parse_graph(obj):
    demand(obj.get('schema') == 1 and obj.get('resolution') == 'FULL_TRANSITIVE_RESOLVED',
           'DEPENDENCY_GRAPH_SCOPE_INVALID')
    components, edges = obj.get('components'), obj.get('edges')
    demand(isinstance(components, list) and len(components) <= MAX_COMPONENTS and
           isinstance(edges, list) and len(edges) <= MAX_EDGES,
           'DEPENDENCY_GRAPH_BOUNDS_INVALID')
    by_id = {}
    for item in components:
        demand(isinstance(item, dict) and set(item) == {'id', 'version', 'sha256'} and
               all(isinstance(item[k], str) and 0 < len(item[k]) <= 256 for k in item),
               'DEPENDENCY_COMPONENT_INVALID')
        name, ver, h = item['id'], item['version'], item['sha256']
        demand(name not in by_id, 'DEPENDENCY_COMPONENT_DUPLICATE')
        demand(len(h) == 64 and all(c in '0123456789abcdef' for c in h),
               'DEPENDENCY_COMPONENT_DIGEST_INVALID')
        by_id[name] = (ver, h)
    arc = set()
    for item in edges:
        demand(isinstance(item, dict) and set(item) == {'consumer', 'dependency'} and
               all(isinstance(v, str) and 0 < len(v) <= 256 for v in item.values()),
               'DEPENDENCY_EDGE_INVALID')
        pair = (item['consumer'], item['dependency'])
        demand(pair not in arc, 'DEPENDENCY_EDGE_DUPLICATE')
        demand(pair[1] in by_id, 'DEPENDENCY_EDGE_UNRESOLVED')
        arc.add(pair)
    return by_id, arc


def _metrics(obj):
    demand(obj.get('schema') == 1 and obj.get('runtime') in ('JVM', 'NATIVE', 'MIXED') and
           isinstance(obj.get('workload_id'), str) and bool(obj['workload_id']) and
           isinstance(obj.get('environment_id'), str) and bool(obj['environment_id']) and
           type(obj.get('samples')) is int and 5 <= obj['samples'] <= 1_000_000,
           'PERF_SNAPSHOT_INCOMPARABLE')
    m = obj.get('metrics')
    demand(isinstance(m, dict) and 0 < len(m) <= MAX_METRICS, 'PERF_METRICS_INVALID')
    for key, v in m.items():
        demand(isinstance(key, str) and 1 <= len(key) <= 80 and
               type(v) in (int, float) and math.isfinite(v) and v >= 0,
               'PERF_METRIC_VALUE_INVALID')
    return m


def audit_dependency_continuity(graph, *, workspace, base, head, routes_file,
                                dependency_graph_path=None, perf_snapshot_path=None):
    """No-promotion audit. Measurements never authorize skipping or merging."""
    changes = audit_git(graph, workspace=workspace, base=base, head=head,
                        routes_file=routes_file)
    root = Path(workspace).resolve()
    touched = [p for p in changes['changed_paths'] if _dependency_metadata(p)]
    signals = []
    gaps = []
    graph_detail = {'state': 'NOT_REQUESTED', 'verified_transitive_graph': False}
    perf_detail = {'state': 'NOT_REQUESTED', 'measured_runtime': False}
    if touched:
        signals.append('DEPENDENCY_OR_BUILD_METADATA_CHANGED')
        # The file change proves *a descriptor changed*, not what resolved.
        if dependency_graph_path is None:
            gaps.append('TRANSITIVE_DEPENDENCY_GRAPH_NOT_SUPPLIED')
            graph_detail['state'] = 'TOKEN_VAZIO'
        else:
            old, h_old = _read_git_json(root, base, dependency_graph_path)
            new, h_new = _read_git_json(root, head, dependency_graph_path)
            graph_detail = {'state': 'TOKEN_VAZIO', 'old_sha256': h_old,
                            'new_sha256': h_new, 'verified_transitive_graph': False}
            if old is None or new is None:
                gaps.append('TRANSITIVE_SNAPSHOT_MISSING_AT_PINNED_COMMIT')
            else:
                oc, oe = _parse_graph(old)
                nc, ne = _parse_graph(new)
                graph_detail.update({
                    'state': 'ASSERTED_GIT_SNAPSHOT_COMPARE',
                    'added': sorted(nc.keys() - oc.keys()),
                    'removed': sorted(oc.keys() - nc.keys()),
                    'changed': sorted(k for k in nc.keys() & oc.keys() if nc[k] != oc[k]),
                    'edges_added': [list(x) for x in sorted(ne - oe)],
                    'edges_removed': [list(x) for x in sorted(oe - ne)],
                })
                if (graph_detail['added'] or graph_detail['removed'] or
                    graph_detail['changed'] or graph_detail['edges_added'] or graph_detail['edges_removed']):
                    signals.append('RESOLVED_GRAPH_SNAPSHOT_CHANGED')
                # A self-reported full graph does not prove that resolution was complete.
                gaps.append('INDEPENDENT_TRANSITIVE_RESOLUTION_NOT_VERIFIED')
        if perf_snapshot_path is None:
            perf_detail['state'] = 'TOKEN_VAZIO'
            gaps.append('GC_ALLOCATION_FRICTION_BASELINE_NOT_SUPPLIED')
        else:
            old, h_old = _read_git_json(root, base, perf_snapshot_path)
            new, h_new = _read_git_json(root, head, perf_snapshot_path)
            perf_detail = {'state': 'TOKEN_VAZIO', 'baseline_sha256': h_old,
                           'candidate_sha256': h_new, 'measured_runtime': False}
            if old is None or new is None:
                gaps.append('PERF_COMPARISON_MISSING_AT_PINNED_COMMIT')
            elif h_old == h_new:
                gaps.append('PERF_SNAPSHOT_UNCHANGED_FOR_DEPENDENCY_DELTA')
            else:
                old_m, new_m = _metrics(old), _metrics(new)
                required = (JVM_MINIMUM_METRICS if old.get('runtime') in ('JVM', 'MIXED')
                            else NATIVE_MINIMUM_METRICS)
                if not required.issubset(old_m) or not required.issubset(new_m):
                    gaps.append('GC_AND_ALLOCATION_METRIC_COVERAGE_INCOMPLETE')
                comparable = all(old[k] == new[k] for k in ('runtime', 'workload_id', 'environment_id'))
                comparable = comparable and old_m.keys() == new_m.keys()
                if not comparable:
                    gaps.append('PERF_COMPARISON_INCOMPARABLE')
                else:
                    perf_detail['state'] = 'ASSERTED_MATCHED_PERF_SNAPSHOTS'
                    perf_detail['ratios'] = {
                        k: (None if old_m[k] == 0 else round(new_m[k] / old_m[k], 6))
                        for k in sorted(old_m)
                    }
                    perf_detail['baseline_samples'] = old['samples']
                    perf_detail['candidate_samples'] = new['samples']
                    if any(v is None for v in perf_detail['ratios'].values()):
                        gaps.append('ZERO_BASELINE_METRIC_RATIO_UNDEFINED')
                    gaps.append('PERFORMANCE_SOURCE_AUTHENTICITY_AND_SIGNIFICANCE_UNVERIFIED')
                    gaps.append('PERFORMANCE_REGRESSION_THRESHOLDS_NOT_APPROVED')
    else:
        signals.append('NO_DEPENDENCY_DESCRIPTOR_CHANGE_IN_SELECTED_DIFF')
    if changes['status'] == 'TOKEN_VAZIO':
        gaps.extend(changes['anomaly_tokens'])
    # A changed file, even when perfectly mapped, never certifies a safe update.
    base_commit_date = _git(root, 'show', '-s', '--format=%cI', base).stdout.decode('utf-8', 'strict').strip()
    head_commit_date = _git(root, 'show', '-s', '--format=%cI', head).stdout.decode('utf-8', 'strict').strip()
    result = {
        'version': 'raf-dependency-continuity/1',
        'status': 'TOKEN_VAZIO' if gaps else 'OBSERVATION_ONLY',
        'priority': 'REVIEW_REQUIRED_UNCLASSIFIED' if touched else 'NOT_CLASSIFIED',
        'visual_alert': ('!!! DEPENDENCY / BUILD-METADATA MODIFICATION DETECTED !!!'
                         if touched else 'NO DECLARED DEPENDENCY FILE DELTA OBSERVED'),
        'base_commit': base, 'candidate_commit': head,
        'base_git_committer_date_asserted': base_commit_date,
        'candidate_git_committer_date_asserted': head_commit_date,
        'pinned_source_checkout_verified': True,
        'baseline_preserved': True, 'changed_dependency_paths': touched,
        'evidence': 'EXACT_GIT_COMMIT_FILES_AND_ASSERTED_SNAPSHOTS',
        'transitive_graph': graph_detail,
        'runtime_metrics': perf_detail,
        'signals': signals, 'typed_gaps': [typed_void('dependency_continuity', t,
            'same_workload_pinned_graph_and_ci_receipt', 'review_before_promotion') for t in sorted(set(gaps))],
        'git_impact_advisory': changes,
        'independent_producer_authenticity_verified': False,
        'performance_claim_allowed': False,
        'runtime_skipping_authorized': False,
        'promote_dependency_update_authorized': False,
        'claim_allowed': False,
    }
    result['audit_id'] = digest(result)
    return result

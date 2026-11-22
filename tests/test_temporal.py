"""Falsifiers: corruption, false-positive guards, order inversion, coverage loss."""
import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from rafvalchecks.core.contract import Violation
from rafvalchecks.core.temporal import analyze_file, analyze_temporal


def event(id, channel, t, **extra):
    x={"id": id, "channel":channel, "occurred_ms":t, "observed_ms":t+40,
       "source_ref":"sha:synthetic", "receipt_ref":"synthetic:receipt", "quality":"good"}
    x.update(extra)
    return x


def fixture(n=4):
    events=[]
    for i in range(n):
        events += [event('a'+str(i),'A',i*10000),event('b'+str(i),'B',i*10000+100)]
    return {"version":1,"events":events,"window_ms":500,"min_support":3}


class TemporalTests(unittest.TestCase):
    def test_lagged_candidate_not_causation(self):
        out=analyze_temporal(fixture())
        self.assertEqual(out['status'],'OBSERVATION_ONLY')
        self.assertEqual(out['coverage']['eligible'],8)
        self.assertEqual([(x['from_channel'],x['to_channel']) for x in out['hypotheses']],[('A','B')])
        self.assertEqual(out['hypotheses'][0]['distinct_pairs'],4)
        self.assertFalse(out['hypotheses'][0]['causality_verified'])
        self.assertFalse(out['hypotheses'][0]['negative_controls_passed'])
        self.assertFalse(out['claim_allowed'])
        self.assertEqual(out['analysis_id'],analyze_temporal(fixture())['analysis_id'])

    def test_reverse_events_not_forward_signal(self):
        obj=fixture()
        for e in obj['events']:
            if e['channel']=='A':e['occurred_ms']+=300
        out=analyze_temporal(obj)
        self.assertNotIn(('A','B'),[(x['from_channel'],x['to_channel']) for x in out['hypotheses']])

    def test_bad_data_quarantined_but_counted(self):
        obj=fixture()
        obj['events'][1]['quality']='suspect'
        obj['events'][3].pop('receipt_ref')
        obj['events'][5]['observed_ms']=-1
        with self.assertRaisesRegex(Violation,'EVENT_TIME_INVALID'):
            analyze_temporal(obj)
        obj['events'][5]['observed_ms']=1
        out=analyze_temporal(obj)
        self.assertEqual(out['coverage']['quarantined'],3)
        self.assertIn('SUSPECT_OR_MISSING_OBSERVATION',out['anomaly_counts'])
        self.assertIn('RECEIPT_REFERENCE_MISSING',out['anomaly_counts'])
        self.assertIn('OBSERVED_BEFORE_OCCURRED_CLOCK_OR_DATA',out['anomaly_counts'])
        self.assertEqual(out['hypotheses'],[])

    def test_duplicate_cannot_inflate_statistical_support(self):
        obj=fixture()
        obj['events'][2]['id']=obj['events'][0]['id']
        out=analyze_temporal(obj)
        self.assertEqual(out['coverage']['duplicate_identity_count'],1)
        self.assertEqual(out['anomaly_counts']['DUPLICATE_EVENT_ID'],2)

    def test_one_effect_cannot_multiply_trigger_support(self):
        d={"version":1,"events":[event('a'+str(i),'A',i*10) for i in range(5)] + [event('b','B',60)],"window_ms":100,"min_support":3}
        self.assertEqual(analyze_temporal(d)['hypotheses'],[])

    def test_missing_not_zero_and_value_zero_allowed(self):
        obj=fixture()
        obj['events'][0]['quality']='missing'
        obj['events'][0]['value']=0
        with self.assertRaisesRegex(Violation,'MISSING_NOT_ZERO'):
            analyze_temporal(obj)
        obj['events'][0]['value']=None
        obj['events'][2]['value']=0
        self.assertEqual(analyze_temporal(obj)['coverage']['eligible'],7)

    def test_unknown_predecessor_not_converted_to_pass(self):
        obj=fixture()
        obj['events'][0]['parent']='missing_event'
        out=analyze_temporal(obj)
        self.assertIn('UNRESOLVED_PREDECESSOR',out['anomaly_counts'])

    def test_empty_input_typed_void(self):
        obj=fixture();obj['events']=[]
        out=analyze_temporal(obj)
        self.assertEqual(out['status'],'TOKEN_VAZIO')
        self.assertEqual(out['typed_voids'][0]['kind'],'TOKEN_VAZIO')

    def test_channel_capacity_fails_closed(self):
        d=fixture();d['events']=[event('x'+str(i),'c'+str(i),i*100) for i in range(17)]
        with self.assertRaisesRegex(Violation,'EVENT_CHANNEL_CAPACITY_EXCEEDED'):
            analyze_temporal(d)

    def test_hash_pinning_file_and_wrong_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'observations.json';path.write_text(json.dumps(fixture()))
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            a=analyze_file(tmp,'observations.json',sha)
            self.assertTrue(a['input_digest_checked'])
            self.assertFalse(a['external_source_trust_verified'])
            with self.assertRaisesRegex(Violation,'EVENT_DIGEST_MISMATCH'):
                analyze_file(tmp,'observations.json','0'*64)

    def test_symlink_and_parent_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'a').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(Violation,'EVENT_FILE_UNAVAILABLE'):
                analyze_file(tmp,'a')
            with self.assertRaisesRegex(Violation,'EVENT_PATH_INVALID'):
                analyze_file(tmp,'../etc/passwd')

    def test_temporal_cascade_is_candidate_only(self):
        d=fixture()
        for i in range(4):d['events'].append(event('c'+str(i),'C',i*10000+200))
        out=analyze_temporal(d)
        self.assertIn(['A','B','C'],out['cascade_candidates'])
        self.assertFalse(out['causal_claim_allowed'])

    def test_no_receipt_no_candidate_even_when_timing_matches(self):
        d=fixture()
        for e in d['events']:e.pop('receipt_ref')
        out=analyze_temporal(d)
        self.assertEqual(out['hypotheses'],[])
        self.assertEqual(out['coverage']['quarantined'],8)

    def test_boolean_not_accepted_as_time(self):
        d=fixture();d['events'][0]['occurred_ms']=True
        with self.assertRaisesRegex(Violation,'EVENT_TIME_INVALID'):
            analyze_temporal(d)

class ModuleIntegrationTests(unittest.TestCase):
    def test_graph_temporal_specialist_fills_void_with_scoped_audit(self):
        from rafvalchecks.core.graph import build
        from rafvalchecks.core.engine import execute
        import os
        from unittest.mock import patch
        root=pathlib.Path(__file__).resolve().parents[1]
        topo=json.loads((root/'examples/topology.temporal.json').read_text())
        graph=build(topo)
        self.assertIn('temporal',graph['nodes'])
        self.assertIn('temporal.__void',graph['nodes'])
        with tempfile.TemporaryDirectory() as tmp:
            workspace=pathlib.Path(tmp)
            (workspace/'examples').mkdir()
            (workspace/'examples/temporal-observations.v1.json').write_bytes(
                (root/'examples/temporal-observations.v1.json').read_bytes())
            manifest={"project":{"name":"temporal", "repository":"rafaelmeloreisnovo/RAF_ValChecks",
                       "source_commit":"7e420be73925c133d77f2e894ea1ae62b8a70d63"},
                      "dependencies":[],"checks":["temporal"],"policy":{"updates":"observe_only",
                       "claim_allowed":False,"reuse_receipts":False,"recompute":"impact_cone_only", "impact_scope":["evidence"]}}
            p=workspace/'manifest.json';p.write_text(json.dumps(manifest))
            with patch.dict(os.environ,{"RAF_EXPECTED_COMMIT":manifest['project']['source_commit'],
                                     "GITHUB_REPOSITORY":manifest['project']['repository']},clear=False):
                old=os.environ.pop('GITHUB_ACTIONS',None)
                try:
                    receipt=execute(topo,p,workspace=workspace)
                    self.assertEqual(receipt['result'],'PASS_SCOPED')
                    module=next(x for x in receipt['nodes'] if x['id']=='temporal')
                    self.assertEqual(module['result'],'PASS_SCOPED')
                    self.assertEqual(len(module['details']['hypotheses']),3)
                    self.assertFalse(module['details']['external_source_trust_verified'])
                    self.assertFalse(module['details']['causal_claim_allowed'])
                finally:
                    if old is not None:os.environ['GITHUB_ACTIONS']=old

    def test_changed_observations_are_never_reused_from_receipt(self):
        from rafvalchecks.core.engine import execute
        from rafvalchecks.core.contract import canonical
        import os
        from unittest.mock import patch
        root=pathlib.Path(__file__).resolve().parents[1]
        topo=json.loads((root/'examples/topology.temporal.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            ws=pathlib.Path(tmp); (ws/'examples').mkdir()
            observations=ws/'examples/temporal-observations.v1.json'
            observations.write_bytes((root/'examples/temporal-observations.v1.json').read_bytes())
            manifest={"project":{"name":"temporal", "repository":"rafaelmeloreisnovo/RAF_ValChecks",
                       "source_commit":"7e420be73925c133d77f2e894ea1ae62b8a70d63"},
                      "dependencies":[],"checks":["temporal"],"policy":{"updates":"observe_only",
                       "claim_allowed":False,"reuse_receipts":False,"recompute":"impact_cone_only",
                       "impact_scope":["evidence"]}}
            mp=ws/'manifest.json';mp.write_text(json.dumps(manifest))
            with patch.dict(os.environ,{"RAF_EXPECTED_COMMIT":manifest['project']['source_commit'],
                                     "GITHUB_REPOSITORY":manifest['project']['repository']},clear=False):
                old=os.environ.pop('GITHUB_ACTIONS',None)
                try:
                    initial=execute(topo,mp,workspace=ws)
                    prior=ws/'prior.json';prior.write_bytes(canonical(initial)+b'\n')
                    hash_before=hashlib.sha256(prior.read_bytes()).hexdigest()
                    changed=json.loads(observations.read_text());changed['events'][0]['quality']='suspect'
                    observations.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(Violation,'EVENT_DIGEST_MISMATCH'):
                        execute(topo,mp,workspace=ws,prior=prior,prior_hash=hash_before,changed_scopes=[])
                finally:
                    if old is not None:os.environ['GITHUB_ACTIONS']=old

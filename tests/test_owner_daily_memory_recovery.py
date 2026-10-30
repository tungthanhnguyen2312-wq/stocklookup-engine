from pathlib import Path
import json

import pytest

from stocklookup_core.decision import integrated_investment_decision_product as iid
from stocklookup_core.portfolio import portfolio_aware_decision as portfolio
from tools import check_owner_daily_host_preflight as preflight


def test_delivery_self_verification_metadata_parses_all_rows_without_universe_buffers(tmp_path, monkeypatch):
    from daily_producer_pipeline import _delivery_metadata
    path = tmp_path/'delivery.json'
    metadata = {'session': '2026-10-26', 'operation_identity': 'op',
                'product_identity': 'product', 'lineage': {'native': True}}
    with path.open('w', encoding='utf-8') as handle:
        handle.write(json.dumps(metadata)[:-1]+',"ticker_research_contexts":{')
        for n in range(24):
            if n:
                handle.write(',')
            handle.write(json.dumps(str(n))+':'+json.dumps({'text': 'Việt Nam '*131072}, ensure_ascii=False))
        handle.write('},"owner_focus_research_contexts":[{"checked":true}],"unused":null}')
    monkeypatch.setattr(Path, 'read_text', lambda *a, **k: pytest.fail('whole delivery Unicode'))
    monkeypatch.setattr(Path, 'read_bytes', lambda *a, **k: pytest.fail('whole delivery bytes'))
    assert _delivery_metadata(path) == metadata
    with path.open('a', encoding='utf-8') as handle:
        handle.write(' {}')
    with pytest.raises(ValueError, match='TRAILING_JSON'):
        _delivery_metadata(path)


@pytest.mark.parametrize('text', [
    '{"ticker_research_contexts":{"A":{},"B":{"bad":]}}}',
    '{"owner_focus_research_contexts":[{}, {"bad":]}]}',
    '{"ticker_research_contexts":{"A":{},"A":{}}}',
])
def test_delivery_metadata_does_not_skip_invalid_discarded_rows(tmp_path, text):
    from daily_producer_pipeline import _delivery_metadata
    path = tmp_path/'delivery.json'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError):
        _delivery_metadata(path)


@pytest.mark.parametrize('failure', [None, 'validation', 'fsync', 'promotion'])
def test_bounded_atomic_copy_preserves_existing_validation_promotion_contract(tmp_path, monkeypatch, failure):
    from stocklookup_core.acquisition import artifact_io as writes
    source, target = tmp_path/'source', tmp_path/'target'
    payload = b'new contents\n'*200000
    source.write_bytes(payload)
    target.write_bytes(b'previous')
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda *a, **k: pytest.fail('whole-file atomic-copy buffer'))
    events = []
    monkeypatch.setattr(writes, '_emit_event', lambda stage, outcome, *a, **k: events.append((stage, outcome)))
    def validator(path):
        with path.open('rb') as handle:
            assert handle.read(13) == payload[:13]
        if failure == 'validation':
            raise ValueError('validation refused')
    def refuse(*args):
        raise OSError('injected failure')
    if failure == 'fsync':
        monkeypatch.setattr(writes.os, 'fsync', refuse)
    if failure == 'promotion':
        monkeypatch.setattr(writes.os, 'replace', refuse)
    if failure:
        with pytest.raises(ValueError if failure == 'validation' else writes.AtomicWriteError):
            writes.atomic_copy_file_bounded(source, target, validator=validator)
        assert read(target) == b'previous'
        assert ('atomic_promotion', 'success') not in events
    else:
        writes.atomic_copy_file_bounded(source, target, validator=validator)
        assert read(target) == payload
        assert events == [('pre_promotion_validation', 'success'), ('atomic_promotion', 'success')]
    assert read(source) == payload
    assert not list(tmp_path.glob('.tmp-*'))


def test_materialization_and_owner_retention_never_buffer_the_complete_companion(tmp_path, monkeypatch):
    import ai_research_session_delivery as delivery
    import daily_research_session_operations as operations
    import daily_producer_pipeline as producer
    from tests.test_ai_research_session_delivery import _operation
    operation = _operation()
    inputs = {'descriptive': {'records': {'ZZZ': {}, 'AAA': {}, 'BBB': {}}}}
    expected = delivery.build_delivery(operation, inputs)
    operation.update(inputs=inputs, snapshot={}, corporate_snapshot={}, strategy_snapshot={})
    monkeypatch.setattr(operations, 'markdown', lambda product: '# Synthetic operation\n')
    monkeypatch.setattr(delivery.io, 'BytesIO', lambda *a, **k: pytest.fail('companion universe buffer'))
    original_read = Path.read_bytes
    def read(self, *args, **kwargs):
        if self.suffix == '.ndjson':
            pytest.fail('whole-companion byte buffer')
        return original_read(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', read)
    target = tmp_path/'operation'
    operations.materialize(target, operation)
    producer._retain_owner_delivery(target, tmp_path/'owner')
    for filename, key in (('ai_research_session_bundle.json', 'primary'),
                          ('ai_research_full_universe.ndjson', 'full_universe'),
                          ('ai_research_bundle_manifest.json', 'manifest'),
                          ('ai_research_session_brief.md', 'brief'),
                          ('current_decision_cockpit_projection.json', 'projection')):
        assert original_read(target/filename) == expected[key]
    assert original_read(tmp_path/'owner/ai_research_full_universe.ndjson') == expected['full_universe']
    assert not list(tmp_path.glob('.delivery-companion-*'))


def test_failed_delivery_projection_does_not_publish_the_spooled_companion(tmp_path, monkeypatch):
    import ai_research_session_delivery as delivery
    import daily_research_session_operations as operations
    from tests.test_ai_research_session_delivery import _operation
    operation = _operation()
    operation.update(inputs={'descriptive': {'records': {'AAA': {}}}}, snapshot={},
                     corporate_snapshot={}, strategy_snapshot={})
    monkeypatch.setattr(operations, 'markdown', lambda product: '# Synthetic operation\n')
    def refuse(*args, **kwargs):
        raise ValueError('projection refused')
    monkeypatch.setattr(delivery, 'build_dashboard_projection', refuse)
    target = tmp_path/'operation'
    target.mkdir()
    (target/'ai_research_session_bundle.json').write_bytes(b'previous')
    with pytest.raises(ValueError, match='projection refused'):
        operations.materialize(target, operation)
    assert (target/'ai_research_session_bundle.json').read_bytes() == b'previous'
    assert not (target/'ai_research_full_universe.ndjson').exists()
    assert not (target/'run_manifest.json').exists()
    assert not list(tmp_path.glob('.delivery-companion-*'))


def test_file_delivery_publication_is_bounded_independent_and_write_once(tmp_path, monkeypatch):
    import hashlib
    from stocklookup_core.acquisition.immutable_delivery import publish_file, protected
    from atomic_io import AtomicWriteError
    source, target = tmp_path/'prepared', tmp_path/'ai_research_full_universe.ndjson'
    payload = b'row\n'*(1024**2)+b'end\n'
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(Path, 'read_bytes', lambda *a, **k: pytest.fail('whole-file publication buffer'))
    assert publish_file(target, source, expected_sha=digest, expected_size=len(payload), protect=True) == 'PUBLISHED_IMMUTABLE'
    assert publish_file(target, source, expected_sha=digest, expected_size=len(payload), protect=True) == 'REUSED'
    assert not source.samefile(target)
    assert protected(target) and not protected(source)
    with target.open('rb') as result:
        assert result.read() == payload
    with pytest.raises(AtomicWriteError, match='DELIVERY_SOURCE_PROOF_MISMATCH'):
        publish_file(target, source, expected_sha='0'*64, expected_size=len(payload))
    assert not list(tmp_path.glob('.delivery-staging-*'))


@pytest.mark.parametrize('race', ['equal', 'different', 'source_changed'])
def test_file_delivery_publication_refuses_races_and_changed_sources(tmp_path, race):
    import hashlib
    from stocklookup_core.acquisition.immutable_delivery import publish_file
    from atomic_io import AtomicWriteError
    source, target = tmp_path/'prepared', tmp_path/'ai_research_full_universe.ndjson'
    source.write_bytes(b'original')
    def intervene(stage):
        if race == 'source_changed':
            source.write_bytes(b'changed')
        else:
            target.write_bytes(b'original' if race == 'equal' else b'other')
    arguments = dict(expected_sha=hashlib.sha256(b'original').hexdigest(), expected_size=8,
                     protect=True, on_stage=intervene)
    if race == 'equal':
        assert publish_file(target, source, **arguments) == 'REUSED'
        assert target.read_bytes() == b'original'
    else:
        with pytest.raises(AtomicWriteError, match='CONTENT_CONFLICT|SOURCE_PROOF_MISMATCH'):
            publish_file(target, source, **arguments)
        if race == 'different':
            assert target.read_bytes() == b'other'
        else:
            assert not target.exists()
    assert not list(tmp_path.glob('.delivery-staging-*'))


def test_file_delivery_bounds_pending_writeback_without_changing_bytes(tmp_path, monkeypatch):
    import hashlib
    import os
    from stocklookup_core.acquisition import immutable_delivery as publication
    source, target = tmp_path/'prepared', tmp_path/'delivery'
    payload = b'a'*9305
    source.write_bytes(payload)
    monkeypatch.setattr(publication, 'CHUNK', 1024)
    monkeypatch.setattr(publication, '_COPY_FLUSH_BYTES', 2048)
    sync = os.fsync
    positions = []
    def observed(fd):
        positions.append(os.lseek(fd, 0, os.SEEK_CUR))
        return sync(fd)
    monkeypatch.setattr(os, 'fsync', observed)
    publication.publish_file(target, source, expected_sha=hashlib.sha256(payload).hexdigest(), expected_size=len(payload))
    assert target.read_bytes() == payload
    assert positions[-1] == len(payload)
    assert all(right-left <= 2048 for left, right in zip([0]+positions, positions))


@pytest.mark.parametrize('value', [
    {'z': 'Việt Nam', 'records': {'ZZZ': {'nested': [None, False, -0.0, 1e-9]}, 'AAA': {}}, 'a': 1},
    {'records': [], 'metadata': {'preserved': True}},
])
def test_record_loader_preserves_unsorted_json_graph_and_types(tmp_path, value):
    from stocklookup_core.evidence.record_artifact_loading import load_record_artifact
    path = tmp_path/'input.json'
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    assert load_record_artifact(path) == value


@pytest.mark.parametrize('text', ['{"records":{"AAA":{},"AAA":{}}}', '{"records":{}} {}'])
def test_record_loader_refuses_ambiguous_or_trailing_input(tmp_path, text):
    from stocklookup_core.evidence.record_artifact_loading import load_record_artifact
    path = tmp_path/'input.json'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError):
        load_record_artifact(path)


def _retained(tmp_path, *, large=False, sorted_keys=True):
    records = {f'T{i:03d}': {'ticker': f'T{i:03d}', 'opaque_evidence': 'x' * (1024**2 if large else 8)}
               for i in range(18 if large else 2)}
    artifact = {'session': '2026-10-23', 'contract_version': iid.CONTRACT_VERSION, 'records': records}
    artifact.update(iid.content_identity(artifact))
    path = tmp_path / 'iid.json'
    path.write_text(json.dumps(artifact, sort_keys=sorted_keys), encoding='utf-8')
    return artifact, path


@pytest.mark.parametrize('large', [False, True])
@pytest.mark.parametrize('method', ['bound', 'default'])
def test_resolver_keeps_exact_graph_without_large_text_load(tmp_path, monkeypatch, large, method):
    artifact, path = _retained(tmp_path, large=large, sorted_keys=False)
    if method == 'default':
        target = tmp_path/'operations-review/canonical-post-close-v1/2026-10-23/enrichment/integrated_investment_decision_product.json'
        target.parent.mkdir(parents=True)
        path.rename(target)
        path = target
    monkeypatch.setattr(portfolio, 'operation_bound_integrated_decision_candidates', lambda *a: [path])
    original_read = Path.read_text
    if large:
        monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k:
            pytest.fail('whole IID text loaded') if self == path else original_read(self, *a, **k))
    if method == 'default':
        actual = portfolio.load_integrated_decision_artifact(tmp_path, '2026-10-23')
        resolved = path
    else:
        actual, resolved = portfolio.resolve_operation_bound_integrated_decision(
            tmp_path, '2026-10-23', artifact['artifact_identity'])
    assert actual == artifact and resolved == path
    assert iid.content_identity(actual)['artifact_identity'] == artifact['artifact_identity']


def test_memory_failure_hint_uses_retained_dimensions_without_reobservation(monkeypatch):
    monkeypatch.setattr(preflight, 'observe', lambda *a: pytest.fail('unexpected new observation'))
    result = {'dimensions': {'physical': {'classification': 'AMBER', 'observed_bytes': 9766522880,
        'green_min_bytes': 10311071568, 'reason': 'PHYSICAL_HEADROOM_LOW'},
        'commit': {'classification': 'READY', 'observed_bytes': 24480735232}}}
    text = ' '.join(preflight.failure_guidance(result))
    assert 'physical: AMBER' in text and '9.096 GiB' in text and '9.603 GiB' in text
    assert 'PHYSICAL_HEADROOM_LOW' in text and 'commit:' not in text


def test_producer_releases_planning_graph_before_operation_resolution(tmp_path, monkeypatch):
    import weakref
    import daily_producer_pipeline as producer
    class InputGraph(dict):
        pass
    class StopBeforeWrites(Exception):
        pass
    references = []
    def resolve(*args):
        graph = InputGraph()
        references.append(weakref.ref(graph))
        return graph, {}
    def operation(*args, **kwargs):
        assert references[0]() is None, 'independent planning graph overlaps operation parsing'
        raise StopBeforeWrites
    monkeypatch.setattr(producer, 'load_registry', lambda *a: {})
    monkeypatch.setattr(producer, 'completed_session_gate', lambda *a, **k: {})
    monkeypatch.setattr(producer, 'resolve_inputs', resolve)
    monkeypatch.setattr(producer, 'validate_coherence', lambda *a: {})
    monkeypatch.setattr(producer, 'build_acquisition_plan', lambda *a, **k: {'items': []})
    monkeypatch.setattr(producer, '_dependency_graph', lambda *a: {})
    monkeypatch.setattr(producer, 'resolve_or_build_daily_session_shadow_recommendation', lambda *a, **k: {
        'chain': {'fundamental_cohort_selection': {}, 'shadow_security_recommendation': {
            'metadata': {'as_of_session': '2026-10-23'}, 'artifact_identity': 'shadow:fixture'}}})
    monkeypatch.setattr(producer, 'run_session_operation', operation)
    with pytest.raises(StopBeforeWrites):
        producer.run_daily_producer(tmp_path, session='2026-10-23', latest_completed_session=False,
                                    producer_head='fixture', consumer_head='fixture')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('tamper', [False, True])
def test_delivery_verifier_hashes_companion_without_whole_file_buffer(tmp_path, monkeypatch, tamper):
    import hashlib
    import daily_producer_pipeline as producer
    operation = {'manifest': {'market_session': '2026-10-23', 'operation_identity': 'operation:fixture'},
                 'product': {'artifact_identity': 'product:fixture'}}
    bundle = {'session': '2026-10-23', 'operation_identity': 'operation:fixture',
              'product_identity': 'product:fixture', 'lineage': {'input_artifacts': {}}}
    projection = {'session': '2026-10-23', 'source': {'operation_identity': 'operation:fixture',
                   'product_identity': 'product:fixture', 'input_artifacts': {}}}
    companion = tmp_path/'ai_research_full_universe.ndjson'
    raw = b'{"ticker":"AAA"}\n'
    companion.write_bytes(raw + (b'tampered' if tamper else b''))
    manifest = {'files': {companion.name: {'sha256': hashlib.sha256(raw).hexdigest()}}}
    for name, value in (('ai_research_session_bundle.json', bundle),
                        ('current_decision_cockpit_projection.json', projection),
                        ('ai_research_bundle_manifest.json', manifest)):
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    original = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda self: pytest.fail('unbounded companion read')
                        if self == companion else original(self))
    if tamper:
        with pytest.raises(producer.DailyProducerError, match='AI_DELIVERY_SELF_VERIFICATION_FAILED'):
            producer._verify_delivery(operation,tmp_path)
    else:
        assert producer._verify_delivery(operation,tmp_path)['status'] == 'PASS'


@pytest.mark.parametrize('records', [{}, {'ZZZ': {'nested': (None, False, float('nan'), -0.0),
    'text': 'Việt Nam', 'opaque': Path('evidence.json')}, 'AAA': {'number': 1e-9}}, {1: {}}])
def test_scenario_binding_chunk_hash_equals_original_field_identity(records):
    from current_evidence_bound_scenario import binding_content_identity
    from stocklookup_core.evidence.field_identity import stable_id
    payload = {'records': records, 'session': '2026-10-23', 'metadata': {'z': 3}}
    expected = stable_id(payload)
    assert binding_content_identity(dict(payload, artifact_identity='ignored', artifact_sha256='ignored'))['artifact_sha256'] == expected


def test_scenario_binding_chunk_hash_preserves_nonfinite_refusal():
    from current_evidence_bound_scenario import binding_content_identity
    with pytest.raises(ValueError):
        binding_content_identity({'records': {'AAA': {'value': float('inf')}}})


@pytest.mark.parametrize('cards', [{}, {'ZZZ': {'nested': (None, False, -0.0),
    'text': 'Việt Nam'}, 'AAA': {'number': 1e-9}}, {1: {}}])
def test_workspace_card_hash_equals_original_strict_canonical_identity(cards):
    import hashlib
    from stocklookup_core.decision.investment_decision_workspace_projection import content_identity
    payload = {'cards': cards, 'session': '2026-10-23', 'metadata': {'z': 3}}
    expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    assert content_identity(dict(payload, artifact_identity='ignored', requested_at='ignored'))['artifact_sha256'] == expected


def test_workspace_card_hash_preserves_strict_nonfinite_refusal():
    from stocklookup_core.decision.investment_decision_workspace_projection import content_identity
    with pytest.raises(ValueError):
        content_identity({'cards': {'AAA': {'value': float('nan')}}})


@pytest.mark.parametrize('nested', [False, True])
def test_large_supplementary_records_lists_and_financial_wrapper_are_bounded(tmp_path, monkeypatch, nested):
    from canonical_current_product_projections import _load_json
    body = {'records': [{'text': 'x' * 1024**2, 'order': i} for i in range(18)], 'z': False}
    value = {'financial_analysis_product': body, 'a': 'Việt Nam'} if nested else body
    path = tmp_path/'supplementary.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr(Path, 'read_text', lambda *a, **k: pytest.fail('whole supplementary Unicode buffer'))
    assert _load_json(path) == value


@pytest.mark.parametrize('records', [{}, {'ZZZ': {'text': 'Việt Nam', 'nested': [None, False, -0.0]},
    'AAA': {'value': 1e-9}}, [{'text': 'Việt Nam'}], {1: {}}])
def test_opportunity_record_hash_matches_original_strict_identity(records):
    import hashlib
    from stocklookup_core.valuation.current_valuation_opportunity_integration import content_identity
    payload = {'contract_version': 'opportunity_context/v1', 'records': records, 'metadata': {'z': 1}}
    expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    assert content_identity(dict(payload, requested_at='ignored'))['artifact_sha256'] == expected


@pytest.mark.parametrize('cards', [{}, {'ZZZ': {'text': 'Việt Nam', 'nested': [None, False, -0.0]},
    'AAA': {'value': 1e-9}}])
def test_workspace_stream_writer_preserves_exact_native_bytes(tmp_path, cards):
    from canonical_current_product_projections import _write_workspace_json
    payload = {'z': 1, 'cards': cards, 'a': 'end'}
    path = tmp_path/'workspace.json'
    _write_workspace_json(path, payload)
    assert path.read_bytes() == (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def test_workspace_stream_writer_validation_failure_preserves_previous_output(tmp_path, monkeypatch):
    from canonical_current_product_projections import _write_workspace_json
    from stocklookup_core.evidence import record_artifact_loading as loader
    path = tmp_path/'workspace.json'
    path.write_bytes(b'previous')
    def refuse(path):
        raise ValueError('validation refused')
    monkeypatch.setattr(loader, 'load_record_artifact', refuse)
    with pytest.raises(ValueError, match='validation refused'):
        _write_workspace_json(path, {'cards': {'AAA': {'value': 1}}})
    assert path.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.workspace-json-*'))


def test_evaluated_copy_streams_native_bytes_and_validates_every_discarded_record(tmp_path, monkeypatch):
    from canonical_current_product_projections import _write_workspace_json
    from stocklookup_core.evidence import record_artifact_loading as loader
    payload = {'records': {'Z': {'text': 'Việt Nam'}, 'A': {'number': -0.0}},
               'valuation_balance_sheet_divergence_context': {'records': {'A': {'value': None}}},
               'metadata': {'flag': False}}
    native = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    path = tmp_path/'evaluated.json'
    original_load = loader.load_record_artifact
    seen = []
    def validate(candidate, *, record_tickers=None):
        assert candidate.read_bytes() == native
        seen.append(original_load(candidate, record_tickers=record_tickers))
        return seen[-1]
    monkeypatch.setattr(loader, 'load_record_artifact', validate)
    _write_workspace_json(path, payload, validation_record_tickers=())
    assert path.read_bytes() == native
    assert seen == [{'records': {}, 'valuation_balance_sheet_divergence_context': {'records': {}},
                     'metadata': {'flag': False}}]
    # Projection still parses unretained rows; malformed data cannot pass validation.
    path.write_bytes(b'{"records":{"A":{"broken": }}}')
    with pytest.raises(ValueError):
        original_load(path, record_tickers=())

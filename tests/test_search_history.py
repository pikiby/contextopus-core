import json
from types import SimpleNamespace

import pytest

from contextopus.core.analytics import OperationJournal
from contextopus.core.filtering import select
from contextopus.core.search_history import SearchHistory
from contextopus.core.storage import StorageLayout


def event(tmp_path, count=3):
    layout = StorageLayout(tmp_path)
    instructions = layout.workspace('chosen') / 'INSTRUCTIONS.md'
    instructions.parent.mkdir(parents=True, exist_ok=True)
    instructions.write_text('Original exact rules')
    journal = OperationJournal(layout)
    identifier = journal.begin(SimpleNamespace(workspace='chosen'), 'core.search', {
        'query': 'private source query', 'purpose': 'Find required conditions', 'task_id': 'task-one'})
    rows = [{'key': ['workspace', 'chosen', str(i)], 'revision': 'revision-' + str(i),
             'distance': i / count, 'excerpt': 'private source body'} for i in range(count)]
    result = select(rows, {'algorithm': 'nearest_n', 'parameters': {'N': 1}})
    journal.finish(identifier, result=result, duration=0.5)
    return journal, identifier


def test_saved_pool_beyond_generic_summary_and_no_sources(tmp_path):
    journal, identifier = event(tmp_path, 150)
    evidence = SearchHistory(journal).read(identifier)
    assert len(evidence['diagnostics']['candidates']) == 150
    assert evidence['purpose'] == 'Find required conditions'
    assert evidence['instructions_revision']
    raw = journal.path.read_bytes()
    assert b'private source body' not in raw and b'private source query' not in raw
    with journal.connect() as db:
        result = json.loads(db.execute('SELECT result FROM operations WHERE id=?', [identifier]).fetchone()[0])
    assert 'candidates' not in result['diagnostics']
    assert result['search_event_id'] == identifier


def test_scope_frozen_pagination_and_rule_revision(tmp_path):
    journal, identifier = event(tmp_path)
    history = SearchHistory(journal)
    snapshot = history.query(context='chosen', task_id='task-one')
    assert [r['event_id'] for r in snapshot['events']] == [identifier]
    assert history.query(context='other')['events'] == []
    assert history.query(task_id='other')['events'] == []
    revision = snapshot['events'][0]['instructions_revision']
    (journal.layout.workspace('chosen') / 'INSTRUCTIONS.md').write_text('Changed rules')
    assert history.query(instructions_revision=revision)['events']
    assert history.query(instructions_revision='unknown')['events'] == []
    with pytest.raises(ValueError):
        history.query(since='2026-10-15T00:00:00')
    with pytest.raises(ValueError):
        history.query(limit=1000)


def test_replay_quantifies_supplied_labels_without_claiming_quality(tmp_path):
    journal, identifier = event(tmp_path)
    result = SearchHistory(journal).replay(identifier, {
        'algorithm': 'nearest_n', 'parameters': {'N': 2}},
        relevant_keys=[['workspace', 'chosen', '0'], ['workspace', 'chosen', '1']])
    assert result['added'] == [['workspace', 'chosen', '1']]
    assert result['label_comparison']['original']['recall'] == 0.5
    assert result['label_comparison']['alternative']['recall'] == 1
    assert result['quality_assessment'] == 'not_established'
    assert result['scope'] == 'recorded_candidates_only'


def test_absent_legacy_evidence_is_readonly(tmp_path):
    journal = OperationJournal(StorageLayout(tmp_path / 'absent'))
    assert SearchHistory(journal).query()['events'] == []
    assert not journal.path.parent.exists()
    with pytest.raises(ValueError, match='unavailable'):
        SearchHistory(journal).read('unknown')


def test_candidate_truncation_prevents_full_coverage_claim(tmp_path):
    journal, identifier = event(tmp_path, 1001)
    result = SearchHistory(journal).replay(identifier, {'algorithm': 'none'})
    assert result['snapshot_truncated'] is True
    assert result['quality_assessment'] == 'not_established'


def test_fragment_replay_preserves_distinct_parts_of_same_material(tmp_path):
    journal, identifier = event(tmp_path)
    rows = [{'key': ['workspace', 'chosen', 'one'], 'part_index': i,
             'revision': 'same', 'distance': i / 10} for i in range(2)]
    original = select(rows, {'algorithm': 'none', 'parameters': {'page_size': 1}}, output='fragments')
    journal.finish(identifier, result=original, duration=0.1)
    replay = SearchHistory(journal).replay(identifier, {
        'algorithm': 'none', 'parameters': {'page_size': 1, 'offset': 1}})
    assert replay['added'][0]['part_index'] == 1
    assert replay['removed'][0]['part_index'] == 0

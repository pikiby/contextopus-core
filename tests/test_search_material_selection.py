"""Regression fixtures for material units, relevance boundaries and bounded evidence."""
import pytest

from contextopus.core.filtering import annotate_candidate_limit, compact_diagnostics, select


def fragments():
    return [
        {'key': ['demo', 'one', name], 'part_index': part, 'distance': distance}
        for name, part, distance in [('a', 0, .10), ('a', 1, .101), ('a', 2, .102),
                                     ('b', 0, .11), ('c', 0, .12), ('d', 0, .13)]
    ]


ALGORITHMS = [
    ('distance_jump', {'N': 3}), ('distance_threshold', {'N': 3}),
    ('nearest_n', {'N': 3}), ('none', {'page_size': 3}), ('archivist', {'top_k': 3}),
]


@pytest.mark.parametrize('algorithm,parameters', ALGORITHMS)
def test_all_material_algorithms_group_before_the_result_limit(algorithm, parameters):
    answer = select(fragments(), {'algorithm': algorithm, 'parameters': parameters})
    assert [row['key'][-1] for row in answer['results']] == ['a', 'b', 'c']
    assert answer['results'][0]['part_index'] == 0
    diag = answer['diagnostics']
    assert diag['version'] == '2.0.0'
    assert diag['deduplication_order'] == 'before_selection'
    assert diag['counts']['considered_fragments'] == 6
    assert diag['counts']['considered_documents'] == diag['counts']['selection_units'] == 4
    assert diag['counts']['selected_materials'] == 3
    assert diag['limits']['result']['omitted'] == 1
    assert diag['completeness']['result_window_complete'] is False
    assert 'result_cap' in diag['completeness']['reasons']


@pytest.mark.parametrize('algorithm,parameters', ALGORITHMS)
def test_fragment_algorithms_keep_individual_parts(algorithm, parameters):
    answer = select(fragments(), {'algorithm': algorithm, 'parameters': parameters}, output='fragments')
    assert [row['part_index'] for row in answer['results']] == [0, 1, 2]
    assert answer['diagnostics']['counts']['selection_units'] == 6
    assert answer['diagnostics']['boundary']['unit'] == 'fragments'
    assert answer['diagnostics']['deduplication_order'] == 'not_applied'


def test_material_pagination_has_no_repeated_or_lost_document_slots():
    pages = [select(fragments(), {'algorithm': 'none', 'parameters': {'offset': offset, 'page_size': 2}})
             for offset in (0, 2, 4)]
    assert [[r['key'][-1] for r in page['results']] for page in pages] == [['a', 'b'], ['c', 'd'], []]
    assert pages[0]['diagnostics']['boundary']['result_cap']['next_offset'] == 2
    assert pages[1]['diagnostics']['boundary']['result_cap']['next_offset'] is None


def test_jump_is_evaluated_beyond_n_and_between_documents():
    rows = fragments()[:3] + [
        {'key': ['demo', 'one', str(i)], 'distance': distance}
        for i, distance in enumerate([.11, .12, .60, .61, .62])]
    answer = select(rows, {'algorithm': 'distance_jump', 'parameters': {'N': 2}})
    boundary = answer['diagnostics']['boundary']
    assert len(answer['results']) == 2
    assert boundary['reason'] == 'result_cap'
    assert boundary['relevance']['reason'] == 'distance_jump'
    assert boundary['relevance']['retained'] == 3
    assert boundary['result_cap'] == {'limit': 2, 'omitted': 1}


@pytest.mark.parametrize('distances,assessment', [([], 'insufficient_candidates'),
    ([.1], 'insufficient_candidates'), ([.1, .2], 'insufficient_candidates'),
    ([.1, .1, .1], 'no_positive_gaps'), ([.1, .11, .12], 'no_jump')])
def test_jump_assessment_does_not_claim_a_cap_is_no_jump(distances, assessment):
    rows = [{'id': str(i), 'distance': d} for i, d in enumerate(distances)]
    answer = select(rows, {'algorithm': 'distance_jump', 'parameters': {'N': 1}})
    boundary = answer['diagnostics']['boundary']
    assert boundary['relevance']['jump_assessment'] == assessment
    assert (boundary['reason'] == 'result_cap') == (len(rows) > 1)


def test_threshold_is_evaluated_before_separate_result_cap():
    answer = select([{'id': str(i), 'distance': d} for i, d in enumerate([.1, .2, .3, .9])],
                    {'algorithm': 'distance_threshold', 'parameters': {'N': 1, 'd_max': .5}})
    boundary = answer['diagnostics']['boundary']
    assert boundary['relevance'] == {'reason': 'distance_threshold', 'retained': 3, 'threshold_removed': 1}
    assert boundary['result_cap'] == {'limit': 1, 'omitted': 2}


def test_tied_material_representatives_preserve_input_order():
    rows = [{'id': 'a', 'distance': .1, 'part_index': 1},
            {'id': 'a', 'distance': .1, 'part_index': 0}, {'id': 'b', 'distance': .1}]
    answer = select(rows, {'algorithm': 'nearest_n'})
    assert [r['id'] for r in answer['results']] == ['a', 'b']
    assert answer['results'][0]['part_index'] == 1


def test_technical_cap_does_not_claim_omitted_documents_can_be_recovered():
    answer = select(fragments()[:3], {'algorithm': 'nearest_n'}, eligible_documents=4, eligible_fragments=6)
    diag = answer['diagnostics']
    annotate_candidate_limit(diag, 3)
    assert len(answer['results']) == 1
    assert diag['counts']['considered_documents'] == 1
    assert diag['completeness']['selection_input_complete'] is False
    assert diag['completeness']['reasons'] == ['candidate_limit']
    assert diag['completeness']['candidate_snapshot_complete'] is True
    compact = compact_diagnostics(diag)
    assert 'candidates' not in compact and 'nearby_rejected' not in compact
    assert compact['counts'] == diag['counts']


def test_invalid_distances_are_separate_from_candidate_limit():
    answer = select([{'id': 'a', 'distance': .1}, {'id': 'b', 'distance': float('nan')}])
    diag = answer['diagnostics']
    annotate_candidate_limit(diag, 2)
    assert diag['candidate_pool_truncated'] is False
    assert diag['completeness']['retrieval_complete'] is True
    assert diag['completeness']['selection_input_complete'] is False
    assert diag['completeness']['reasons'] == ['invalid_distances']

import json
import math
import pytest
from contextopus.core.filtering import AlgorithmRegistry, select


def rows(distances):
    return [dict(id=str(i), revision='r1',distance=d,excerpt='private body',vector=[1,2]) for i,d in enumerate(distances)]


def test_legacy_parameters_use_current_material_grouping():
    candidates=rows([.10,.11,.12,.60,.61,.62])
    candidates[1]['id']='0'
    result=select(candidates,legacy={'N':20,'d_max':.8,'min_jump':.02,'multiplier':3})
    assert [r['id'] for r in result['results']]==['0','2']
    assert result['diagnostics']['boundary']['reason']=='distance_jump'
    assert 'private body' not in json.dumps(result['diagnostics'])
    assert 'vector' not in json.dumps(result['diagnostics'])


def test_none_page_and_fragments():
    candidates=rows([.3,.1,.2,.4]); candidates[2]['id']='1'
    answer=select(candidates,{'algorithm':'none','parameters':{'offset':1,'page_size':2}},output='fragments')
    assert [r['distance'] for r in answer['results']]==[.2,.3]
    assert answer['diagnostics']['boundary']['reason']=='pagination'


@pytest.mark.parametrize('distances',[[],[.1],[.1,.2],[.1,.11,.12],[.1,.1,.1]])
def test_no_jump_on_small_or_flat_sets(distances):
    assert len(select(rows(distances))['results'])==len(distances)


def test_threshold_and_weak_plateau():
    assert len(select(rows([.1,.2,.7]), {'algorithm':'distance_threshold','parameters':{'d_max':.3}})['results'])==2



@pytest.mark.parametrize('selection',[{'algorithm':'missing'},{'algorithm':'nearest_n','parameters':{'d_max':1}},{'algorithm':'none','parameters':{'page_size':False}},{'parameters':{'N':float('nan')}}])
def test_bad_parameters(selection):
    with pytest.raises(ValueError): select([],selection)


def test_provider_discovery_and_removal(tmp_path):
    path=tmp_path/'custom';path.mkdir()
    description={'id':'custom','version':'3','purpose':'custom test','parameters_schema':{'type':'object','additionalProperties':False},'defaults':{},'when_to_use':'test','how_to_adjust':'none'}
    (path/'description.json').write_text(json.dumps(description))
    (path/'algorithm.py').write_text("def select(rows, parameters):\n    return rows[:1], {'reason':'custom','boundary_index':1}\n")
    registry=AlgorithmRegistry([tmp_path])
    assert select(rows([.1,.2]),{'algorithm':'custom'},registry=registry)['diagnostics']['version']=='3'
    registry.refresh()
    assert registry.catalog('custom')==[]


def test_broken_provider_isolated(tmp_path):
    folder=tmp_path/'bad';folder.mkdir()
    (folder/'description.json').write_text('{}')
    registry=AlgorithmRegistry([tmp_path])
    assert len(registry.errors)==1
    assert len(registry.catalog())==5
    assert select(rows([.1]),registry=registry)['results']


def test_archivist_exact_jump_plateau_and_grouping():
    def run(distances, **parameters):
        return select(rows(distances), {'algorithm':'archivist','parameters':parameters})
    assert len(run([.1,.11,.12,.6,.61,.62])['results'])==3
    plateau = run([.1,.11,.13,.15,.151,.152])
    assert len(plateau['results'])==4
    assert plateau['diagnostics']['boundary']['reason']=='archivist_weak_plateau'
    assert len(run([.6,.6,.6])['results'])==3
    assert len(run([.1,.11,.13,.15,.151,.152],top_k=2)['results'])==2
    duplicate=rows([.1,.1,.11,.12,.6,.61,.62]);duplicate[1]['id']='0'
    result=select(duplicate,{'algorithm':'archivist'})
    assert len(result['results'])==3
    assert result['diagnostics']['deduplication_order']=='before_selection'


def test_enabled_fingerprint_current_registry_cached_and_disabled_unloaded(tmp_path):
    from contextopus.core.filtering import registry_for_layout
    from contextopus.core.storage import StorageLayout
    from contextopus.core.module_management import ModuleManager
    layout=StorageLayout(tmp_path)
    package=tmp_path/'modules/demo/package'
    provider=package/'filter_algorithms/custom';provider.mkdir(parents=True)
    manifest=package.parent/'module.json'
    manifest.write_text(json.dumps({'id':'demo','version':'1.0.0'}))
    description={'id':'custom','version':'1','purpose':'custom','parameters_schema':{'type':'object','additionalProperties':False},'defaults':{},'when_to_use':'test','how_to_adjust':'none'}
    (provider/'description.json').write_text(json.dumps(description))
    (provider/'algorithm.py').write_text("def select(rows,parameters):\n    return rows[:1], {'reason':'custom'}\n")
    manager=ModuleManager.__new__(ModuleManager);manager.base=tmp_path/'modules'
    fingerprint=manager._digest('demo')
    layout.configuration.mkdir(parents=True)
    path=layout.configuration/'modules.json'
    path.write_text(json.dumps({'demo':{'enabled':True,'prepared':fingerprint}}))
    first=registry_for_layout(layout)
    assert first.catalog('custom')
    assert registry_for_layout(layout) is first
    (provider/'algorithm.py').write_text("raise RuntimeError('must not execute unprepared source')\n")
    changed=registry_for_layout(layout)
    assert not changed.catalog('custom')
    assert changed.errors[0]['module']=='demo'
    path.write_text(json.dumps({'demo':{'enabled':False,'prepared':fingerprint}}))
    disabled=registry_for_layout(layout)
    assert not disabled.catalog('custom')
    assert not disabled.errors


def test_count_units_distinguish_fragments_from_documents():
    candidates=rows([.1,.11,.2]);candidates[1]['id']='0'
    result=select(candidates,{'algorithm':'nearest_n'},eligible_documents=2,eligible_fragments=3)
    counts=result['diagnostics']['counts']
    assert counts['eligible_documents']==2
    assert counts['eligible_fragments']==counts['considered_fragments']==3
    assert counts['selected_fragments']==2
    assert counts['considered_documents']==2
    assert counts['selected_materials']==2


def test_semantic_catalog_requires_explicit_refresh_for_missing_or_stale_cards():
    from contextopus.core.filtering import AlgorithmCatalog
    class Index:
        def __init__(self, revisions): self.revisions=revisions
        def vector_revisions(self,module,collection): return self.revisions
        def search_detailed(self,*args,**kwargs): raise AssertionError('must not search stale cards')
    for revisions,state in [({},'missing'),({'disabled_algorithm':'r1'},'stale')]:
        result=AlgorithmCatalog(AlgorithmRegistry(),Index(revisions)).search('threshold',semantic=True)
        assert result['results']==[]
        assert result['catalog_state']==state
        assert result['next_action']=='core.algorithms_refresh'

import json
from pathlib import Path
import pytest
from contextopus.integrations.native import plan, integrate, IntegrationConflict
from contextopus.integrations.skill_delivery import entrypoints, delivery_options

@pytest.mark.parametrize('client',['codex','claude-code','cursor','opencode','crush','hermes'])
def test_client_full_names_and_alias_reuse(tmp_path,monkeypatch,client):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'.config'))
    monkeypatch.delenv('HERMES_HOME',raising=False)
    preview=plan(client,tmp_path,scope='user')
    assert preview['entrypoints']==[{'identity':'modules','installed_name':'contextopus-modules','relationship':'namespaced'}]
    integrate(preview)
    renamed=plan(client,tmp_path,scope='user',skill_aliases={'modules':'m'})
    assert len(renamed['removals'])==1
    integrate(renamed)
    again=plan(client,tmp_path,scope='user')
    assert again['entrypoints'][0]['installed_name']=='m'
    assert not integrate(again)['written']
    reset=plan(client,tmp_path,scope='user',skill_aliases={})
    assert reset['entrypoints'][0]['installed_name']=='contextopus-modules'


def test_alias_protects_user_file_and_stale_preview(tmp_path):
    target=tmp_path/'.agents/skills/m/SKILL.md';target.parent.mkdir(parents=True);target.write_text('mine')
    with pytest.raises(IntegrationConflict,match='collision'):
        plan('codex',tmp_path,skill_aliases={'modules':'m'})
    preview=plan('codex',tmp_path)
    config=tmp_path/'.codex/config.toml';config.parent.mkdir(parents=True);config.write_text('# changed')
    with pytest.raises(IntegrationConflict,match='changed after preview'):integrate(preview)
    assert not (tmp_path/'.agents/skills/contextopus-modules').exists()


def test_config_only_does_not_retire_skills(tmp_path):
    integrate(plan('codex',tmp_path,skill_aliases={'modules':'m'}))
    preview=plan('codex',tmp_path,install_skills=False)
    assert not preview['removals']
    integrate(preview)
    assert (tmp_path/'.agents/skills/m/SKILL.md').exists()


def test_selection_and_alias_collision():
    sources=[('workspace',Path('a')),('agents',Path('b'))]
    options=delivery_options({},['workspace'],{'workspace':'w'})
    assert [x[:2] for x in entrypoints(sources,options)]==[('workspace','w')]
    with pytest.raises(ValueError,match='collision'):
        entrypoints(sources,delivery_options({},None,{'workspace':'x','agents':'x'}))
    with pytest.raises(ValueError,match='Unknown selected'):
        entrypoints(sources,delivery_options({},['missing']))
    with pytest.raises(ValueError,match='Invalid skill'):
        delivery_options({},None,{'workspace':'../escape'})
    assert delivery_options({'delivery':{'selected':['workspace']}},[])['selected'] is None


def test_modified_retired_alias_is_preserved(tmp_path):
    integrate(plan('codex',tmp_path,skill_aliases={'modules':'m'}))
    target=tmp_path/'.agents/skills/m/SKILL.md';target.write_text('user edits')
    result=integrate(plan('codex',tmp_path,skill_aliases={}))
    assert str(target) in [x['path'] for x in result['preserved']]
    assert target.read_text()=='user edits'

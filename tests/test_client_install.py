import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'distribution/client_install.py'

@pytest.fixture
def installer(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('client_install_test',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/'client.json').write_text(json.dumps({'client':'cursor','delivery':'plugin'}))
    monkeypatch.setattr(module,'__file__',str(tmp_path/'install.py'))
    monkeypatch.setattr(module,'bundled_modules',lambda package,selected:[])
    return module,tmp_path


def test_reuse_preview_does_not_launch_anything(installer,monkeypatch):
    m,p=installer;monkeypatch.setattr(m,'runtime',lambda:'/existing/contextopus')
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:pytest.fail('preview executed a command'))
    assert m.main(['--plan'])==0


def test_reuse_plugin_checks_owner_without_copying_skills(installer,monkeypatch):
    m,p=installer;monkeypatch.setattr(m,'runtime',lambda:'/existing/contextopus')
    calls=[]
    def run(command,**kwargs):
        calls.append(command);return SimpleNamespace(stdout=json.dumps([] if 'query' in command else {'state':'running','root':str(p)}))
    monkeypatch.setattr(m.subprocess,'run',run)
    assert m.main(['--yes','--root',str(p)])==0
    assert calls[0]==['/existing/contextopus','--root',str(p),'service','status']
    assert all('execute' not in command and 'integrate' not in command for command in calls)


def test_reuse_rejects_other_owner_and_stopped_core(installer,monkeypatch):
    m,p=installer;monkeypatch.setattr(m,'runtime',lambda:'/existing/contextopus')
    for state in [{'state':'stopped'},{'state':'running','root':str(p/'other')}]:
        monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=json.dumps(state)))
        with pytest.raises(RuntimeError):m.main(['--yes','--root',str(p)])


def test_fresh_plugin_uses_shared_installer_without_client_copy(installer,monkeypatch):
    m,p=installer;monkeypatch.setattr(m,'runtime',lambda:None)
    calls=[];monkeypatch.setattr(m.subprocess,'call',lambda argv:calls.append(argv) or 0)
    assert m.main(['--plan','--module','workspace','--skip-model'])==0
    assert calls[0][2]==str(p/'runtime/install.py')
    assert calls[0][3:]==['--client','none','--module','workspace','--skip-model','--plan']


def test_missing_module_installed_and_procedure_checked(installer,monkeypatch):
    m,p=installer
    source=p/'runtime/modules/example'
    (source/'package/procedures').mkdir(parents=True)
    (source/'package/procedures/work.md').write_text('work')
    (source/'module.json').write_text(json.dumps({'procedures':'procedures','operations':[{'name':'example.read'}]}))
    calls=[]; installed=False
    def query(base,op,args=None,**kw):
        nonlocal installed
        calls.append((op,args,kw))
        if op=='core.modules':return [{'id':'example','state':'enabled','operations':['example.read']}] if installed else []
        if op=='core.module_source_plan':return {'revision':'reviewed'}
        if op=='core.module_install':
            assert args['source_revision']=='reviewed';installed=True;return {'state':'enabled'}
        if op=='procedure':return {'content':'work'}
        pytest.fail(op)
    monkeypatch.setattr(m,'query',query)
    modules=[{'id':'example','path':'modules/example'}]
    m.ensure_modules([],p,modules)
    assert calls[-1][1]=={'name':'example/work'}
    calls.clear();m.ensure_modules([],p,modules)
    assert not any(op=='core.module_install' for op,_,_ in calls)


def test_disabled_module_never_silently_enabled(installer,monkeypatch):
    m,p=installer
    monkeypatch.setattr(m,'query',lambda *a,**k:[{'id':'example','state':'disabled'}])
    with pytest.raises(RuntimeError,match='explicit repair'):
        m.ensure_modules([],p,[{'id':'example','path':'modules/example'}])


def test_missing_operations_cannot_report_success(installer,monkeypatch):
    m,p=installer;source=p/'runtime/modules/example';source.mkdir(parents=True)
    (source/'module.json').write_text(json.dumps({'operations':[{'name':'example.read'}]}))
    monkeypatch.setattr(m,'query',lambda *a,**k:[{'id':'example','state':'enabled','operations':[]}])
    with pytest.raises(RuntimeError,match='requires an update'):
        m.ensure_modules([],p,[{'id':'example','path':'modules/example'}])

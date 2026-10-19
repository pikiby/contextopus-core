import pytest
from contextopus.integrations.native import plan, integrate, IntegrationConflict
from contextopus.core.module_management import ModuleManager
from contextopus.core.operations import OperationRegistry
from types import SimpleNamespace
import json


def setup_module_root(root):
    module = root / 'modules/sample'
    skill = module / 'package/skills/sample-help'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: sample-help\ndescription: Sample help\n---\nRead scripts/help.py')
    (skill / 'scripts/help.py').write_text('print("help")\n')
    (skill / 'asset.bin').write_bytes(b'\x00\xff')
    (module / 'module.json').write_text(json.dumps({'id':'sample','version':'1.0','skills':'skills','operations':[]}))
    manager = ModuleManager(SimpleNamespace(layout=SimpleNamespace(root=root),registry=OperationRegistry()))
    return manager, skill


def test_native_integrates_only_enabled_prepared_skills_and_supporting_files(tmp_path):
    root, project = tmp_path / 'root', tmp_path / 'project'
    manager, skill = setup_module_root(root)
    assert not any('sample-help' in item['path'] for item in plan('codex',project,root=root)['writes'])
    manager.prepare('sample')
    manager.enable('sample')
    preview = plan('codex',project,root=root)
    assert preview['module_errors'] == []
    integrate(preview)
    target = project / '.agents/skills/sample-help'
    assert (target / 'SKILL.md').read_bytes() == (skill / 'SKILL.md').read_bytes()
    assert (target / 'scripts/help.py').read_text() == 'print("help")\n'
    assert (target / 'asset.bin').read_bytes() == b'\x00\xff'
    manager.disable('sample')
    preview = plan('codex',project,root=root)
    assert len([item for item in preview['removals'] if 'sample-help' in item['path']]) == 3
    integrate(preview)
    assert not (target / 'SKILL.md').exists()


def test_native_preserves_modified_module_skill_and_rejects_collision(tmp_path):
    root, project = tmp_path / 'root', tmp_path / 'project'
    manager, skill = setup_module_root(root)
    manager.prepare('sample')
    manager.enable('sample')
    target = project / '.agents/skills/sample-help/SKILL.md'
    target.parent.mkdir(parents=True)
    target.write_text('user skill')
    with pytest.raises(IntegrationConflict, match='collision'):
        plan('codex',project,root=root)
    target.unlink()
    integrate(plan('codex',project,root=root))
    target.write_text('user changed installed skill')
    manager.disable('sample')
    preview = plan('codex',project,root=root)
    assert str(target) in [item['path'] for item in preview['preserved']]
    integrate(preview)
    assert target.read_text() == 'user changed installed skill'


def test_native_module_skill_update_and_config_only(tmp_path):
    import shutil
    root, project = tmp_path / 'root', tmp_path / 'project'
    manager, skill = setup_module_root(root)
    manager.prepare('sample')
    manager.enable('sample')
    assert not any('sample-help' in item['path'] for item in plan('codex',project,root=root,install_skills=False)['writes'])
    integrate(plan('codex',project,root=root))
    replacement = tmp_path / 'replacement'
    shutil.copytree(root / 'modules/sample/package', replacement / 'package')
    (replacement / 'module.json').write_text(json.dumps({'id':'sample','version':'2.0','skills':'skills','operations':[]}))
    (replacement / 'package/skills/sample-help/scripts/help.py').write_text('print("new help")\n')
    manager.update('sample', str(replacement))
    preview = plan('codex',project,root=root)
    integrate(preview)
    assert (project / '.agents/skills/sample-help/scripts/help.py').read_text() == 'print("new help")\n'




def test_module_skill_names_cannot_case_collide_with_bundled_skills(tmp_path):
    root, project = tmp_path / 'root', tmp_path / 'project'
    manager, skill = setup_module_root(root)
    skill.rename(skill.with_name('M'))
    manager.prepare('sample')
    manager.enable('sample')
    with pytest.raises(IntegrationConflict, match='name collision: M'):
        plan('codex', project, root=root)

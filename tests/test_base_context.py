"""Base docs use ordinary records and recover exact managed updates."""
import copy
from unittest.mock import patch
import pytest
from contextopus.modules.workspace.base_context import BaseContext, packaged_bundle
from contextopus.modules.workspace.cycles import CycleRuntime
from contextopus.modules.workspace.runtime import PCWError
from test_runtime import Factory


@pytest.fixture
def base(tmp_path):
    (tmp_path / 'modules/workspace/workspace_contexts').mkdir(parents=True)
    factory = Factory()
    bundle = packaged_bundle()
    bundle['documents'] = [
        {'key': 'guide', 'type': 'guide', 'description': 'Explains the verified product workflow and where its requirements apply.', 'content': '# Product guide\n\nVerified product documentation.\n'},
        {'key': 'template', 'type': 'template', 'description': 'Provides the fields to review when authoring product instructions.', 'content': '# Product template\n\nPurpose: ...\n'}]
    return BaseContext(tmp_path, runtime_factory=lambda root, context:
        CycleRuntime(root, context, provider_factory=factory), bundle=bundle)


def install(service):
    result = service.install(service.plan()['plan_revision'])
    assert result['status'] == 'installed', result
    return result


def settings(service, changes):
    runtime = service.runtime_factory(service.layout.root, service.status()['managed_context'])
    try:
        preview = runtime.settings_preview(changes, 'Update the documentation context policy for this test')
        runtime.settings_apply(preview['preview_revision'], 'Approve the exact shown documentation settings')
    finally:
        runtime.close()


def test_passive_preview_then_shared_index_and_history(base):
    assert base.status()['context'] is None
    assert base.status()['next_action'] == 'core.base_plan'
    preview = base.plan()
    assert preview['create'] and preview['material_max_tokens'] is None
    assert not base.path.exists()
    assert not base._context_path(preview['context']).exists()
    install(base)
    state = base._read()
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        assert runtime.record_types()['types'] == [
            {'type': 'guide', 'count': 1}, {'type': 'project', 'count': 1}, {'type': 'template', 'count': 1}]
        for receipt in state['managed']['documents'].values():
            assert runtime.read(material_id=receipt['id'])['index_status'] == 'indexed'
        assert (runtime.engine.root / '.git').is_dir()
        assert base.plan()['status'] == 'current'
        assert base.install(base.plan()['plan_revision'])['status'] == 'current'
    finally:
        runtime.close()


@pytest.mark.parametrize('deleted', [False, True])
def test_preserve_modified_or_deleted_docs(base, deleted):
    install(base)
    state = base._read()
    receipt = state['managed']['documents']['guide']
    path = base._context_path(state['managed']['context']) / receipt['path']
    if deleted:
        path.unlink()
    else:
        path.write_text(path.read_text() + '\nUser knowledge\n')
    base.bundle['documents'][0]['content'] += '\nNew release guide\n'
    preview = base.plan()
    assert preview['status'] == 'conflicts'
    assert preview['conflicts'][0]['reason'] == ('deleted' if deleted else 'user_modified')
    assert preview['conflicts'][0]['incoming'] == base.bundle['documents'][0]['content']
    assert base.install(preview['plan_revision'])['status'] == 'conflicts'
    assert path.exists() is not deleted
    if not deleted:
        assert 'User knowledge' in path.read_text()


def test_preserve_custom_instructions_role_and_ids(base):
    install(base)
    initial = base._read()
    root = base._context_path(initial['managed']['context'])
    instructions = root / 'INSTRUCTIONS.md'
    custom = instructions.read_text() + '\nCustom documentation rule\n'
    instructions.write_text(custom)
    other = base.runtime_factory(base.layout.root, 'other')
    try:
        other.workspace_create('other-create', base.bundle['instructions'], '# Other project', 'Create another context',
                               settings=base.bundle['settings'], project_description='Defines the independent context used to verify documentation role selection.')
    finally:
        other.close()
    base.select('other')
    base.bundle['documents'][0]['content'] += '\nDocumented new behavior\n'
    base.bundle['version'] = 'next-version'
    updated = install(base)
    assert updated['context'] == 'other' and updated['active_rules_changed'] is False
    assert instructions.read_text() == custom
    assert base._read()['managed']['documents']['guide']['id'] == initial['managed']['documents']['guide']['id']
    assert base.plan()['status'] == 'current'


def test_stale_plan_and_unmanaged_collision(base):
    preview = base.plan()
    base._context_path(preview['context']).mkdir()
    with pytest.raises(PCWError, match='changed since preview'):
        base.install(preview['plan_revision'])
    collision = base.plan()
    assert collision['conflicts'][0]['reason'] == 'unmanaged_context_exists'
    assert base.install(collision['plan_revision'])['status'] == 'conflicts'


def test_changed_approval_requires_real_confirmation(base):
    install(base)
    instructions = base._context_path(base.status()['context']) / 'INSTRUCTIONS.md'
    settings(base, {'knowledge_approval_required': True})
    base.bundle['documents'][0]['content'] += '\nNew documentation\n'
    preview = base.plan()
    assert preview['approval_required'] is True
    assert base.install(preview['plan_revision'])['status'] == 'review_requires_approval'
    assert not base._read().get('pending')
    assert base.install(preview['plan_revision'], 'Approve exact shown documentation revision')['status'] == 'installed'


def test_changed_limit_needs_split_preserves_docs(base):
    install(base)
    instructions = base._context_path(base.status()['context']) / 'INSTRUCTIONS.md'
    settings(base, {'material_max_tokens': 20})
    custom = instructions.read_text()
    before = copy.deepcopy(base._read()['managed'])
    base.bundle['documents'][0]['content'] += '\n' + 'long text ' * 100
    result = base.install(base.plan()['plan_revision'])
    assert result['status'] == 'needs_split'
    assert instructions.read_text() == custom and base._read()['managed'] == before


def test_partial_apply_retries_same_proposal(base):
    original = CycleRuntime.proposal_apply
    calls = []
    def partial(runtime, *args, **kwargs):
        calls.append(args[1])
        if len(calls) == 1:
            return {'status': 'partial', 'error': 'Injected interruption'}
        return original(runtime, *args, **kwargs)
    preview = base.plan()
    with patch.object(CycleRuntime, 'proposal_apply', partial):
        assert base.install(preview['plan_revision'])['status'] == 'partial'
        assert base.plan()['status'] == 'pending'
        assert base.install(preview['plan_revision'])['status'] == 'installed'
    assert len(set(calls)) == 1
    assert len(base._read()['managed']['documents']) == 2


def test_long_packaged_docs_initially_unlimited_and_linked_to_project(base):
    base.bundle['documents'][0]['content'] += '\n' + 'documented behavior ' * 150
    base.bundle['documents'][0]['links'] = ['template']
    install(base)
    state = base._read()
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        guide = runtime.read(material_id=state['managed']['documents']['guide']['id'])
        assert runtime.project_read()['id'] in guide['links']
        assert state['managed']['documents']['template']['id'] in guide['links']
    finally:
        runtime.close()


def test_managed_update_preserves_user_added_links(base):
    install(base)
    state = base._read()
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        cycle = runtime.startup('custom-links')['cycle_id']
        created = runtime.proposal_prepare(cycle, [{'key': 'custom', 'content': '# User reference\nAdditional context', 'description': 'Explains the user reference conditions needed by the product guide.'}])
        runtime.proposal_apply(cycle, created['proposal_id'], created['revision'])
        user_id = created['created_ids']['custom']
        guide_id = state['managed']['documents']['guide']['id']
        guide = runtime.read(material_id=guide_id)
        changed = runtime.proposal_prepare(cycle, [{'material_id': guide_id, 'expected_revision': guide['revision'], 'links': [*guide['links'], user_id]}])
        runtime.proposal_apply(cycle, changed['proposal_id'], changed['revision'])
        runtime.finish(cycle)
    finally:
        runtime.close()
    base.bundle['documents'][0]['content'] += '\nUpdated guide\n'
    assert base.plan()['conflicts'] == []
    install(base)
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        assert user_id in runtime.read(material_id=guide_id)['links']
    finally:
        runtime.close()


def test_crash_after_preparation_recovers_saved_proposal(base):
    original = base._write
    crashed = False
    def interrupted(state):
        nonlocal crashed
        if state.get('pending', {}).get('stage') == 'apply' and not crashed:
            crashed = True
            raise OSError('Crash before installer receipt')
        return original(state)
    preview = base.plan()
    with patch.object(base, '_write', interrupted):
        with pytest.raises(OSError, match='installer receipt'):
            base.install(preview['plan_revision'])
    saved = base._read()['pending']
    assert saved['stage'] == 'prepare'
    assert base.install(preview['plan_revision'])['status'] == 'installed'
    assert len(base._read()['managed']['documents']) == 2


def test_bundle_descriptions_are_authored_and_description_only_updates_are_reviewed(base):
    assert all(item.get('description', '').strip() for item in packaged_bundle()['documents'])
    install(base)
    state = base._read()
    entry = state['managed']['documents']['guide']
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        original = runtime.read(material_id=entry['id'])
        assert original['description'] == base.bundle['documents'][0]['description']
    finally:
        runtime.close()
    incoming = 'Explains the product workflow, verified limits and newly documented applicability.'
    base.bundle['documents'][0]['description'] = incoming
    preview = base.plan()
    assert preview['status'] == 'ready' and preview['changes'][0]['description'] == incoming
    install(base)
    runtime = base.runtime_factory(base.layout.root, state['context'])
    try:
        updated = runtime.read(material_id=entry['id'])
        assert updated['description'] == incoming and updated['content'] == original['content']
        assert updated['id'] == original['id']
    finally:
        runtime.close()


def test_managed_update_preserves_user_description_as_conflict(base):
    from contextopus.modules.workspace.runtime import _parse
    import yaml
    install(base)
    state = base._read()
    entry = state['managed']['documents']['guide']
    path = base._context_path(state['managed']['context']) / entry['path']
    metadata, body = _parse(path.read_text())
    metadata['description'] = 'Describes the user-specific workflow and its verified exceptions.'
    path.write_text('---\n' + yaml.safe_dump(metadata, allow_unicode=True) + '---\n' + body)
    before = path.read_bytes()
    base.bundle['documents'][0]['content'] += '\nUpstream behavior.\n'
    plan = base.plan()
    assert plan['status'] == 'conflicts' and plan['conflicts'][0]['reason'] == 'user_modified'
    assert base.install(plan['plan_revision'])['status'] == 'conflicts'
    assert path.read_bytes() == before


def test_native_link_alias_reformat_does_not_look_like_user_content_change(base):
    from contextopus.modules.workspace.runtime import _parse
    import yaml
    base.bundle['documents'][0]['links'] = ['template']
    install(base)
    state = base._read()
    entry = state['managed']['documents']['guide']
    path = base._context_path(state['managed']['context']) / entry['path']
    metadata, body = _parse(path.read_text())
    assert all(link.startswith('[[') for link in metadata['links'])
    metadata['links'] = [link.split('|', 1)[0] + '|Readable user display]]' for link in metadata['links']]
    path.write_text('---\n' + yaml.safe_dump(metadata, allow_unicode=True) + '---\n' + body)
    assert base.plan()['status'] == 'current'
    base.bundle['documents'][0]['content'] += '\nUpstream behavior.\n'
    assert base.plan()['conflicts'] == []
    install(base)
    assert base.plan()['status'] == 'current'


def test_missing_native_target_is_a_reviewable_conflict_with_no_rewrite(base):
    base.bundle['documents'][0]['links'] = ['template']
    install(base)
    state = base._read()
    root = base._context_path(state['managed']['context'])
    guide = root / state['managed']['documents']['guide']['path']
    target = root / state['managed']['documents']['template']['path']
    target.unlink()
    before = guide.read_bytes()
    plan = base.plan()
    assert any(item['reason'] == 'navigation_conflict' for item in plan['conflicts'])
    assert base.install(plan['plan_revision'])['status'] == 'conflicts'
    assert guide.read_bytes() == before and not target.exists()

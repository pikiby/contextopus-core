import pytest
from contextopus.core.settings import Settings
from contextopus.core.storage import StorageLayout

def test_read_does_not_create_root(tmp_path):
    root = tmp_path / 'absent'
    settings = Settings(StorageLayout(root))
    assert settings.snapshot()['values']['include_archived'] is False
    assert not root.exists()

def test_preview_and_stale_revision(tmp_path):
    settings = Settings(StorageLayout(tmp_path))
    preview = settings.preview({'include_archived': True})
    assert not preview['requires_reindex']
    assert not settings.snapshot()['values']['include_archived']
    settings.apply(preview['preview_revision'])
    assert settings.snapshot()['values']['include_archived']
    with pytest.raises(ValueError): settings.apply(preview['preview_revision'])
    assert settings.preview({'model': 'new-model'})['requires_reindex']


def test_layers_request_safety_and_stale_selected_scope(tmp_path):
    import json
    import pytest
    from contextopus.core.settings import Settings
    from contextopus.core.storage import StorageLayout
    layout=StorageLayout(tmp_path);settings=Settings(layout)
    root=settings.preview({'searchN':3});settings.apply(root['preview_revision'])
    module=settings.preview({'searchN':5},module='workspace');settings.apply(module['preview_revision'])
    context=settings.preview({'searchN':7},module='workspace',context='alpha');settings.apply(context['preview_revision'])
    assert settings.snapshot()['values']['searchN']==3
    assert settings.snapshot(module='workspace')['values']['searchN']==5
    assert settings.snapshot(module='workspace',context='alpha')['values']['searchN']==7
    assert settings.snapshot(module='workspace',context='alpha',request={'searchN':11})['values']['searchN']==11
    before=settings.preview({'distance':0.5},module='workspace',context='alpha')
    path=settings._scope_path(module='workspace',context='alpha');path.write_text(json.dumps({'searchN':9}))
    with pytest.raises(ValueError,match='changed'): settings.apply(before['preview_revision'])
    with pytest.raises(ValueError): settings.snapshot(module='..')
    preview=settings.preview({'searchN':19},module='workspace',context='alpha',request_only=True)
    result=settings.apply(preview['preview_revision'])
    assert result['saved'] is False
    assert result['settings']['values']['searchN']==19
    assert settings.snapshot(module='workspace',context='alpha')['values']['searchN']==9

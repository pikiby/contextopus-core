"""Release transition fixtures use actual previously tagged skill bytes."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile
import shutil


import pytest

from contextopus.integrations import IntegrationConflict, integrate, plan

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_release_versions_and_documentation_agree():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert next(p["version"] for p in lock["package"] if p["name"] == "contextopus-core") == version
    # pathlib includes hidden native-client directories such as .codex-plugin.
    manifests = set((ROOT / "plugins/contextopus").rglob("plugin.json"))
    assert {ROOT / "plugins/contextopus/plugin.json",
            ROOT / "plugins/contextopus/.codex-plugin/plugin.json"} <= manifests
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["name"] == "contextopus"
        assert manifest["version"] == version, path
    assert (ROOT / "docs/releases" / f"{version}.md").is_file()




def test_release_bundles_hash_only_the_exact_asset_set(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('build_release_under_test', ROOT / 'scripts/build_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'VERSION', '1.3.0')
    def core_installer(destination, wheel):
        assert wheel.name == 'contextopus_core-1.3.0-py3-none-any.whl'
        (destination / 'contextopus-core-1.3.0.zip').write_bytes(b'Core installer fixture')
    monkeypatch.setattr(module, 'build_core_installer', core_installer)
    destination = tmp_path / 'dist'
    destination.mkdir()
    # Build orchestration must not include another candidate merely because its
    # filename contains the same version. Runtime archive contents are verified
    # independently by verify_release against the real artifacts.
    (destination / 'contextopus_core-1.3.0-py3-none-any.whl').write_bytes(b'wheel fixture')
    (destination / 'contextopus_core-1.3.0.tar.gz').write_bytes(b'source fixture')
    (destination / 'unrelated-1.3.0-candidate.zip').write_bytes(b'not a release asset')
    for name in ('LICENSE', 'NOTICE'):
        (tmp_path / name).write_text(name)
    core_skill = tmp_path / 'src/contextopus/resources/skills/m/SKILL.md'
    core_skill.parent.mkdir(parents=True)
    core_skill.write_text('Core module management')
    guide = tmp_path / 'docs/integrations/hermes.md'
    guide.parent.mkdir(parents=True)
    guide.write_text('Reviewed Hermes native integration guide')
    module.main()
    entries = (destination / 'SHA256SUMS').read_text().splitlines()
    assert len(entries) == 8
    assert {line.split('  ')[1] for line in entries} == {
        'contextopus_core-1.3.0-py3-none-any.whl',
        'contextopus_core-1.3.0.tar.gz',
        'contextopus-core-1.3.0.zip',
        *(f'contextopus-{client}-1.3.0.zip' for client in
          ('codex', 'claude-code', 'opencode', 'crush', 'hermes')),
    }
    assert all('candidate' not in line for line in entries)
    for line in entries:
        checksum, name = line.split('  ')
        assert checksum == hashlib.sha256((destination / name).read_bytes()).hexdigest()
    with zipfile.ZipFile(destination / 'contextopus-codex-1.3.0.zip') as archive:
        assert archive.read('skills/m/SKILL.md') == core_skill.read_bytes()
        instructions = archive.read('INSTALL.txt').decode()
        assert 'guide, read, write' in instructions
        assert 'CONTEXTOPUS_LEGACY_TOOLS=1' in instructions
        assert 'optional modules from their own repositories' in instructions
        assert 'modules install ID' in instructions
    with zipfile.ZipFile(destination / 'contextopus-hermes-1.3.0.zip') as archive:
        assert archive.read('skills/m/SKILL.md') == core_skill.read_bytes()
        assert archive.read('HERMES.md') == guide.read_bytes()
        instructions = archive.read('INSTALL.txt').decode()
        assert 'contextopus integrate hermes --user --apply' in instructions
        assert '$HERMES_HOME/config.yaml' in instructions
        assert '~/.hermes on Linux/macOS' in instructions
        assert '%LOCALAPPDATA%/hermes on Windows' in instructions
        assert 'fallback ~/AppData/Local/hermes' in instructions
        assert 'HERMES_DATA_DIR_SUFFIX' in instructions
        assert '$HERMES_HOME/skills/' in instructions
        assert '--hermes-home <directory>' in instructions
        assert '--project' not in instructions


def test_bundle_build_requires_matching_runtime_artifacts(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('build_release_missing', ROOT / 'scripts/build_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='exact wheel and source archive'):
        module.main()


def test_installed_verifier_refuses_wrong_version_or_checkout_prefix():
    spec = importlib.util.spec_from_file_location('verify_installed_guard', ROOT / 'scripts/verify_installed.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match='Expected deliberately-wrong-version'):
        module.verify('deliberately-wrong-version')
    from importlib.metadata import version
    with pytest.raises(ValueError, match='outside the clean installation prefix'):
        module.verify(version('contextopus-core'), prefix='/tmp/not-the-installed-candidate')

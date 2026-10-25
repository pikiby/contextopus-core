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
    spec=importlib.util.spec_from_file_location('release_test', ROOT/'scripts/build_release.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'VERSION','1.3.0')
    destination=tmp_path/'dist';destination.mkdir()
    for name in ('contextopus_core-1.3.0-py3-none-any.whl','contextopus_core-1.3.0.tar.gz','unrelated.zip'):
        (destination/name).write_bytes(b'fixture')
    def core(dest,wheel,modules=()):
        assert modules==[tmp_path/'workspace']
        (dest/'contextopus-core-1.3.0.zip').write_bytes(b'starter')
    def client(starter,output,name,platform):
        assert starter.read_bytes()==b'starter'
        output.write_bytes((name+platform).encode())
    monkeypatch.setattr(module,'build_core_installer',core)
    monkeypatch.setattr(module,'build_client_installer',client)
    module.main(destination,[tmp_path/'workspace'])
    entries=(destination/'SHA256SUMS').read_text().splitlines()
    assert len(entries)==15
    assert not any('unrelated' in line for line in entries)
    for line in entries:
        checksum,name=line.split('  ')
        assert checksum==hashlib.sha256((destination/name).read_bytes()).hexdigest()


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

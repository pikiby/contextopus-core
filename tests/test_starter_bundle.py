"""Artifact integrity, portability and deterministic starter-bundle packaging."""

import hashlib
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / "distribution"


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle = load_source("starter_bundle_validation", DISTRIBUTION / "bundle.py")
# Direct-script imports deliberately resolve the builder's sibling validator.
previous = sys.path[:]
try:
    sys.path.insert(0, str(DISTRIBUTION))
    builder = load_source("starter_bundle_builder", DISTRIBUTION / "build.py")
finally:
    sys.path[:] = previous


def make_wheel(path, *, filename_version="1.4.0", metadata_version=None, name="contextopus-core", extra=None):
    wheel = path / ("contextopus_core-" + filename_version + "-py3-none-any.whl")
    metadata_version = metadata_version or filename_version
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("contextopus_core-" + filename_version + ".dist-info/METADATA",
                         "Metadata-Version: 2.4\nName: " + name + "\nVersion: " + metadata_version + "\n")
        archive.writestr("contextopus/__init__.py", "__version__ = '" + filename_version + "'\n")
        if extra:
            for member, content in extra:
                archive.writestr(member, content)
    return wheel


@pytest.fixture
def inputs(tmp_path):
    support = tmp_path / "support"
    support.mkdir()
    for name in bundle.REQUIRED_FILES - {"LICENSE", "NOTICE", "bundle.py"}:
        (support / name).write_text("Starter fixture " + name + "\n", encoding="utf-8")
    shutil.copy2(DISTRIBUTION / "bundle.py", support / "bundle.py")
    (support / "install_support.py").write_text("# Optional installer helper\n")
    legal = tmp_path / "core"
    legal.mkdir()
    (legal / "LICENSE").write_text("Core test license\n")
    (legal / "NOTICE").write_text("Core test notice\n")
    wheel = make_wheel(tmp_path)
    module = tmp_path / "custom_module"
    (module / "package").mkdir(parents=True)
    (module / "package/worker.py").write_bytes(b"# Preserve exact source bytes\r\n")
    (module / "module.json").write_text(json.dumps({
        "id": "custom_module", "version": "0.7.6", "core_requires": ">=1.4,<2",
        "operations": [],
    }))
    (module / "LICENSE.md").write_text("Independent module license\n")
    (module / "NOTICE").write_text("Independent module notice\n")
    return dict(wheel=wheel, module=module, support=support, legal=legal, tmp=tmp_path)


def build(inputs, name="starter.zip", modules=None):
    return builder.build_bundle(
        inputs["wheel"], [inputs["module"]] if modules is None else modules,
        inputs["tmp"] / name, "1.4.0-dev", distribution=inputs["support"], core_root=inputs["legal"],
    )


def extracted(inputs):
    archive = build(inputs)
    destination = inputs["tmp"] / "unpacked"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(destination)
    return destination / "contextopus"


def rewrite_manifest(root, mutation):
    path = root / "bundle.json"
    value = json.loads(path.read_text())
    mutation(value)
    path.write_text(json.dumps(value))


def test_deterministic_build_preserves_inputs_and_pins_every_file(inputs):
    one = build(inputs)
    two = build(inputs, "second.zip")
    assert one.read_bytes() == two.read_bytes()
    assert Path(str(one) + ".sha256").read_text() == hashlib.sha256(one.read_bytes()).hexdigest() + "  starter.zip\n"
    with zipfile.ZipFile(one) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert all(name.startswith("contextopus/") for name in archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert archive.read("contextopus/modules/custom_module/package/worker.py") == b"# Preserve exact source bytes\r\n"
        assert archive.read("contextopus/modules/custom_module/LICENSE.md") == (inputs["module"] / "LICENSE.md").read_bytes()
        manifest = json.loads(archive.read("contextopus/bundle.json"))
        payload = {info.filename.removeprefix("contextopus/"): archive.read(info) for info in archive.infolist() if not info.is_dir()}
    assert manifest["python"] == "3.12"
    assert manifest["bundle_version"] == "1.4.0-dev"
    assert manifest["core"]["version"] == "1.4.0"
    assert manifest["modules"] == [{"id": "custom_module", "version": "0.7.6", "core_requires": ">=1.4,<2", "path": "modules/custom_module"}]
    assert manifest["files"] == {path: hashlib.sha256(data).hexdigest() for path, data in payload.items() if path != "bundle.json"}


def test_loader_works_without_site_packages(inputs):
    root = extracted(inputs)
    script = """import importlib.util,sys
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('validator',sys.argv[1]+'/bundle.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.load_bundle(sys.argv[1])['core']['version']=='1.4.0'
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(root)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (root / "__pycache__").exists()


def test_refuses_existing_archive_or_checksum(inputs):
    output = build(inputs)
    old = output.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build(inputs)
    assert output.read_bytes() == old
    output.unlink()
    with pytest.raises(ValueError, match="overwrite"):
        build(inputs)
    assert not output.exists()


def test_unicode_output_name_uses_a_readable_external_checksum(inputs):
    output = build(inputs, "café.zip")
    assert Path(str(output) + ".sha256").read_text(encoding="utf-8").endswith("  café.zip\n")


@pytest.mark.parametrize("kind", ["changed", "missing", "extra", "symlink"])
def test_payload_tampering_is_rejected(inputs, kind):
    root = extracted(inputs)
    source = root / "modules/custom_module/package/worker.py"
    if kind == "changed":
        source.write_bytes(b"modified")
    elif kind == "missing":
        source.unlink()
    elif kind == "extra":
        (root / "extra.txt").write_text("undeclared")
    else:
        source.unlink()
        source.symlink_to(inputs["module"] / "package/worker.py")
    with pytest.raises(ValueError):
        bundle.load_bundle(root)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/drive", "modules\\escape", "modules/a/../b", "packages/CON.whl", "modules/a/trailing.", "modules/a/bad:name", "modules/a//file"])
def test_manifest_paths_are_portable_and_contained(inputs, path):
    root = extracted(inputs)
    rewrite_manifest(root, lambda value: value["files"].update({path: "0" * 64}))
    with pytest.raises(ValueError):
        bundle.load_bundle(root)


def test_duplicate_module_ids_are_rejected_by_builder_and_loader(inputs):
    with pytest.raises(ValueError, match="Duplicate module ID"):
        build(inputs, modules=[inputs["module"], inputs["module"]])
    root = extracted(inputs)
    rewrite_manifest(root, lambda value: value["modules"].append(dict(value["modules"][0])))
    with pytest.raises(ValueError, match="Duplicate module ID"):
        bundle.load_bundle(root)


def test_case_insensitive_collisions_are_rejected(inputs):
    (inputs["module"] / "package/WORKER.py").write_text("collision")
    with pytest.raises(ValueError, match="collision"):
        build(inputs)


@pytest.mark.parametrize("field", ["version", "core_requires"])
def test_module_declaration_mismatch_is_rejected_even_with_valid_file_hashes(inputs, field):
    root = extracted(inputs)
    rewrite_manifest(root, lambda value: value["modules"][0].update({field: "2"}))
    with pytest.raises(ValueError, match="Module manifest differs"):
        bundle.load_bundle(root)


def test_core_version_declaration_mismatch_is_rejected(inputs):
    root = extracted(inputs)
    rewrite_manifest(root, lambda value: value["core"].update(version="9.0"))
    with pytest.raises(ValueError, match="Core version differs"):
        bundle.load_bundle(root)


@pytest.mark.parametrize("extra", [[("../escape", b"bad")], [("/absolute", b"bad")], [("folder\\bad", b"bad")], [("contextopus/__init__.py", b"duplicate")]])
def test_wheel_traversal_and_duplicate_archive_entries_are_rejected(inputs, extra):
    duplicate = any(name == "contextopus/__init__.py" for name, _ in extra)
    with (pytest.warns(UserWarning, match="Duplicate name") if duplicate else nullcontext()):
        inputs["wheel"] = make_wheel(inputs["tmp"], extra=extra)
    with pytest.raises(ValueError):
        build(inputs)


def test_wheel_symlink_is_rejected(inputs):
    with zipfile.ZipFile(inputs["wheel"], "a") as archive:
        info = zipfile.ZipInfo("contextopus/link.py")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../outside")
    with pytest.raises(ValueError, match="symlinks"):
        build(inputs)


def test_wheel_case_collisions_in_empty_directories_are_rejected(inputs):
    inputs["wheel"] = make_wheel(inputs["tmp"], extra=[("EMPTY/", b""), ("empty/", b"")])
    with pytest.raises(ValueError, match="collision"):
        build(inputs)


@pytest.mark.parametrize("change", [{"metadata_version": "9.0"}, {"name": "different-project"}])
def test_wheel_filename_and_metadata_must_match(inputs, change):
    inputs["wheel"] = make_wheel(inputs["tmp"], **change)
    with pytest.raises(ValueError):
        build(inputs)


def test_incompatible_core_is_rejected_before_archive_creation(inputs):
    manifest = inputs["module"] / "module.json"
    value = json.loads(manifest.read_text())
    value["core_requires"] = ">=9,<10"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="incompatible"):
        build(inputs)
    assert not (inputs["tmp"] / "starter.zip").exists()


def test_modules_require_their_own_license(inputs):
    (inputs["module"] / "LICENSE.md").unlink()
    with pytest.raises(ValueError, match="LICENSE"):
        build(inputs)


@pytest.mark.parametrize("path", ["data/catalog.sqlite3", "package/__pycache__/worker.pyc", "config/runtime.json", "package/model.safetensors", "package/sessions.jsonl", "package/catalog.sqlite3-wal", "package/transcripts.jsonl.zst"])
def test_module_live_state_models_and_caches_are_not_bundled(inputs, path):
    target = inputs["module"] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not distributable")
    with pytest.raises(ValueError):
        build(inputs)


@pytest.mark.parametrize("path", [".env", ".env.local", "credentials.json", ".credentials.toml", "secrets.yaml", ".runtime.json.bak", ".config.old", ".tmp/result.json", "tmp/work.json", "workspace_contexts/project/record.md", ".backups/previous.json"])
def test_module_root_credentials_backups_and_working_state_are_rejected(inputs, path):
    target = inputs["module"] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("dummy fixture data")
    with pytest.raises(ValueError):
        build(inputs)


def test_legitimate_packaged_templates_and_code_directories_are_preserved(inputs):
    paths = ["package/templates/.env.example", "package/templates/credentials.example",
             "package/templates/config/runtime.json", "package/tmp/helpers.py",
             "package/workspace_contexts/schema.py"]
    for path in paths:
        target = inputs["module"] / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("public template or source")
    output = build(inputs)
    with zipfile.ZipFile(output) as archive:
        for path in paths:
            assert archive.read("contextopus/modules/custom_module/" + path) == b"public template or source"


def test_missing_installer_is_a_build_error(inputs):
    (inputs["support"] / "install.sh").unlink()
    with pytest.raises(ValueError, match="support file"):
        build(inputs)


def test_unknown_schema_python_duplicate_json_keys_and_extra_owners_fail(inputs):
    root = extracted(inputs)
    original = (root / "bundle.json").read_text()
    for field, changed in [("schema_version", 2), ("python", "3.13")]:
        rewrite_manifest(root, lambda value: value.update({field: changed}))
        with pytest.raises(ValueError):
            bundle.load_bundle(root)
        (root / "bundle.json").write_text(original)
    (root / "bundle.json").write_text(original.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    with pytest.raises(ValueError, match="Duplicate JSON"):
        bundle.load_bundle(root)
    (root / "bundle.json").write_text(original)
    (root / "unowned.txt").write_bytes(b"owned by nobody")
    rewrite_manifest(root, lambda value: value["files"].update({"unowned.txt": hashlib.sha256(b"owned by nobody").hexdigest()}))
    with pytest.raises(ValueError, match="no declared owner"):
        bundle.load_bundle(root)


def test_empty_package_and_no_modules_are_supported(inputs):
    (inputs["module"] / "package/worker.py").unlink()
    root = extracted(inputs)
    assert (root / "modules/custom_module/package").is_dir()
    assert bundle.load_bundle(root)["modules"][0]["id"] == "custom_module"
    no_modules = build(inputs, "core-only.zip", modules=[])
    with zipfile.ZipFile(no_modules) as archive:
        assert json.loads(archive.read("contextopus/bundle.json"))["modules"] == []

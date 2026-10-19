"""Inspect and stage a trusted built folder/ZIP without running module code."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

from .module_files import (PackageError, _MODULE_ID, _collision_key, _object_pairs, _unique_paths,
                           check_module_payload, module_metadata, safe_path,
                           tree_files)

MAX_FILES = 10_000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _digest(stream, target=None):
    digest, size = hashlib.sha256(), 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise PackageError('Module file exceeds the 256 MiB limit')
        digest.update(chunk)
        if target is not None:
            target.write(chunk)
    return digest.hexdigest(), size


def _regular(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PackageError('Expected a regular module payload file')
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def _archive_members(archive, module):
    infos = archive.infolist()
    if len(infos) > MAX_FILES:
        raise PackageError('Module archive has too many entries')
    names = [item.filename.rstrip('/') for item in infos]
    if len(names) != len(set(names)):
        raise PackageError('Duplicate module archive member')
    for info, name in zip(infos, names):
        safe_path(name)
        mode = info.external_attr >> 16
        if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise PackageError('Module archive symlinks/special files are forbidden')
        if info.flag_bits & 1:
            raise PackageError('Encrypted module archives are forbidden')
        if info.file_size > MAX_FILE_BYTES:
            raise PackageError('Module archive file exceeds the 256 MiB limit')
    _unique_paths([item.filename for item in infos if not item.is_dir()])
    spellings = {}
    for name in names:
        parts = name.split('/')
        for length in range(1, len(parts) + 1):
            spelling = '/'.join(parts[:length])
            key = _collision_key(spelling)
            if key in spellings and spellings[key] != spelling:
                raise PackageError('Case-insensitive archive path collision')
            spellings[key] = spelling
    if ({_collision_key(item.filename) for item in infos if not item.is_dir()}
            & {_collision_key(item.filename.rstrip('/')) for item in infos if item.is_dir()}):
        raise PackageError('Archive file is also used as a directory')
    prefix = '' if 'module.json' in names else module + '/'
    if prefix + 'module.json' not in names:
        raise PackageError('ZIP must contain module.json and package/ at its root or under its module ID')
    if prefix and any(name != module and not name.startswith(prefix) for name in names):
        raise PackageError('Module ZIP contains unrelated top-level files')
    members = {}
    for info in infos:
        name = info.filename.rstrip('/')
        if prefix and name == module and info.is_dir():
            continue
        relative = name[len(prefix):]
        safe_path(relative)
        check_module_payload([relative])
        if not info.is_dir():
            members[relative] = info
    check_module_payload(members)
    if not any(name.startswith('package/') for name in members) and prefix + 'package' not in names:
        raise PackageError('Module ZIP requires a package directory')
    return members


def inspect_source(source, module):
    """Read and hash every payload byte; no dependencies, code, schema or copies."""
    if not isinstance(module, str) or not _MODULE_ID.fullmatch(module) or module == 'core':
        raise PackageError('Invalid module ID')
    source = Path(source).expanduser()
    if source.is_symlink():
        raise PackageError('Module source must not be a symlink')
    source = source.resolve()
    hashes, modes, total = {}, {}, 0
    if source.is_dir():
        paths = tree_files(source)
        check_module_payload(paths + [path.relative_to(source).as_posix()
                                     for path in source.rglob('*') if path.is_dir()])
        metadata = module_metadata(source)
        if len(paths) > MAX_FILES:
            raise PackageError('Module source has too many files')
        manifest = json.loads((source / 'module.json').read_text(encoding='utf-8'), object_pairs_hook=_object_pairs)
        for name in paths:
            with _regular(source / name) as stream:
                hashes[name], size = _digest(stream)
            modes[name] = (source / name).stat().st_mode & 0o755
            total += size
            if total > MAX_TOTAL_BYTES:
                raise PackageError('Module source exceeds the 512 MiB limit')
    else:
        try:
            with zipfile.ZipFile(source) as archive:
                members = _archive_members(archive, module)
                info = members.get('module.json')
                if info is None or info.file_size > 1024 * 1024:
                    raise PackageError('Missing/oversized module.json')
                manifest = json.loads(archive.read(info).decode('utf-8'), object_pairs_hook=_object_pairs)
                if not isinstance(manifest, dict):
                    raise PackageError('module.json must contain an object')
                for name, info in members.items():
                    with archive.open(info) as stream:
                        hashes[name], size = _digest(stream)
                    modes[name] = (info.external_attr >> 16) & 0o755 or 0o644
                    total += size
                    if total > MAX_TOTAL_BYTES:
                        raise PackageError('Module source exceeds the 512 MiB limit')
                metadata = {key: manifest.get(key) for key in ('id', 'version', 'core_requires')}
        except (zipfile.BadZipFile, KeyError, UnicodeError) as exc:
            raise PackageError('Cannot read a built module ZIP') from exc
    if total > MAX_TOTAL_BYTES:
        raise PackageError('Module source exceeds the 512 MiB limit')
    if metadata['id'] != module:
        raise PackageError('Source module ID differs from the requested module')
    if not all(isinstance(metadata[key], str) and metadata[key] for key in metadata):
        raise PackageError('Module artifact must declare id, version and core_requires')
    fingerprint = hashlib.sha256(json.dumps({'files': hashes, 'modes': modes}, sort_keys=True).encode()).hexdigest()
    return {'source': str(source), 'module': module, 'version': metadata['version'],
            'core_requires': metadata['core_requires'], 'manifest': manifest,
            'files': hashes, 'modes': modes, 'bytes': total, 'fingerprint': fingerprint}


@contextmanager
def staged_source(plan, parent):
    """Copy into an owned temporary folder and reject changes before publication."""
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.module-source-', dir=parent) as temporary:
        stage, source = Path(temporary), Path(plan['source'])
        (stage / 'package').mkdir()
        archive = zipfile.ZipFile(source) if source.is_file() else None
        try:
            members = _archive_members(archive, plan['module']) if archive else None
            for name, expected in plan['files'].items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with (archive.open(members[name]) if archive else _regular(source / name)) as stream, target.open('xb') as output:
                    digest, _ = _digest(stream, output)
                if digest != expected:
                    raise PackageError('Module source changed during staging; inspect it again')
                target.chmod(plan['modes'][name])
            if inspect_source(source, plan['module'])['fingerprint'] != plan['fingerprint']:
                raise PackageError('Module source changed during staging; inspect it again')
            yield stage
        finally:
            if archive is not None:
                archive.close()


def publish_new(stage, target):
    """Reserve a new target exclusively; publish its manifest after complete code."""
    target = Path(target)
    target.mkdir()  # Never replace even an empty concurrently-created directory.
    try:
        for entry in Path(stage).iterdir():
            if entry.name != 'module.json':
                os.replace(entry, target / entry.name)
        os.replace(Path(stage) / 'module.json', target / 'module.json')
    except BaseException as exc:
        raise RuntimeError(f'Module publication was interrupted; preserve and inspect {target}') from exc

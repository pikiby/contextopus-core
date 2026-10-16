"""Versioned product documentation stored as ordinary Workspace records.

The role pointer never selects active instructions. Only an explicit install
applies its exact preview, through the standard Workspace proposal machinery.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
from importlib.metadata import version
import json
import os
import tempfile

from contextopus.core.storage import StorageLayout, sync_directory
from .cycles import CycleRuntime
from .policies import policies
from .runtime import PCWError, _parse

DEFAULT_CONTEXT = 'contextopus-base'


def _revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def packaged_bundle():
    source = files('contextopus').joinpath('resources', 'base_context')
    manifest = json.loads(source.joinpath('manifest.json').read_text())
    documents = []
    for item in manifest['documents']:
        content = source.joinpath(item['file']).read_text()
        if item['key'] == 'installed-version':
            content = content.replace(manifest['version'], version('contextopus-core'))
        documents.append({**item, 'content': content})
    instructions = files('contextopus.modules.workspace').joinpath('default_instructions.md').read_text()
    # These product docs may be long; ordinary contexts keep their own limits.
    instructions = instructions.replace('material_max_tokens: 1024', 'material_max_tokens: null')
    instructions += '\n## Product documentation context\n\nThis context holds packaged product documentation and has no material length limit. Reading these records never changes an active task context or its instructions. Future edits to these rules govern product documentation updates too.\n'
    return {**manifest, 'version': version('contextopus-core'), 'documents': documents, 'instructions': instructions,
            'project': '# Contextopus product documentation\n\nInstalled-version guides, examples and templates. These records are reference material; reading them never changes the active context or its rules.\n'}


class BaseContext:
    def __init__(self, work_root, *, runtime_factory=CycleRuntime, bundle=None):
        self.layout = StorageLayout.resolve(work_root)
        self.path = self.layout.configuration / 'base-context.json'
        self.runtime_factory = runtime_factory
        self.bundle = bundle if bundle is not None else packaged_bundle()

    def _read(self):
        return json.loads(self.path.read_text()) if self.path.is_file() else {}

    def _write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise PCWError('Base context configuration cannot be a symlink')
        fd, temporary = tempfile.mkstemp(prefix='.base-context-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            sync_directory(self.path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _context_path(self, name):
        self.layout._name(name)
        path = self.layout.workspace_base / name
        if path.is_symlink():
            raise PCWError('Base context cannot be a symlink')
        return path

    def status(self):
        state = self._read()
        selected = state.get('context')
        installed = state.get('managed', {})
        return {'context': selected, 'path': str(self._context_path(selected)) if selected else None,
                'present': bool(selected and (self._context_path(selected) / 'INSTRUCTIONS.md').is_file()),
                'installed_version': installed.get('version'), 'packaged_version': self.bundle['version'],
                'managed_context': installed.get('context'),
                'pending': {key: state['pending'].get(key) for key in ('revision', 'stage')} if state.get('pending') else None,
                'next_action': 'core.base_install' if state.get('pending') else 'core.base_plan' if not installed or installed.get('version') != self.bundle['version'] else None,
                'active_rules_changed': False}

    def select(self, context: str):
        path = self._context_path(context)
        if not (path / 'INSTRUCTIONS.md').is_file() or not (path / 'knowledge').is_dir():
            raise PCWError('Select an existing Workspace context')
        with self.layout.guard():
            state = self._read()
            state['context'] = context
            self._write(state)
        return self.status()

    def plan(self):
        state = self._read()
        if state.get('pending'):
            pending = state['pending']
            return {**pending['plan'], 'status': 'pending', 'plan_revision': pending['revision'],
                    'next_action': 'core.base_install', 'active_rules_changed': False}
        managed = state.get('managed', {})
        context = managed.get('context', DEFAULT_CONTEXT)
        root = self._context_path(context)
        create = not managed
        conflicts, changes, unchanged = [], [], []
        incoming = {item['key']: item for item in self.bundle['documents']}
        if create and root.exists():
            conflicts.append({'reason': 'unmanaged_context_exists', 'path': str(root),
                              'incoming': self.bundle})
        instructions_path = root / 'INSTRUCTIONS.md'
        instructions_hash = _file_hash(instructions_path)
        if managed and instructions_hash is None:
            conflicts.append({'reason': 'instructions_missing', 'path': str(instructions_path),
                              'incoming': self.bundle['instructions']})
        instructions = instructions_path.read_text() if instructions_hash else self.bundle['instructions']
        settings = policies(instructions)
        for key, item in incoming.items():
            previous = managed.get('documents', {}).get(key)
            if previous:
                path = root / previous['path']
                actual = _file_hash(path)
                metadata, body = _parse(path.read_text()) if actual else ({}, '')
                compatible_metadata_edit = (actual is not None and _revision(body) == previous.get('body_revision')
                    and metadata.get('id') == previous['id'] and metadata.get('type') == previous.get('type', item['type'])
                    and set(previous.get('links', [])) <= set(metadata.get('links', [])))
                if actual != previous['file_hash'] and not compatible_metadata_edit:
                    conflicts.append({'key': key, 'path': str(path),
                                      'reason': 'deleted' if actual is None else 'user_modified',
                                      'current': path.read_text() if actual else None,
                                      'incoming': item['content']})
                    continue
                required_links = [managed.get('documents', {}).get(key, {}).get('id') for key in item.get('links', [])]
                links_complete = all(ident and ident in metadata.get('links', []) for ident in required_links)
                if body == item['content'] and metadata.get('type') == item['type'] and links_complete:
                    unchanged.append(key)
                    continue
                changes.append({'key': key, 'material_id': previous['id'],
                                'expected_file_hash': actual, 'before': body, 'content': item['content'],
                                'type': item['type'], 'bundle_links': item.get('links', [])})
            else:
                changes.append({'key': key, 'before': None, 'content': item['content'], 'type': item['type'], 'bundle_links': item.get('links', [])})
        # Removed bundle entries remain user-visible records, never automatic deletions.
        retired = sorted(set(managed.get('documents', {})) - set(incoming))
        result = {'context': context, 'version': self.bundle['version'], 'create': create,
                  'instructions_revision': instructions_hash, 'changes': changes,
                  'conflicts': conflicts, 'unchanged': unchanged, 'retained_retired': retired,
                  'approval_required': settings['knowledge_approval_required'],
                  'material_max_tokens': settings['material_max_tokens'],
                  'initial_instructions': self.bundle['instructions'] if create else None,
                  'initial_project': self.bundle['project'] if create else None,
                  'state_revision': _revision(state), 'active_rules_changed': False}
        result['plan_revision'] = _revision(result)
        result['status'] = 'conflicts' if conflicts else 'ready' if changes or create or managed.get('version') != self.bundle['version'] else 'current'
        return result

    def install(self, plan_revision: str, confirmation: str | None = None):
        with self.layout.guard():
            state = self._read()
            pending = state.get('pending')
            preview = self.plan()
            if preview['plan_revision'] != plan_revision:
                raise PCWError('Base context changed since preview; read core.base_plan again')
            if preview['conflicts']:
                return {'status': 'conflicts', 'conflicts': preview['conflicts'], 'active_rules_changed': False}
            if not pending and preview['status'] == 'current':
                return {**self.status(), 'status': 'current'}
            if preview['approval_required'] and (not isinstance(confirmation, str) or not confirmation.strip()):
                return {'status': 'review_requires_approval', 'plan_revision': plan_revision,
                        'review_changes': preview['changes'], 'active_rules_changed': False}
            if not pending:
                pending = {'revision': plan_revision, 'plan': preview, 'stage': 'create',
                           'documents': dict(state.get('managed', {}).get('documents', {}))}
                state['pending'] = pending
                self._write(state)
            runtime = self.runtime_factory(self.layout.root, preview['context'])
            try:
                return self._apply(runtime, state, pending, confirmation)
            finally:
                runtime.close()

    def _apply(self, runtime, state, pending, confirmation):
        preview, revision = pending['plan'], pending['revision']
        if pending['stage'] == 'create':
            if preview['create']:
                created = runtime.workspace_create('base-create-' + revision[:32],
                    preview['initial_instructions'], preview['initial_project'],
                    'Install the exact packaged Contextopus base documentation from the reviewed plan')
                if created['status'] != 'created':
                    return {'status': created['status'], 'plan_revision': revision, 'result': created}
            pending['stage'] = 'prepare'
            self._write(state)
        if pending['stage'] == 'prepare':
            opened = runtime.startup('base-install-' + revision[:32])
            pending['cycle_id'] = opened['cycle_id']
            self._write(state)
            changes = []
            project = runtime.project_read()
            for item in preview['changes']:
                change = {key: item[key] for key in ('content', 'type')}
                if item.get('material_id'):
                    current = runtime.read(material_id=item['material_id'])
                    path = runtime.engine.root / current['path']
                    if _file_hash(path) != item['expected_file_hash']:
                        raise PCWError('Managed base document changed; preserve it and review a fresh plan')
                    change.update(material_id=item['material_id'], expected_revision=current['revision'], links=list(current['links']))
                else:
                    change['key'] = item['key']
                    change['links'] = []
                desired = [pending['documents'][key]['id'] if key in pending['documents'] else '@' + key for key in item.get('bundle_links', [])]
                desired.append(project['id'])
                change['links'] = list(dict.fromkeys([*change['links'], *desired]))
                changes.append(change)
            try:
                # A crash after runtime preparation but before our receipt must
                # resume that exact dedicated-cycle proposal, never allocate twice.
                proposals = runtime._records()['cycles'][pending['cycle_id']]['proposals']
                if len(proposals) > 1:
                    raise PCWError('Unexpected additional proposal in base installation cycle')
                if proposals:
                    ident, entry = next(iter(proposals.items()))
                    saved = runtime._load_plan(pending['cycle_id'], ident, entry)
                    proposal = {'proposal_id': ident, 'revision': entry['revision'],
                                'status': entry['state'], 'created_ids': saved['created_ids']}
                else:
                    proposal = runtime.proposal_prepare(pending['cycle_id'], changes,
                        no_changes_reason='Packaged documents already match' if not changes else None,
                        summary='Update Contextopus product documentation')
            except PCWError as exc:
                # Size-policy failures stay recoverable without modifying instructions.
                return {'status': 'needs_review', 'error': str(exc), 'plan_revision': revision,
                        'next_action': 'review_base_context_instructions', 'active_rules_changed': False}
            if proposal['status'] == 'needs_split':
                return {**proposal, 'plan_revision': revision, 'active_rules_changed': False}
            pending.update(stage='finish' if proposal['status'] == 'no_changes' else 'apply', proposal_id=proposal['proposal_id'],
                           proposal_revision=proposal['revision'], created_ids=proposal['created_ids'])
            self._write(state)
        if pending['stage'] == 'apply':
            review = runtime.proposal_read(pending['cycle_id'], pending['proposal_id'])
            if review['approval_required'] and (not isinstance(confirmation, str) or not confirmation.strip()):
                return {'status': 'review_requires_approval', 'plan_revision': revision,
                        'review_changes': review['review_changes'], 'active_rules_changed': False}
            result = runtime.proposal_apply(pending['cycle_id'], pending['proposal_id'],
                                           pending['proposal_revision'], confirmation=confirmation)
            if result['status'] != 'applied':
                return {'status': result['status'], 'plan_revision': revision, 'result': result,
                        'active_rules_changed': False}
            for item in preview['changes']:
                ident = item.get('material_id') or pending['created_ids'][item['key']]
                current = runtime.read(material_id=ident)
                pending['documents'][item['key']] = {'id': ident, 'path': current['path'],
                    'file_hash': _file_hash(runtime.engine.root / current['path']),
                    'body_revision': _revision(item['content']), 'type': item['type'],
                    'links': list(current['links'])}
            pending['stage'] = 'finish'
            self._write(state)
        result = runtime.finish(pending['cycle_id'])
        if result['status'] != 'closed':
            return {'status': 'partial', 'plan_revision': revision, 'result': result}
        state['managed'] = {'context': preview['context'], 'version': preview['version'],
                            'documents': pending['documents']}
        state.setdefault('context', preview['context'])
        state.pop('pending', None)
        self._write(state)
        return {**self.status(), 'status': 'installed', 'plan_revision': revision}


def register(app):
    service = BaseContext(app.layout.root, runtime_factory=lambda root, context:
        CycleRuntime(root, context, provider_factory=app.resources.acquire))
    app.base_context = service
    app._operation('core.base_status', 'query', service.status)
    app._operation('core.base_plan', 'query', service.plan)
    app._operation('core.base_install', 'execute', service.install,
                   {'plan_revision': (str, ...), 'confirmation': (str | None, None)})
    app._operation('core.base_select', 'execute', service.select, {'context': (str, ...)})


def prepare_setup(app):
    """Deliver bundled docs only at explicit init/model-apply boundaries.

    Readiness/status/search callers never invoke this function. Failures in
    documentation or derivative catalog delivery cannot undo a working model.
    """
    if app.active_profile() is None:
        return {'status': 'model_setup_required',
                'base_context': {'status': 'pending', 'next_action': 'core.model_plan'},
                'algorithm_catalog': {'status': 'pending', 'next_action': 'core.model_plan'}}
    try:
        catalog = {'status': 'ready', **app.execute('core.algorithms_refresh')}
    except Exception as exc:
        catalog = {'status': 'pending', 'error': str(exc), 'next_action': 'core.algorithms_refresh'}
    try:
        preview = app.query('core.base_plan')
        if preview['status'] == 'conflicts':
            documentation = {'status': 'conflicts', 'plan': preview, 'next_action': 'core.base_plan'}
        elif preview['approval_required'] and preview['status'] != 'current':
            documentation = {'status': 'review_requires_approval', 'plan': preview,
                             'next_action': 'core.base_install'}
        else:
            documentation = app.execute('core.base_install', {'plan_revision': preview['plan_revision']})
            if documentation['status'] not in {'installed', 'current'}:
                documentation.update(plan=preview, next_action='core.base_install')
    except Exception as exc:
        documentation = {'status': 'pending', 'error': str(exc), 'next_action': 'core.base_plan'}
    ready = documentation['status'] in {'installed', 'current'} and catalog['status'] == 'ready'
    return {'status': 'ready' if ready else 'pending', 'base_context': documentation,
            'algorithm_catalog': catalog}

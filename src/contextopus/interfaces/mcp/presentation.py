"""Transport-only presentation after dispatch and journaling; never edit source results."""
from contextopus.core.filtering import compact_diagnostics


_EMPTY_MATERIAL_FIELDS = {'description', 'status', 'sources', 'required_sources', 'links',
                          'link_targets', 'index_error'}
_EMPTY_PROBLEMS = {'warnings', 'errors', 'problems', 'pending_preparation', 'needs_correction', 'unregistered'}
_PRESENT_OPERATIONS = {
    'core.search', 'workspace.search', 'workspace.projects_search',
    'workspace.read', 'workspace.read_many', 'workspace.project_read', 'workspace.list',
    'workspace.startup', 'workspace.workspace_create', 'workspace.proposal_apply',
    'workspace.proposal_prepare', 'workspace.instructions_prepare', 'workspace.instructions_apply',
    'workspace.tmp_read', 'workspace.tmp_list',
}


def present(result, *, operation, arguments=None, detail='compact'):
    if detail not in ('compact', 'full'):
        raise ValueError('detail must be compact or full')
    if detail == 'full':
        return result
    if operation not in _PRESENT_OPERATIONS:
        import copy
        return copy.deepcopy(result)
    arguments = arguments or {}
    search = operation in {'core.search', 'workspace.search', 'workspace.projects_search'}
    fragment_output = arguments.get('output') == 'fragments' or (
        isinstance(result, dict) and (result.get('diagnostics') or {}).get('output') == 'fragments')

    def walk(value, field=None):
        # Review text, configuration nulls/false/0 and historical source evidence
        # have their own exact contracts; presentation must not reinterpret them.
        if field in {'review_changes', 'relation_candidates', 'settings', 'effective_settings', 'changes', 'diagnostics', 'metadata'}:
            if field == 'diagnostics' and search and isinstance(value, dict):
                return compact_diagnostics(value)
            import copy
            return copy.deepcopy(value)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        material = ('id' in value and any(k in value for k in ('title', 'content', 'path', 'workspace'))
                    or 'key' in value and 'distance' in value)
        output = {key: walk(item, key) for key, item in value.items()}
        if material:
            targets = value.get('link_targets')
            if isinstance(targets, list):
                labelled = {target['id']: target for target in targets
                            if isinstance(target, dict) and 'id' in target}
                output['links'] = [walk(link if isinstance(link, dict) else labelled.get(link, {'id': link, 'missing': True}))
                                   for link in value.get('links', [])]
                output.pop('link_targets', None)
            key = value.get('key')
            if isinstance(key, (list, tuple)) and len(key) == 3:
                output.setdefault('path', value.get('location'))
                if output.get('location') == output.get('path'):
                    output.pop('location', None)
                if key[0] == 'workspace':
                    output.setdefault('workspace', key[1])
                metadata = value.get('metadata', {})
                if isinstance(metadata, dict):
                    for name in ('description', 'type', 'status'):
                        if name in metadata:
                            output.setdefault(name, metadata[name])
                            if output[name] == metadata[name]:
                                output['metadata'].pop(name, None)
                    if not output.get('metadata'):
                        output.pop('metadata', None)
            for name in _EMPTY_MATERIAL_FIELDS:
                if output.get(name) in (None, '', []):
                    output.pop(name, None)
            if output.get('index_status') == 'indexed':
                output.pop('index_status')
            if search and not fragment_output:
                output.pop('excerpt', None)
        for key in _EMPTY_PROBLEMS:
            if output.get(key) in (None, [], {}):
                output.pop(key, None)
        analytics = output.get('analytics')
        if isinstance(analytics, dict) and analytics.get('status') == 'recorded' and set(analytics) <= {'status', 'event_id', 'duration'}:
            output.pop('analytics')
        return output

    return walk(result)

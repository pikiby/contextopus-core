"""Shared, metadata-observable candidate selection; providers use the same contract."""
from pathlib import Path
import importlib.util
import json
import math


class AlgorithmRegistry:
    def __init__(self, provider_directories=()):
        self._algorithms = {}
        self.refresh(provider_directories)

    def refresh(self, provider_directories=()):
        found = {}
        self.errors = []
        for root in [Path(__file__).parent / 'algorithms', *map(Path, provider_directories)]:
            paths = [root] if (root / 'description.json').is_file() else sorted(root.glob('*'))
            for path in paths:
                if not (path / 'description.json').is_file():
                    continue
                try:
                    description = json.loads((path / 'description.json').read_text())
                    for name in ('id', 'version', 'purpose', 'parameters_schema', 'defaults', 'when_to_use', 'how_to_adjust'):
                        if name not in description:
                            raise ValueError(f'Missing algorithm description field: {name}')
                    import jsonschema
                    jsonschema.Draft202012Validator.check_schema(description['parameters_schema'])
                    jsonschema.validate(description['defaults'], description['parameters_schema'])
                    if any(not isinstance(description[k], str) or not description[k] for k in ('id','version','purpose','when_to_use','how_to_adjust')):
                        raise ValueError('Algorithm description strings must be nonempty')
                    ident = description['id']
                    if ident in found:
                        raise ValueError(f'Duplicate search algorithm: {ident}')
                    spec = importlib.util.spec_from_file_location('contextopus_filter_' + ident, path / 'algorithm.py')
                    module = importlib.util.module_from_spec(spec)
                    exec(compile((path / "algorithm.py").read_text(), str(path / "algorithm.py"), "exec"), module.__dict__)
                    if not callable(getattr(module, 'select', None)):
                        raise ValueError('Algorithm must export select(rows, parameters)')
                    found[ident] = (description, module.select)
                except Exception as exc:
                    if root == Path(__file__).parent / 'algorithms':
                        raise
                    self.errors.append({'path':str(path), 'error':str(exc)})
        self._algorithms = found
        return self.catalog()

    def contains(self, ident):
        return isinstance(ident, str) and ident in self._algorithms

    def catalog(self, query=None):
        values = [dict(v[0]) for _, v in sorted(self._algorithms.items())]
        if query is None:
            return values
        exact = [d for d in values if d['id'] == query]
        return exact or [d for d in values if query.casefold() in json.dumps(d).casefold()]

    def resolve(self, selection=None):
        import jsonschema
        selection = selection or {'algorithm': 'distance_jump'}
        if not isinstance(selection, dict) or set(selection) - {'algorithm', 'parameters'}:
            raise ValueError('selection requires algorithm and parameters')
        ident = selection.get('algorithm', 'distance_jump')
        if ident not in self._algorithms:
            raise ValueError(f'Unknown search algorithm: {ident}')
        description, function = self._algorithms[ident]
        supplied = selection.get('parameters', {})
        if not isinstance(supplied, dict):
            raise ValueError('selection.parameters must be an object')
        parameters = {**description['defaults'], **supplied}
        if any(type(v) in (int,float) and not math.isfinite(v) for v in parameters.values()):
            raise ValueError('Algorithm numbers must be finite')
        try:
            jsonschema.validate(parameters, description['parameters_schema'])
        except jsonschema.ValidationError as exc:
            raise ValueError(exc.message) from exc
        return {'algorithm': ident, 'parameters': parameters}, description, function


def select(rows, selection=None, *, eligible_count=None, eligible_documents=None, eligible_fragments=None, output='materials', legacy=None, registry=None):
    registry = registry or registry_for_layout()
    if legacy is not None and selection is None:
        selection = {'algorithm': 'distance_jump', 'parameters': {k:v for k,v in legacy.items() if k in ('N','d_max','min_jump','multiplier')}}
    effective, description, function = registry.resolve(selection)
    if output not in ('materials','fragments'):
        raise ValueError('output must be materials or fragments')
    candidates = []
    for index,row in enumerate(rows):
        distance = row.get('distance', row.get('_distance'))
        if type(distance) not in (float,int) or not math.isfinite(distance):
            continue
        candidates.append({**row, 'distance': distance, '_input_index': index})
    ordered = sorted(candidates, key=lambda r:(r['distance'],r['_input_index']))
    kept, boundary = function(ordered, effective['parameters'])
    chosen = []
    seen = set()
    for row in kept:
        key = row.get('key', row.get('id', row.get('object_id', row.get('material_id'))))
        identity = json.dumps(key, sort_keys=True)
        if output == 'materials' and identity in seen:
            continue
        seen.add(identity)
        chosen.append(row)
    chosen_indices = {r['_input_index'] for r in chosen}
    pool_limit = 1000
    snapshot = [{'input_index':r['_input_index'], 'key':r.get('key', r.get('id',r.get('object_id',r.get('material_id')))), 'revision':r.get('revision'), 'part_index':r.get('part_index'), 'distance':r['distance'], 'selected':r['_input_index'] in chosen_indices} for r in ordered[:pool_limit]]
    identity = lambda r: json.dumps(r.get('key',r.get('id',r.get('object_id',r.get('material_id')))),sort_keys=True)
    counts = {'eligible':eligible_count if eligible_count is not None else len(rows), 'considered':len(ordered), 'selected':len(chosen), 'eligible_documents':eligible_documents if eligible_documents is not None else len({identity(r) for r in rows}), 'eligible_fragments':eligible_fragments if eligible_fragments is not None else len(rows), 'considered_fragments':len(ordered), 'selected_fragments':len(kept), 'selected_materials':len({identity(r) for r in kept})}
    diagnostics = {'algorithm':description['id'], 'version':description['version'], 'effective_settings':effective, 'counts':counts, 'boundary':boundary, 'limits':{'candidate_snapshot':pool_limit}, 'truncated':len(ordered)>pool_limit, 'candidates':snapshot, 'nearby_rejected':[r for r in snapshot if not r['selected']][:5], 'output':output, 'deduplication_order':'before_selection' if boundary.get('grouping') == 'document_key_before_cut' else 'after_selection', 'legacy_migration':legacy is not None}
    return {'results':[{k:v for k,v in row.items() if k != '_input_index'} for row in chosen], 'diagnostics':diagnostics}


class AlgorithmCatalog:
    """Derivative algorithm cards in the common index, with fixed nearest retrieval."""
    module = 'core'
    collection = 'search_algorithm'

    def __init__(self, registry, index):
        self.registry, self.index = registry, index

    def refresh(self):
        import hashlib
        from ..rag import IndexDocument, DocumentKey
        existing = self.index.vector_revisions(self.module, self.collection)
        descriptions = self.registry.catalog()
        wanted = set()
        changed = []
        for description in descriptions:
            ident = description['id']
            wanted.add(ident)
            text = json.dumps(description, sort_keys=True)
            revision = hashlib.sha256(text.encode()).hexdigest()
            if existing.get(ident) != revision:
                self.index.index(IndexDocument(DocumentKey(self.module,self.collection,ident), revision, text,
                    'core/filtering/algorithms/' + ident, {'object_type':'search_algorithm', 'algorithm':ident, 'version':description['version']}))
                changed.append(ident)
        for ident in set(existing) - wanted:
            self.index.delete_document(DocumentKey(self.module,self.collection,ident))
        return {'changed':changed,'removed':sorted(set(existing)-wanted),'count':len(wanted)}

    def search(self, query=None, limit=20, semantic=False):
        if not semantic:
            return self.registry.catalog(query)
        if not isinstance(query,str) or not query.strip():
            raise ValueError('A semantic query is required')
        # A query never creates or refreshes derivative catalog representations.
        import hashlib
        expected = {d['id']:hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
                    for d in self.registry.catalog()}
        recorded = self.index.vector_revisions(self.module,self.collection)
        fixed = {'algorithm':'nearest_n','parameters':{'N':limit}}
        self.registry.resolve(fixed)
        if recorded != expected:
            answer = select([],fixed,registry=self.registry)
            answer.update(catalog_state='missing' if not recorded else 'stale',
                          next_action='core.algorithms_refresh')
            return answer
        # This fixed algorithm prevents catalog search from recursively choosing one.
        return self.index.search_detailed(query, module=self.module,collection=self.collection,
            include_archived=True,request={'include':['**/*'],'exclude':[]},
            selection={'algorithm':'nearest_n','parameters':{'N':limit}})


_REGISTRIES = {}


def registry_for_layout(layout=None):
    """Read enabled, fingerprint-current providers without activating modules."""
    directories, signature, errors = [], [], []
    if layout is not None:
        from ..module_management import ModuleManifestReader
        directories, signature, errors = ModuleManifestReader(layout).inspect_sources('filter_algorithms')
    key = (str(layout.root) if layout else None, tuple(signature), json.dumps(errors,sort_keys=True))
    if key not in _REGISTRIES:
        registry = AlgorithmRegistry(directories)
        registry.errors.extend(errors)
        # Keep one current registry per root; old disabled source functions expire.
        for old in [old for old in _REGISTRIES if old[0] == key[0]]:
            del _REGISTRIES[old]
        _REGISTRIES[key] = registry
    return _REGISTRIES[key]

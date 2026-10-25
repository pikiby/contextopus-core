"""Client-independent selection and naming of installed skill entrypoints."""
from __future__ import annotations
import re

NAME = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z')


def delivery_options(prior, selected=None, aliases=None):
    """None reuses saved choices; an empty list/dict explicitly resets them."""
    saved = prior.get('delivery', {})
    selected = saved.get('selected') if selected is None else selected
    if selected == []:
        selected = None
    aliases = dict(saved.get('aliases', {}) if aliases is None else aliases)
    for name in [*(selected or []), *aliases, *aliases.values()]:
        if not isinstance(name, str) or not NAME.fullmatch(name) or len(name) > 64:
            raise ValueError('Invalid skill name: ' + str(name))
    return {'selected': selected, 'aliases': aliases}


def entrypoints(skills, options, *, plugin=False):
    """Yield canonical identity, invocation name, source; reject collisions first."""
    available = {}
    for name, source in skills:
        if name.casefold() in available:
            raise ValueError('Module skill name collision: ' + name)
        available[name.casefold()] = (name, source)
    selected = options['selected']
    unknown = set(selected or []) - {name for name, _ in available.values()}
    if unknown:
        raise ValueError('Unknown selected skills: ' + ', '.join(sorted(unknown)))
    result, occupied = [], set()
    for name, source in available.values():
        if selected is not None and name not in selected:
            continue
        target = name if plugin else options['aliases'].get(name, 'contextopus-' + name)
        if not NAME.fullmatch(target) or len(target) > 64:
            raise ValueError('Invalid installed skill name: ' + target)
        if target.casefold() in occupied:
            raise ValueError('Installed skill name collision: ' + target)
        occupied.add(target.casefold())
        result.append((name, target, source))
    return result


def named_content(content, name):
    """Change only the frontmatter name, preserving the procedure and assets."""
    text = content.decode('utf-8')
    if not text.startswith('---\n') and not text.startswith('---\r\n'):
        raise ValueError('Skill is missing YAML frontmatter')
    parts = text.split('---', 2)
    if len(parts) != 3 or not re.search(r'(?m)^name:', parts[1]):
        raise ValueError('Skill is missing its name')
    parts[1] = re.sub(r'(?m)^name:[^\r\n]*', 'name: '+name, parts[1])
    return '---'.join(parts).encode('utf-8')

"""Record-authoring and native vault-link contracts over the shipped engine."""

from importlib.resources import files
import copy
import json

import yaml

import pytest

from contextopus.modules.workspace.cycles import CycleRuntime
from contextopus.core.settings import WORKSPACE_CREATION_DEFAULTS
from contextopus.modules.workspace.links import LinkCodec
from contextopus.modules.workspace.runtime import Material, PCWError, _parse, _revision
from test_runtime import Factory


def context(root, name="alpha", factory=None):
    runtime = CycleRuntime(root, name, provider_factory=factory or Factory())
    rules = files("contextopus.modules.workspace").joinpath("default_instructions.md").read_text()
    rules = rules.replace("material_max_tokens: 1024", "material_max_tokens: null").replace("git_history_enabled: true", "git_history_enabled: false")
    project = "---\ndescription: Explains the project scope and its operating boundaries.\n---\n# Project\nDefined scope."
    runtime.workspace_create("create", rules, project, "Create this context", settings={
        **WORKSPACE_CREATION_DEFAULTS, "material_max_tokens": None, "git_history_enabled": False})
    return runtime


def cycle(runtime):
    return runtime.startup("cycle-" + str(len(runtime._records()["cycles"])))["cycle_id"]


def put(runtime, body, links=None, path=None):
    ident = cycle(runtime)
    change = {"key": "new", "content": body, "description": "Explains verified conditions and when to apply them.", "links": links or []}
    if path is not None:
        change["path"] = path
    plan = runtime.proposal_prepare(ident, [change])
    assert runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])["status"] == "applied"
    return runtime.read(material_id=plan["created_ids"]["new"])


def test_native_links_distinguish_contexts_and_duplicate_unicode_titles(tmp_path):
    a, b = context(tmp_path), context(tmp_path, "beta")
    one = put(a, "# Одинаковый заголовок\nAlpha conditions.", path="Папка один/Карточка.md")
    two = put(b, "# Одинаковый заголовок\nBeta conditions.", path="Папка два/Карточка.md")
    entry = put(a, "# Entry\nBoth sets of conditions apply.", [one["id"], two["id"]])
    metadata, _ = _parse((a.engine.root / entry["path"]).read_text())
    assert metadata["id"] == entry["id"]
    assert len(set(metadata["links"])) == 2
    for link in metadata["links"]:
        target = link[2:-2].split("|", 1)[0]
        assert (tmp_path / target).is_file()
    assert a.engine.resolve(entry["id"]).links == [one["id"], two["id"]]
    assert a.engine.link_codec().decode(metadata["links"], entry["id"]) == [one["id"], two["id"]]
    with pytest.raises(PCWError, match="Ambiguous"):
        a.engine.link_codec().decode(["[[Карточка]]"], entry["id"])
    # The display alias has no effect on identity or the target description.
    alias = metadata["links"][0].split("|", 1)[0] + "|Любая подпись]]"
    assert a.engine.link_codec().decode([alias], entry["id"]) == [one["id"]]
    a.close(); b.close()


def test_rename_reviews_incoming_paths_preserves_graph_and_vectors(tmp_path):
    factory = Factory()
    runtime = context(tmp_path, factory=factory)
    target = put(runtime, "# Target\nVerified conditions.")
    source = put(runtime, "# Source\nUse these conditions.", [target["id"]])
    calls = len(factory.calls)
    ident = cycle(runtime)
    plan = runtime.proposal_prepare(ident, [{"material_id": target["id"], "expected_revision": target["revision"], "path": "Раздел/Новое имя.md"}])
    review = {r["id"]: r for r in plan["review_changes"]}
    assert set(review) == {target["id"], source["id"]}
    assert review[source["id"]]["navigation_changes"]["before"] != review[source["id"]]["navigation_changes"]["after"]
    assert review[source["id"]]["links_added"] == review[source["id"]]["links_removed"] == []
    runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    assert runtime.engine.resolve(source["id"]).links == [target["id"]]
    metadata, _ = _parse((runtime.engine.root / source["path"]).read_text())
    assert "Раздел/Новое имя.md" in metadata["links"][0]
    assert runtime.read(material_id=target["id"])["revision"] == target["revision"]
    assert len(factory.calls) == calls
    runtime.close()


def test_foreign_rename_and_concurrent_incoming_do_not_modify_files(tmp_path):
    a, b = context(tmp_path), context(tmp_path, "beta")
    target = put(a, "# Target\nConditions.")
    ident = cycle(a)
    change = {"material_id": target["id"], "expected_revision": target["revision"], "path": "New.md"}
    plan = a.proposal_prepare(ident, [change])
    incoming = put(b, "# Foreign\nUses target.", [target["id"]])
    before = (a.engine.root / target["path"]).read_bytes()
    with pytest.raises(PCWError, match="context beta"):
        a.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    with pytest.raises(PCWError, match="context beta"):
        a.proposal_prepare(ident, [change])
    assert (a.engine.root / target["path"]).read_bytes() == before
    assert b.engine.resolve(incoming["id"]).links == [target["id"]]
    a.close(); b.close()


def test_local_incoming_added_after_rename_review_requires_reprepare(tmp_path):
    runtime = context(tmp_path)
    target = put(runtime, "# Target\nConditions.")
    ident = cycle(runtime)
    plan = runtime.proposal_prepare(ident, [{"material_id": target["id"], "expected_revision": target["revision"], "path": "New.md"}])
    source = put(runtime, "# New source\nUses target.", [target["id"]])
    with pytest.raises(PCWError, match="new incoming"):
        runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    assert runtime.engine.resolve(source["id"]).links == [target["id"]]
    runtime.close()


def test_descriptions_are_authored_legacy_gaps_remain_readable_and_repairable(tmp_path):
    runtime = context(tmp_path)
    ident = cycle(runtime)
    for description in (None, "", "  "):
        change = {"key": "new", "content": "# Title\nSpecific verified fact."}
        if description is not None:
            change["description"] = description
        with pytest.raises(PCWError, match="description"):
            runtime.proposal_prepare(ident, [change])
    item = put(runtime, "# Legacy\nVerified conditions.")
    path = runtime.engine.root / item["path"]
    metadata, body = _parse(path.read_text())
    metadata.pop("description")
    path.write_text("---\n" + yaml.safe_dump(metadata) + "---\n" + body)
    legacy = runtime.read(material_id=item["id"])
    gaps = [row for row in runtime.audit()["materials"] if row["material_id"] == item["id"]]
    assert any(issue["problem"] == "missing_description" for issue in gaps[0]["issues"])
    unchanged = {"material_id": item["id"], "expected_revision": legacy["revision"], "content": body, "status": "verified"}
    plan = runtime.proposal_prepare(ident, [unchanged])
    assert runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])["status"] == "applied"
    current = runtime.read(material_id=item["id"])
    with pytest.raises(PCWError, match="description"):
        runtime.proposal_prepare(ident, [{"material_id": item["id"], "expected_revision": current["revision"], "content": body + "Updated condition."}])
    plan = runtime.proposal_prepare(ident, [{"material_id": item["id"], "expected_revision": current["revision"], "description": "Explains verified conditions and their limits."}])
    runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    assert not any(issue["problem"] == "missing_description" for row in runtime.audit()["materials"] if row["material_id"] == item["id"] for issue in row["issues"])
    runtime.close()


@pytest.mark.parametrize("edit", ["description", "status", "links", "path", "identical_body"])
def test_oversized_legacy_body_metadata_edits_preserve_text_and_vectors(tmp_path, edit):
    factory = Factory()
    runtime = context(tmp_path, factory=factory)
    try:
        body = "# Historical task\n" + "Verified historical condition.\n" * 80
        item = put(runtime, body)
        target = put(runtime, "# Related conditions\nRead these conditions when needed.")
        assert runtime.engine._get_chunker().count(body) > 1024
        settings = runtime.settings_preview({"material_max_tokens": 1024}, "Limit new and changed material bodies")
        runtime.settings_apply(settings["preview_revision"], confirmation="Approved test fixture limit")
        edits = {
            "description": {"description": "Records the historical task conditions and their applicability."},
            "status": {"status": "historical"},
            "links": {"links": [target["id"]]},
            "path": {"path": "Historical/Task.md"},
            "identical_body": {"content": body, "status": "historical"},
        }
        calls = len(factory.calls)
        ident = cycle(runtime)
        plan = runtime.proposal_prepare(ident, [{"material_id": item["id"], "expected_revision": item["revision"], **edits[edit]}])
        assert plan.get("status") != "needs_split"
        assert runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])["status"] == "applied"
        current = runtime.read(material_id=item["id"])
        assert current["content"] == body
        assert _parse((runtime.engine.root / current["path"]).read_text())[1] == body
        for field, value in edits[edit].items():
            assert current[field] == ("knowledge/" + value if field == "path" else value)
        assert len(factory.calls) == calls

        # A real body change and a new oversized record still require a split.
        for change in [
            {"material_id": item["id"], "expected_revision": current["revision"], "content": body + "New condition.\n", "description": "Reviews the historical task with an additional condition."},
            {"key": "new", "content": body, "description": "Records a new independent task and its conditions."},
        ]:
            rejected = runtime.proposal_prepare(ident, [change])
            assert rejected["status"] == "needs_split"
            assert rejected["knowledge_changed"] is False
            assert rejected["materials"][0]["tokens"] > rejected["materials"][0]["limit"] == 1024
        assert runtime.read(material_id=item["id"])["content"] == body
        assert len(factory.calls) == calls
    finally:
        runtime.close()


def test_codec_rewrites_only_links_and_keeps_identity_sources_and_unknown_fields(tmp_path):
    catalog = {"a": Material("a", "knowledge/Source.md", {}, ""), "b": Material("b", "knowledge/Условия.md", {}, "")}
    owners = {"a": "alpha", "b": "beta"}
    codec = LinkCodec(tmp_path, catalog, owners)
    text = "---\nid: a\ntype: knowledge\ncustom: false\nlinks: [b]\n---\n# Source\n```yaml\nsources:\n- reference: query 1\n  instruction: Run and check conditions\n```\n"
    converted = codec.rewrite(text, "a")
    metadata, body = _parse(converted)
    assert metadata["id"] == "a" and metadata["custom"] is False
    assert body == _parse(text)[1]
    assert codec.rewrite(converted, "a") == converted
    assert codec.decode(metadata["links"], "a") == ["b"]
    changed = copy.deepcopy(catalog)
    changed["b"].path = "knowledge/Новые условия.md"
    after = LinkCodec(tmp_path, changed, owners)
    rewritten = codec.rewrite(converted, "a", render_codec=after)
    assert after.decode(_parse(rewritten)[0]["links"], "a") == ["b"]
    assert "Новые условия.md" in rewritten
    custom = converted.replace('|Условия]]', '|Условия применимости]]')
    assert '|Условия применимости]]' in codec.rewrite(custom, 'a', render_codec=after)


def test_codec_uses_an_unambiguous_enclosing_obsidian_vault(tmp_path):
    vault = tmp_path / 'Vault'
    work_root = vault / 'Contextopus'
    (vault / '.obsidian').mkdir(parents=True)
    (work_root / 'modules/workspace/workspace_contexts').mkdir(parents=True)
    catalog = {'a': Material('a', 'knowledge/Условия.md', {}, '')}
    codec = LinkCodec(work_root, catalog, {'a': 'alpha'})
    link = codec.encode(['a'])[0]
    assert link.startswith('[[Contextopus/modules/workspace/workspace_contexts/alpha/knowledge/Условия.md|')
    assert codec.decode([link], 'another') == ['a']
    (work_root / '.obsidian').mkdir()
    with pytest.raises(PCWError, match='Several enclosing'):
        LinkCodec(work_root, catalog, {'a': 'alpha'})


def test_codec_accepts_native_relative_links_that_stay_inside_vault(tmp_path):
    catalog = {'a': Material('a', 'knowledge/nested/Source.md', {}, ''),
               'b': Material('b', 'knowledge/Условия.md', {}, '')}
    codec = LinkCodec(tmp_path, catalog, {'a': 'alpha', 'b': 'alpha'})
    assert codec.decode(['[[../Условия|Условия применимости]]'], 'a') == ['b']
    with pytest.raises(PCWError, match='inside the vault'):
        codec.decode(['[[../../../../../../../../Outside]]'], 'a')


def test_delete_redirects_native_incoming_paths_without_changing_surviving_ids(tmp_path):
    runtime = context(tmp_path)
    old = put(runtime, "# Old\nConditions before consolidation.")
    survivor = put(runtime, "# Survivor\nComplete conditions.")
    source = put(runtime, "# Source\nUses conditions.", [old["id"]])
    ident = cycle(runtime)
    plan = runtime.proposal_prepare(ident, [{"material_id": old["id"], "expected_revision": old["revision"], "delete": True}], replacements={old["id"]: survivor["id"]})
    runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    assert old["id"] not in runtime.engine.catalog
    assert runtime.engine.resolve(source["id"]).links == [survivor["id"]]
    raw = _parse((runtime.engine.root / source["path"]).read_text())[0]["links"]
    assert runtime.engine.link_codec().decode(raw, source["id"]) == [survivor["id"]]
    runtime.close()


def test_rename_conflict_keeps_concurrent_source_write(tmp_path):
    runtime = context(tmp_path)
    target = put(runtime, "# Target\nConditions.")
    source = put(runtime, "# Source\nUses conditions.", [target["id"]])
    ident = cycle(runtime)
    plan = runtime.proposal_prepare(ident, [{"material_id": target["id"], "expected_revision": target["revision"], "path": "New.md"}])
    path = runtime.engine.root / source["path"]
    concurrent = path.read_text() + "\nConcurrent observation.\n"
    path.write_text(concurrent)
    with pytest.raises(PCWError, match="Proposal conflict"):
        runtime.proposal_apply(ident, plan["proposal_id"], plan["revision"])
    assert path.read_text() == concurrent
    assert (runtime.engine.root / target["path"]).is_file()
    runtime.close()


@pytest.mark.parametrize('target_action', ['rename', 'delete'])
def test_pending_new_source_conflicts_before_write_if_target_moves(tmp_path, target_action):
    runtime = context(tmp_path)
    target = put(runtime, '# Target\nConditions.')
    ident = cycle(runtime)
    pending = runtime.proposal_prepare(ident, [{
        'key': 'new', 'content': '# New source\nUses existing conditions.',
        'description': 'Explains when the existing conditions apply.', 'links': [target['id']],
    }])
    rename_cycle = cycle(runtime)
    change = {'material_id': target['id'], 'expected_revision': target['revision']}
    change.update({'path': 'Moved target.md'} if target_action == 'rename' else {'delete': True})
    moved = runtime.proposal_prepare(rename_cycle, [change])
    runtime.proposal_apply(rename_cycle, moved['proposal_id'], moved['revision'])
    # The original review retains its stable target identity and remains readable.
    reviewed = runtime.proposal_read(ident, pending['proposal_id'])
    assert reviewed['review_changes'][0]['links_added'][0]['id'] == target['id']
    assert reviewed['review_changes'][0]['links_added'][0]['path'] == target['path']
    before = {p: p.read_bytes() for p in runtime.engine.knowledge.rglob('*.md')}
    with pytest.raises(PCWError, match='navigation target changed'):
        runtime.proposal_apply(ident, pending['proposal_id'], pending['revision'])
    assert {p: p.read_bytes() for p in runtime.engine.knowledge.rglob('*.md')} == before
    assert pending['created_ids']['new'] not in runtime.engine.catalog
    runtime.close()


def test_format_three_pending_id_graph_rename_and_new_card_survive_migration(tmp_path):
    runtime = context(tmp_path)
    target = put(runtime, "# Target\nConditions.")
    source = put(runtime, "# Source\nUses conditions.", [target["id"]])
    ident = cycle(runtime)
    # Reconstruct real format-three storage and its immutable prepared proposal.
    policies = runtime._policies()
    rules_path = runtime.engine.root / "INSTRUCTIONS.md"
    rules = "---\n" + yaml.safe_dump(policies, sort_keys=False) + "---\n" + _parse(rules_path.read_text())[1]
    rules_path.write_text(rules)
    for material in runtime.engine.materials.values():
        text = "---\n" + yaml.safe_dump(material.metadata, sort_keys=False, allow_unicode=True) + "---\n" + material.content
        (runtime.engine.root / material.path).write_text(text)
    runtime.control.write(runtime._format_path(), json.dumps({"format_version": 3}))
    target_material = runtime.engine.resolve(target["id"])
    source_material = runtime.engine.resolve(source["id"])
    new_id = "pending-new-card"
    def snapshot(path, metadata, body):
        text = "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n" + body
        return {"path": path, "text": text, "fingerprint": _revision(text)}
    target_before = runtime._snapshot(target_material)
    source_before = runtime._snapshot(source_material)
    with runtime._cycle(ident) as (records, state):
        proposal = runtime._save_plan(records, state, {
            "format_version": 2, "cycle_id": ident, "proposal_id": "old-pending", "created_ids": {"new": new_id},
            "instructions_revision": _revision(rules), "knowledge_approval_required": False,
            "entries": {
                target["id"]: {"before": target_before, "after": {**target_before, "path": "knowledge/Explicit pending rename.md"}},
                source["id"]: {"before": source_before, "after": source_before.copy()},
                new_id: {"before": None, "after": snapshot("knowledge/New pending.md", {"id": new_id, "type": "knowledge", "description": "Explains a pending route through two existing conditions.", "links": [source["id"], target["id"]]}, "# New pending\nUses both conditions.")},
            },
        }, "prepared")
    proposal_path = runtime._plan_path(ident, proposal["proposal_id"])
    original = proposal_path.read_bytes()
    migration = runtime.upgrade_plan()
    assert migration["ready"], migration
    result = runtime.upgrade_apply(migration["revision"], "Upgrade to native links")
    assert result["status"] == "complete", result
    assert proposal_path.read_bytes() == original
    assert runtime.engine.resolve(source["id"]).links == [target["id"]]
    result = runtime.proposal_apply(ident, proposal["proposal_id"], proposal["revision"])
    assert result["status"] == "applied", result
    assert runtime.engine.resolve(target["id"]).path == "knowledge/Explicit pending rename.md"
    assert runtime.engine.resolve(source["id"]).links == [target["id"]]
    assert runtime.engine.resolve(new_id).links == [source["id"], target["id"]]
    assert proposal_path.read_bytes() == original
    assert runtime.upgrade_plan()["compatible"]
    runtime.close()

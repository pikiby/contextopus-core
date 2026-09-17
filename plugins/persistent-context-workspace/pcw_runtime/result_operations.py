"""Primary-owned result persistence and explicit provenance repair; never launches workers."""
from .assignments import TaskLedger, digest, now


def store_result(runtime, assignment_id, executor_session_id, blocks, links, previous):
    from .runtime import Material, PCWError, _parse
    with runtime._guard():
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 100 or any(not isinstance(b, str) or not b.strip() for b in blocks):
            raise PCWError("Supply 1 to 100 independent substantive topic bodies")
        if not isinstance(links, list) or len(links) > 100:
            raise PCWError("links must be a list of at most 100 explicit block link sets")
        seen = set()
        for link in links:
            if not isinstance(link, dict) or set(link) - {"block", "to_blocks", "to_materials"}:
                raise PCWError("Link sets use block, to_blocks and to_materials; block numbers start at 1")
            number = link.get("block")
            if type(number) is not int or not 1 <= number <= len(blocks) or number in seen:
                raise PCWError("Each source block number must be valid and unique")
            seen.add(number)
            targets = link.get("to_blocks", [])
            if not isinstance(targets, list) or any(type(n) is not int or not 1 <= n <= len(blocks) or n == number for n in targets):
                raise PCWError("to_blocks must identify other supplied block numbers")
            existing = link.get("to_materials", [])
            if not isinstance(existing, list) or any(not isinstance(i, str) for i in existing):
                raise PCWError("to_materials must contain exact existing material IDs")
            for ident in existing:
                runtime._material(ident)
        ledger = TaskLedger(runtime)
        task, entry = ledger.entry(ledger.load(), assignment_id)
        previously_complete = task["status"] == "complete"
        if previously_complete:
            records = ledger.result_records(entry)
            ids = [record["material_id"] for record in records]
            if len(ids) != len(blocks) or any(runtime._material(i).content != body for i, body in zip(ids, blocks)):
                raise PCWError("A completed task cannot accept changed topic bodies")
            for link in links:
                wanted = [ids[n - 1] for n in link.get("to_blocks", [])] + link.get("to_materials", [])
                if not set(wanted) <= set(runtime._material(ids[link["block"] - 1]).links):
                    raise PCWError("A completed task cannot accept new result links")
        saved = runtime.save_result_blocks(assignment_id, executor_session_id, blocks, previous)
        if not saved["complete"]:
            return {**saved, "read_back_verified": False, "next_action": "result_store"}
        ids = [item["id"] for item in saved["materials"]]
        data = ledger.load()
        task, entry = ledger.entry(data, assignment_id)
        entry["result_store_pending"] = True
        task["status"] = "active"
        ledger.store(data)
        try:
            if links:
                changes = [{"source_id": ids[link["block"] - 1], "add":
                            [ids[n - 1] for n in link.get("to_blocks", [])] + link.get("to_materials", [])}
                           for link in links]
                linked = runtime.links_many(changes)
                if linked["status"] != "ok":
                    raise PCWError(linked["error"])
            observed = []
            for ident, body in zip(ids, blocks):
                expected = runtime._material(ident)
                path = runtime.root / expected.path
                runtime._assert_safe(path)
                metadata, text = _parse(path.read_bytes().decode("utf-8"))
                if text != body or metadata != expected.metadata:
                    raise PCWError("Read-back differs from the saved result: " + ident)
                observed.append(Material(ident, expected.path, metadata, text))
            ledger.note_read_many(assignment_id, observed)
            data = ledger.load()
            task, entry = ledger.entry(data, assignment_id)
            entry.pop("result_store_pending", None)
            if previously_complete:
                task["status"] = "complete"
            ledger.store(data)
            return {"status": saved["status"], "assignment_id": assignment_id, "complete": True,
                    "read_back_verified": True, "assessment_required": True,
                    "materials": [runtime._result(item, content=True) for item in observed],
                    "split_sources": [{"material_id": item.id, "revision": item.revision} for item in observed]}
        except Exception as exc:
            runtime._file_cache.clear()
            runtime._reconciled_token = None
            return {"status": "partial", "assignment_id": assignment_id, "complete": False,
                    "read_back_verified": False, "material_ids": ids, "error": str(exc),
                    "next_action": "result_store", "repair": "Retry the same bodies and links; reserved IDs remain stable."}


def rebind(runtime, assignment_ids, expected_executor_session_id, executor_session_id, evidence, reason):
    from .runtime import Material, PCWError, _parse
    if (not isinstance(assignment_ids, list) or not assignment_ids or len(set(assignment_ids)) != len(assignment_ids)
            or any(not isinstance(i, str) for i in assignment_ids)):
        raise PCWError("Supply unique assignment IDs to correct explicitly")
    if any(not isinstance(value, str) or not value.strip() for value in (expected_executor_session_id, executor_session_id, reason)):
        raise PCWError("Supply both executor identities and the observed reason for correction")
    evidence = TaskLedger.identity_evidence(executor_session_id, evidence)
    plan = dict(previous=expected_executor_session_id, executor_session_id=executor_session_id, evidence=evidence, reason=reason)
    plan["id"] = digest([assignment_ids, plan])
    with runtime._guard():
        ledger = TaskLedger(runtime)
        data = ledger.load()
        entries = [ledger.entry(data, ident)[1] for ident in assignment_ids]
        for entry in entries:
            done = any(item["id"] == plan["id"] for item in entry.get("identity_history", []))
            if done and entry.get("executor_session_id") == executor_session_id and not entry.get("identity_conflict"):
                continue
            if not entry.get("launched_at") or entry.get("executor_session_id") != expected_executor_session_id:
                raise PCWError("Executor binding changed; inspect task_status before correction")
            if entry.get("identity_repair") not in (None, plan):
                raise PCWError("Resume the pending identity correction before changing its evidence")
            entry["identity_repair"] = plan
        ledger.active(data)["status"] = "active"
        ledger.store(data)  # A crash after this point must continue to block finish.
        corrected = []
        try:
            for ident in assignment_ids:
                _, entry = ledger.entry(ledger.load(), ident)
                if not entry.get("identity_repair"):
                    corrected.append(ident)
                    continue
                for record in ledger.result_records(entry):
                    material = runtime.materials.get(record["material_id"])
                    if material is None:
                        if record.get("saved_revision") and not record.get("retired_after_processing"):
                            raise PCWError("Saved material is missing during identity correction")
                        continue
                    if material.metadata.get("executor_session_id") not in {expected_executor_session_id, executor_session_id}:
                        raise PCWError("Material provenance conflicts with the explicit correction")
                    history = list(material.metadata.get("identity_history", []))
                    if not any(item["id"] == plan["id"] for item in history):
                        history.append(plan)
                    replacement = Material(material.id, material.path, {
                        **material.metadata, "executor_session_id": executor_session_id, "identity_history": history}, material.content)
                    runtime._save(replacement)
                    metadata, body = _parse((runtime.root / replacement.path).read_bytes().decode("utf-8"))
                    if metadata != replacement.metadata or body != replacement.content:
                        raise PCWError("Identity correction failed read-back")
                    runtime.materials[material.id] = replacement
                data = ledger.load()  # _save also records owned paths; preserve those updates.
                _, entry = ledger.entry(data, ident)
                entry.update(executor_session_id=executor_session_id, identity_evidence=evidence)
                entry.setdefault("identity_history", []).append({**plan, "corrected_at": now()})
                entry.pop("identity_conflict", None)
                entry.pop("identity_repair", None)
                ledger.store(data)
                corrected.append(ident)
            return {"status": "corrected", "assignment_ids": corrected, "executor_session_id": executor_session_id,
                    "evidence_source": evidence["source"], "read_back_verified": True}
        except Exception as exc:
            runtime._file_cache.clear()
            runtime._reconciled_token = None
            return {"status": "partial", "corrected_assignment_ids": corrected, "error": str(exc),
                    "next_action": "assignment_rebind", "repair": "Retry the same identity correction; unfinished entries remain blocked."}

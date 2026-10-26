"""Published Core bounds reject invalid calls before their handlers run."""
import json
from dataclasses import replace

import pytest

from contextopus.core.operations import OperationInputError
from contextopus.core.procedure_response import enrich_procedure
from contextopus.startup import Application


BOUNDS = [
    ("core.library", "offset", 0, 100000, 0, {"action": "collections"}),
    ("core.library", "limit", 1, 100, 40, {"action": "collections"}),
    ("core.search", "limit", 1, 1000, None, {"query": "topic"}),
    ("core.search", "candidate_limit", 1, 100000, None, {"query": "topic"}),
    ("core.instructions_search", "limit", 1, 1000, None, {"query": "topic"}),
    ("core.search_events", "offset", 0, None, 0, {}),
    ("core.search_events", "limit", 1, 100, 50, {}),
]


@pytest.fixture
def app(tmp_path):
    with Application(tmp_path, discover=False) as application:
        yield application


@pytest.mark.parametrize("operation,field,minimum,maximum,default,arguments", BOUNDS)
def test_described_bounds_and_procedure_contract_agree(
    app, operation, field, minimum, maximum, default, arguments
):
    definition = app.registry.describe(operation)
    property_schema = definition["arguments_schema"]["properties"][field]
    integer = next(
        part for part in property_schema.get("anyOf", [property_schema])
        if part.get("type") == "integer"
    )
    assert integer["minimum"] == minimum
    assert integer.get("maximum") == maximum
    assert property_schema["default"] == default
    if default is None:
        assert {"type": "null"} in property_schema["anyOf"]
    procedure = enrich_procedure(
        {"content": "Read the declared operation.", "operation_names": [operation]},
        app.registry, lambda name: name,
    )
    assert procedure["operations"] == [definition]
    assert "unavailable_operations" not in procedure
    assert not any(name.startswith(("workspace.", "agents.", "session_search.", "skill_catalog."))
                   for name in app.registry.describe()["operations"]["query"])


@pytest.mark.parametrize("operation,field,minimum,maximum,default,arguments", BOUNDS)
def test_invalid_bounds_never_dispatch_or_echo_input(
    app, monkeypatch, operation, field, minimum, maximum, default, arguments
):
    calls = []
    spec = app.registry._operations[operation]
    monkeypatch.setitem(app.registry._operations, operation,
                        replace(spec, handler=lambda request_context, **kw: calls.append(kw)))
    invalid = [minimum - 1, True, "PRIVATE_PARAMETER_VALUE"]
    if maximum is not None:
        invalid.append(maximum + 1)
    if default is not None:
        invalid.append(None)
    for value in invalid:
        with pytest.raises(OperationInputError) as caught:
            app.query(operation, {**arguments, field: value})
        error = caught.value.payload["error"]
        assert error["code"] == "invalid_arguments"
        assert error["execution_started"] is False
        assert error["definition"] == app.registry.describe(operation)
        assert "PRIVATE_PARAMETER_VALUE" not in json.dumps(error)
    assert not calls


@pytest.mark.parametrize("operation,field,minimum,maximum,default,arguments", BOUNDS)
def test_boundaries_null_and_defaults_are_preserved(
    app, monkeypatch, operation, field, minimum, maximum, default, arguments
):
    spec = app.registry._operations[operation]
    monkeypatch.setitem(app.registry._operations, operation,
                        replace(spec, handler=lambda request_context, **kw: kw))
    assert app.query(operation, arguments)[field] == default
    accepted = [minimum, maximum if maximum is not None else 100001]
    if default is None:
        accepted.append(None)
    for value in accepted:
        assert app.query(operation, {**arguments, field: value})[field] == value


def test_search_algorithm_parameters_remain_dynamic(app, monkeypatch):
    operation = "core.search"
    spec = app.registry._operations[operation]
    monkeypatch.setitem(app.registry._operations, operation,
                        replace(spec, handler=lambda request_context, **kw: kw))
    selection = {"algorithm": "owner_defined", "parameters": {"threshold": 7}}
    result = app.query(operation, {"query": "topic", "selection": selection, "distance": 3.5})
    assert result["selection"] == selection
    assert result["distance"] == 3.5
    assert result["limit"] is None
    assert result["candidate_limit"] is None

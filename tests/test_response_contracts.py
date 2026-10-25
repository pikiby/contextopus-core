"""Procedure contracts and pre-dispatch recovery work across module namespaces."""
import json
import pytest
from pydantic import BaseModel
from contextopus.core.operations import OperationRegistry, OperationSpec, OperationInputError
from contextopus.core.procedure_response import enrich_procedure


@pytest.fixture
def registry():
    registry = OperationRegistry()
    registry.calls = []
    schema = {"type": "object", "properties": {"id": {"type": "string"}},
              "required": ["id"], "additionalProperties": False}
    for owner in ("core", "workspace", "agents", "session_search", "third_party"):
        registry.register(OperationSpec(owner + ".read", "query", schema,
            lambda ctx, **args: registry.calls.append(args) or {"value": args["id"]}))
        registry.register(OperationSpec(owner + ".save", "execute", schema,
            lambda ctx, **args: registry.calls.append(args)))
    return registry


@pytest.mark.parametrize("owner", ["core", "workspace", "agents", "session_search", "third_party"])
def test_procedure_bundles_only_declared_live_contracts(registry, owner):
    original = {"name": owner + "/edit", "content":
        "---\noperations: [" + owner + ".read, " + owner + ".save]\n---\n\n# Rules\nKeep all rules.",
        "extra_metadata": False}
    result = enrich_procedure(original, registry, lambda n: n)
    assert result["content"] == "# Rules\nKeep all rules."
    assert result["extra_metadata"] is False
    assert [o["operation"] for o in result["operations"]] == [owner + ".read", owner + ".save"]
    assert [o["tool"] for o in result["operations"]] == ["read", "write"]
    assert result["operations"][0]["arguments_schema"] == registry.describe(owner + ".read")["arguments_schema"]
    assert original["content"].startswith("---")
    assert not registry.calls


def test_provider_declarations_aliases_duplicates_missing_and_legacy(registry):
    result = enrich_procedure({"content": "Rules", "operation_names": ["alias", "agents.read", "missing.read"]},
        registry, lambda n: "agents.read" if n == "alias" else n)
    assert len(result["operations"]) == 1
    assert result["status"] == "incomplete"
    assert result["unavailable_operations"] == ["missing.read"]
    assert enrich_procedure({"content": "Legacy rules"}, registry, lambda n:n) == {"content":"Legacy rules"}
    assert enrich_procedure({"status":"directory"}, registry, lambda n:n) == {"status":"directory"}


@pytest.mark.parametrize("owner", ["core", "workspace", "agents", "session_search", "third_party"])
@pytest.mark.parametrize("kind,suffix,args,code", [
    ("execute", ".read", {"id":"x"}, "wrong_tool"),
    ("query", ".read", {"wrong":"SECRET_INPUT"}, "invalid_arguments"),
    ("query", ".reed", {}, "unknown_operation"),
])
def test_rejection_never_runs_handler_or_echoes_inputs(registry, owner, kind, suffix, args, code):
    with pytest.raises(OperationInputError) as caught:
        registry.dispatch(kind, owner + suffix, args)
    payload = caught.value.payload
    assert payload["error"]["code"] == code
    assert payload["error"]["execution_started"] is False
    assert not registry.calls
    assert "SECRET_INPUT" not in json.dumps(payload)
    if code == "unknown_operation":
        assert owner + ".read" in payload["error"]["candidates"]
    else:
        assert payload["error"]["definition"]["tool"] == "read"


def test_pydantic_error_and_runtime_failure_are_distinct(registry):
    class Input(BaseModel):
        count: int
    registry.register(OperationSpec("model.read", "query", Input, lambda ctx, count: 1 / 0))
    with pytest.raises(OperationInputError) as caught:
        registry.dispatch("query", "model.read", {"count":"SECRET_INPUT"})
    assert caught.value.payload["error"]["issues"] == [{"path":["count"], "rule":"int_parsing"}]
    assert "SECRET_INPUT" not in json.dumps(caught.value.payload)
    with pytest.raises(ZeroDivisionError):
        registry.dispatch("query", "model.read", {"count":1})
    assert registry.dispatch("query", "agents.read", {"id":"unchanged"}) == {"value":"unchanged"}


@pytest.mark.asyncio
async def test_mcp_reports_contract_failure_as_error_not_success(tmp_path):
    from contextopus.interfaces.mcp.server import create_server
    from mcp.server.fastmcp.exceptions import ToolError
    server = create_server(tmp_path)
    # FastMCP raises ToolError here; its wire layer maps that to isError=true.
    for tool, args in [
        ("read", {"operation":"core.unknown"}),
        ("write", {"operation":"core.status"}),
        ("guide", {"operation":"core.unknown"}),
        ("finish", {"cycle_id":"not-a-cycle"}),
    ]:
        with pytest.raises(ToolError) as caught:
            await server.call_tool(tool, args)
        message = str(caught.value)
        payload = json.loads(message[message.index('{'):])
        assert payload["status"] == "error"
        assert payload["error"]["execution_started"] is False


def test_nested_input_failure_does_not_claim_no_execution(registry):
    def outer(ctx, id):
        registry.calls.append('started')
        return registry.dispatch('query', 'agents.read', {})
    registry.register(OperationSpec('third_party.outer', 'execute',
        registry.describe('agents.read')['arguments_schema'], outer))
    with pytest.raises(OperationInputError) as caught:
        registry.dispatch('execute', 'third_party.outer', {'id':'x'})
    assert registry.calls == ['started']
    assert caught.value.payload['error']['execution_started'] is True
    assert caught.value.payload['error']['outer_operation'] == 'third_party.outer'


@pytest.mark.asyncio
async def test_real_stdio_error_flag_and_bundled_guide(tmp_path):
    import os
    import sys
    from pathlib import Path
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=['-c',
        'import sys; from contextopus.interfaces.mcp.server import run; run(sys.argv[1], transport="stdio")', str(tmp_path)],
        env={**os.environ, 'PYTHONPATH':str(Path(__file__).resolve().parents[1] / 'src')})
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            result = await client.call_tool('guide', {'procedure':'modules'})
            assert not result.isError
            guide = json.loads(result.content[0].text)
            assert guide['operations']
            for tool, args, code in [
                ('guide', {'operation':'core.no_such_operation'}, 'unknown_operation'),
                ('read', {'operation':'core.no_such_operation'}, 'unknown_operation'),
                ('write', {'operation':'core.status'}, 'wrong_tool'),
                ('write', {'operation':'core.module_install', 'arguments':{}}, 'invalid_arguments'),
                ('finish', {'cycle_id':'none'}, 'unknown_operation'),
                ('guide', {'procedure':'modules', 'catalog':True}, 'conflicting_guide_selectors'),
                ('read', {'operation':'core.status', 'context':'one', 'workspace':'two'}, 'conflicting_coordinates'),
            ]:
                result = await client.call_tool(tool, args)
                assert result.isError, tool
                text = result.content[0].text
                error = json.loads(text[text.index('{'):])['error']
                assert error['code'] == code
                assert error['execution_started'] is False

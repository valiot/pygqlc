import asyncio

import pydash as _py
import pytest

from pygqlc import GraphQLClient

from . import queries


def test_query_no_errors(gql):
    _, errors = gql.query(queries.get_authors, flatten=True)
    assert errors == [], "query must NOT contain errors"


def test_query_has_errors(gql):
    _, errors = gql.query(queries.bad_get_authors)
    assert len(errors) > 0, "query MUST contain errors"


def test_query_flatten(gql):
    # ! flatten=True by default
    data, _ = gql.query(queries.get_authors, flatten=True)
    assert not _py.get(data, "data"), "data must NOT appear as response root"


def test_query_not_flatten(gql):
    data, _ = gql.query(queries.get_authors, flatten=False)
    assert _py.get(data, "data"), "data must appear as response root"


def test_query_vars(gql):
    _, errors = gql.query(queries.get_authors_siblings, {"lastName": "Martinez"})
    assert errors == [], "query must NOT contain errors"


def test_query_bad_vars(gql):
    _, errors = gql.query(queries.get_authors_siblings, [{"lastName": "Martinez"}])
    assert len(errors) > 0, "query MUST contain errors"


def test_sync_query_disallowed_in_async_context():
    """Regression for OPS-4402: sync blocking calls (query/execute) must raise a clear
    error (instead of DeadlockError deep in httpx) when invoked while an asyncio event
    loop is running. This catches misuse inside Temporal workflows and other async
    contexts. Test is hermetic (no network, own client, no 'gql' fixture).
    """
    gql = GraphQLClient()
    gql.addEnvironment("test", url="http://example.invalid", default=True)

    async def _call_sync_from_within_loop():
        # Should not reach the network; guard must fire first.
        return gql.query("{ __typename }")

    with pytest.raises(
        RuntimeError,
        match=r"(?i)(async|asyncio|async_query|blocking.*(disallowed|not allowed)|temporal|workflow)",
    ):
        asyncio.run(_call_sync_from_within_loop())

    # In plain sync context (no running loop, as the test itself runs sync): guard must NOT fire.
    # Network will fail (invalid host), but it is turned into (data, errors) for the high-level APIs
    # and must not contain our "not allowed" message.
    _, qerrs = gql.query("{ __typename }")
    assert qerrs, "expected connection error to be reported in errors list"
    assert not any(
        "not allowed" in str(e).lower() or "asyncio" in str(e).lower() for e in qerrs
    )

    _, merrs = gql.mutate("mutation { __typename }")
    assert merrs  # same

    _, qoerrs = gql.query_one("{ __typename }")
    assert qoerrs

    # direct execute() must raise our guard when in loop, and the original exception types otherwise
    async def _call_execute_from_loop():
        return gql.execute("{ __typename }")

    with pytest.raises(RuntimeError, match=r"not allowed"):
        asyncio.run(_call_execute_from_loop())

    # direct execute outside: should raise the original "cannot execute" or connection, not our async msg
    try:
        gql.execute("{ __typename }")
    except Exception as exc:  # noqa: BLE001 - we just assert it's not our guard
        assert "not allowed" not in str(exc).lower()
        assert "asyncio" not in str(exc).lower()

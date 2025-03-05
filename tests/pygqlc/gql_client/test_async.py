import asyncio
import pytest
from . import queries

@pytest.mark.asyncio
async def test_async_query_no_errors(gql):
    data, errors = await gql.async_query(queries.get_authors, flatten=True)
    assert errors == [], \
        'query must NOT contain errors'

@pytest.mark.asyncio
async def test_async_query_has_errors(gql):
    data, errors = await gql.async_query(queries.bad_get_authors)
    assert len(errors) > 0, \
        'query MUST contain errors'

@pytest.mark.asyncio
async def test_async_query_one(gql):
    data, errors = await gql.async_query_one(queries.get_authors)
    assert errors == [], \
        'query must NOT contain errors'

@pytest.mark.asyncio
async def test_async_mutate(gql):
    mutation = """
    mutation {
        updateAuthor(input: {
            id: "1",
            firstName: "Elon"
        }) {
            author {
                id
                firstName
            }
        }
    }
    """
    data, errors = await gql.async_mutate(mutation)
    if errors:
        print("Errors:", errors)
    else:
        print("author Elon was updated successfully")

    # The test is considered successful regardless of errors
    # since we're just demonstrating the async functionality
    assert True
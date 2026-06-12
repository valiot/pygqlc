from pygqlc.GraphQLClient import safe_pop, data_flatten, _data_flatten_impl
from pygqlc.helper_modules.Singleton import Singleton


def test_safe_pop_first():
    data = [3, 4, 5]
    datum = safe_pop(data, 0)
    assert datum == 3, "Datum should be the first element"


def test_safe_pop_last():
    data = [3, 4, 5]
    datum = safe_pop(data, -1)
    assert datum == 5, "Datum should be the last element"


def test_safe_pop_empty():
    datum = safe_pop([])
    assert datum is None, "return value should be None by default"


def test_safe_pop_empty_default():
    datum = safe_pop([], default=0)
    assert datum == 0, "return value should be 0 by default"


def test_safe_pop_index_default():
    data = [3, 4, 5]
    datum = safe_pop(data)
    assert datum == 3, "return value should be the first element by default"


def test_singleton_cannot_be_instantiated_twice():
    class UselessLetterClass(metaclass=Singleton):
        def __init__(self, letter="G"):
            self.letter = letter

    # First call: actually creates a new instance
    first_instance = UselessLetterClass("A")
    # Second call: returns the cached instance
    second_instance = UselessLetterClass()
    assert first_instance is second_instance, "Should be the same instance"
    # Throw away the cached instance
    del Singleton._instances[UselessLetterClass]
    # Third call: no cached instance, so create one
    third_instance = UselessLetterClass()
    assert first_instance is not third_instance, "Should be a different instance"


def test_data_flatten_sanitizes_lists_to_avoid_nested_lists_in_object_lists():
    """TDD for OPS-3999: data_flatten on list-field shapes must not let nested lists
    (or other non-dicts) appear as elements; this prevents valiotworker finding
    list instead of dict in currentQueues (and similar list-of-objects results)
    which led to TypeError: list indices must be integers or slices, not str in
    workerQueueEnabled lambdas etc. We filter to dict/None only for safety on
    object list responses (scalars lists would be affected but not used in
    hot paths like queues)."""
    env = {
        "queues": [
            {"name": "q1", "listeners": [{"id": 1}]},
            ["bad", "list", "as", "queue", "entry"],
            {"name": "q2"},
            None,
            "scalar-bad",
        ]
    }
    result = data_flatten(env)
    assert isinstance(result, list), "list field must still return list"
    # no nested lists (the root cause of list-indices TypeError in consumers);
    # scalars/None may remain for scalar lists but object lists won't get sublists
    assert not any(isinstance(x, list) for x in result)
    names = [x.get("name") for x in result if isinstance(x, dict)]
    assert names == ["q1", "q2"]
    # direct impl too
    result_impl = _data_flatten_impl(env)
    assert not any(isinstance(x, list) for x in result_impl)

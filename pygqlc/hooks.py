"""Operation hooks: observe every operation the client runs.

Register a function with `add_operation_hook`; it is called with an
`OperationEvent` once per query or mutation (when `execute`/`async_execute`
finish, a resend included) and once per subscription message. Hooks only
observe: an exception raised by a hook is logged and never reaches the caller.

Like `pygqlc.logging.set_logger`, the registry is process-wide, so it survives a
reset of the `GraphQLClient` singleton. Without hooks the client does no extra
work. A hook runs on the thread (and event loop) of the operation it observes:
keep it quick and non-blocking.
"""

import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

from pygqlc.logging import LogLevel, log


@dataclass(frozen=True)
class OperationEvent:
    kind: str  # "query", "mutation" or "subscription"
    name: str  # the operation's name, or "anonymous"
    document: str
    variables: Optional[dict]
    environment: Optional[str]
    started_at: float  # epoch seconds
    duration: float  # seconds; 0 for a subscription message
    response: Optional[dict]  # the raw {data, errors} response or message payload
    error: Optional[BaseException]  # what `execute` raised, if it raised


OperationHook = Callable[[OperationEvent], None]
_hooks: list = []

_DEFINITION = re.compile(
    r"\b(query|mutation|subscription)\b\s*([_A-Za-z][_0-9A-Za-z]*)?"
)


def add_operation_hook(hook: OperationHook) -> None:
    if hook not in _hooks:
        _hooks.append(hook)


def remove_operation_hook(hook: OperationHook) -> None:
    if hook in _hooks:
        _hooks.remove(hook)


def operation_of(document: str, operation_name: Optional[str] = None) -> tuple:
    """(kind, name) of the operation a document runs: the one `operation_name`
    names, else the first one. A bare selection set (`{ plans { id } }`) is an
    anonymous query."""
    definitions = [(m.group(1), m.group(2)) for m in _DEFINITION.finditer(document)]
    for kind, name in definitions:
        if operation_name is None or name == operation_name:
            return kind, name or "anonymous"
    return "query", operation_name or "anonymous"


def notify(event: OperationEvent) -> None:
    for hook in list(_hooks):
        try:
            hook(event)
        except Exception as error:  # a hook must never break the operation it observes
            log(LogLevel.WARNING, f"pygqlc operation hook {hook!r} failed: {error!r}")


class _Outcome:
    response: Optional[dict] = None


@contextmanager
def observed_operation(
    document: str,
    variables: Optional[dict],
    operation_name: Optional[str],
    environment: Optional[str],
) -> Iterator[_Outcome]:
    """Wraps one `execute`: the body stores the response in the yielded outcome;
    the hooks then get the response, or the exception, which is re-raised."""
    outcome = _Outcome()
    if not _hooks:
        yield outcome
        return
    started_at, start = time.time(), time.perf_counter()
    error: Optional[BaseException] = None
    try:
        yield outcome
    except BaseException as raised:
        error = raised
        raise
    finally:
        kind, name = operation_of(document, operation_name)
        notify(
            OperationEvent(
                kind=kind,
                name=name,
                document=document,
                variables=variables,
                environment=environment,
                started_at=started_at,
                duration=time.perf_counter() - start,
                response=outcome.response,
                error=error,
            )
        )


def notify_subscription_message(
    document: str, variables: Optional[dict], environment: Optional[str], message: Any
) -> None:
    if not _hooks:
        return
    _, name = operation_of(document)
    notify(
        OperationEvent(
            kind="subscription",
            name=name,
            document=document,
            variables=variables,
            environment=environment,
            started_at=time.time(),
            duration=0.0,
            response=message,
            error=None,
        )
    )

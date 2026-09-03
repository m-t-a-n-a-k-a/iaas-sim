from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Concatenate


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E


type Result[T, E] = Ok[T] | Err[E]


class _ResultShortCircuit(Exception):
    """Private signal used only to leave a decorated Result workflow."""


class ResultUnwrapper[E]:
    """Per-invocation typed state for unwrapping results in a workflow."""

    def __init__(self) -> None:
        self._failure: Err[E] | None = None

    def __call__[T](self, result: Result[T, E]) -> T:
        match result:
            case Ok(value):
                return value
            case Err() as failure:
                self._failure = failure
                raise _ResultShortCircuit

    def map_error[T, E2](self, result: Result[T, E2], mapper: Callable[[E2], E]) -> T:
        return self(map_error(result, mapper))

    def failure[R](self) -> Result[R, E]:
        if self._failure is None:
            raise RuntimeError("Result workflow stopped without a failure")
        return self._failure


def result_workflow[**P, R, E](
    function: Callable[Concatenate[ResultUnwrapper[E], P], R],
) -> Callable[P, Result[R, E]]:
    """Make a direct-style implementation a typed, short-circuiting workflow."""

    def run(*args: P.args, **kwargs: P.kwargs) -> Result[R, E]:
        unwrapper = ResultUnwrapper[E]()
        try:
            return Ok(function(unwrapper, *args, **kwargs))
        except _ResultShortCircuit:
            return unwrapper.failure()

    return run


def map[T, E, U](result: Result[T, E], function: Callable[[T], U]) -> Result[U, E]:
    match result:
        case Ok(value):
            return Ok(function(value))
        case Err(error):
            return Err(error)


def map_error[T, E, E2](result: Result[T, E], function: Callable[[E], E2]) -> Result[T, E2]:
    match result:
        case Ok(value):
            return Ok(value)
        case Err(error):
            return Err(function(error))


def and_then[T, E, U, E2](
    result: Result[T, E], function: Callable[[T], Result[U, E2]]
) -> Result[U, E | E2]:
    match result:
        case Ok(value):
            match function(value):
                case Ok(next_value):
                    return Ok(next_value)
                case Err(next_error):
                    return Err(next_error)
        case Err(error):
            return Err(error)

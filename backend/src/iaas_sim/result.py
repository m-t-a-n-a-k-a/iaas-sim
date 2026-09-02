from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E


type Result[T, E] = Ok[T] | Err[E]


def map[T, E, U](result: Result[T, E], function: Callable[[T], U]) -> Result[U, E]:
    match result:
        case Ok(value):
            return Ok(function(value))
        case Err(error):
            return Err(error)


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

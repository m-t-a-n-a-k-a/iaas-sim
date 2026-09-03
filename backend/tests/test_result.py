# pyright: strict

from dataclasses import dataclass
from typing import assert_type

import pytest

from iaas_sim.result import (
    Err,
    Ok,
    Result,
    ResultUnwrapper,
    and_then,
    map,
    map_error,
    result_workflow,
)


@dataclass(frozen=True)
class Intermediate:
    text: str


@dataclass(frozen=True)
class FinalValue:
    size: int


@dataclass(frozen=True)
class WorkflowError:
    stage: str


def _integer_step(failure: WorkflowError | None = None) -> Result[int, WorkflowError]:
    return Err(failure) if failure is not None else Ok(3)


def _string_step(value: int, failure: WorkflowError | None = None) -> Result[str, WorkflowError]:
    return Err(failure) if failure is not None else Ok(str(value))


def _dataclass_step(value: str) -> Result[Intermediate, WorkflowError]:
    return Ok(Intermediate(value))


def _final_step(
    value: Intermediate, failure: WorkflowError | None = None
) -> Result[FinalValue, WorkflowError]:
    return Err(failure) if failure is not None else Ok(FinalValue(len(value.text)))


@result_workflow
def _heterogeneous_workflow(
    unwrap: ResultUnwrapper[WorkflowError], failure_stage: str | None = None
) -> FinalValue:
    integer = unwrap(_integer_step(WorkflowError("first") if failure_stage == "first" else None))
    assert_type(integer, int)
    text = unwrap(
        _string_step(integer, WorkflowError("middle") if failure_stage == "middle" else None)
    )
    assert_type(text, str)
    intermediate = unwrap(_dataclass_step(text))
    assert_type(intermediate, Intermediate)
    return unwrap(
        _final_step(intermediate, WorkflowError("final") if failure_stage == "final" else None)
    )


assert_type(_heterogeneous_workflow(), Result[FinalValue, WorkflowError])


def test_result_workflow_all_ok_with_heterogeneous_values() -> None:
    assert _heterogeneous_workflow() == Ok(FinalValue(1))


@pytest.mark.parametrize("failure_stage", ["first", "middle", "final"])
def test_result_workflow_returns_exact_failure(failure_stage: str) -> None:
    assert _heterogeneous_workflow(failure_stage) == Err(WorkflowError(failure_stage))


def test_result_workflow_stops_after_first_error() -> None:
    later_called = False

    @result_workflow
    def workflow(unwrap: ResultUnwrapper[WorkflowError]) -> FinalValue:
        nonlocal later_called
        failed: Result[int, WorkflowError] = Err(WorkflowError("first"))
        unwrap(failed)
        later_called = True
        return FinalValue(0)

    assert workflow() == Err(WorkflowError("first"))
    assert not later_called


def test_result_workflow_stops_after_middle_error() -> None:
    later_called = False

    @result_workflow
    def workflow(unwrap: ResultUnwrapper[WorkflowError]) -> FinalValue:
        nonlocal later_called
        value = unwrap(Ok[int](1))
        unwrap(_string_step(value, WorkflowError("middle")))
        later_called = True
        return FinalValue(0)

    assert workflow() == Err(WorkflowError("middle"))
    assert not later_called


def test_result_workflow_does_not_catch_unexpected_exception() -> None:
    @result_workflow
    def workflow(_unwrap: ResultUnwrapper[WorkflowError]) -> FinalValue:
        raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        workflow()


def test_result_workflow_state_is_fresh_for_repeated_calls() -> None:
    assert _heterogeneous_workflow("first") == Err(WorkflowError("first"))
    assert _heterogeneous_workflow() == Ok(FinalValue(1))


def test_nested_result_workflows_short_circuit_independently() -> None:
    @result_workflow
    def inner(unwrap: ResultUnwrapper[WorkflowError]) -> int:
        failed: Result[int, WorkflowError] = Err(WorkflowError("inner"))
        return unwrap(failed)

    @result_workflow
    def outer(unwrap: ResultUnwrapper[WorkflowError]) -> str:
        return str(unwrap(inner()))

    assert outer() == Err(WorkflowError("inner"))


@pytest.mark.parametrize(
    ("result", "expected", "expected_calls"),
    [
        pytest.param(Ok(3), Ok(6), 1, id="ok-applies-function"),
        pytest.param(Err("original"), Err("original"), 0, id="err-short-circuits"),
    ],
)
def test_map(result: Result[int, str], expected: Result[int, str], expected_calls: int) -> None:
    calls = 0

    def double(value: int) -> int:
        nonlocal calls
        calls += 1
        return value * 2

    assert map(result, double) == expected
    assert calls == expected_calls


@pytest.mark.parametrize(
    ("result", "next_result", "expected", "expected_calls"),
    [
        pytest.param(Ok(3), Ok(6), Ok(6), 1, id="ok-continues-to-ok"),
        pytest.param(Ok(3), Err("next"), Err("next"), 1, id="ok-continues-to-err"),
        pytest.param(Err("original"), Ok(6), Err("original"), 0, id="err-short-circuits"),
    ],
)
def test_and_then(
    result: Result[int, str],
    next_result: Result[int, str],
    expected: Result[int, str],
    expected_calls: int,
) -> None:
    calls = 0

    def continue_with(_value: int) -> Result[int, str]:
        nonlocal calls
        calls += 1
        return next_result

    assert and_then(result, continue_with) == expected
    assert calls == expected_calls


@pytest.mark.parametrize(
    ("result", "expected", "expected_calls"),
    [
        pytest.param(Ok(3), Ok(3), 0, id="ok-preserves-value"),
        pytest.param(Err("original"), Err(8), 1, id="err-converts-error"),
    ],
)
def test_map_error(
    result: Result[int, str], expected: Result[int, int] | Result[int, str], expected_calls: int
) -> None:
    calls = 0

    def error_length(error: str) -> int:
        nonlocal calls
        calls += 1
        return len(error)

    assert map_error(result, error_length) == expected
    assert calls == expected_calls

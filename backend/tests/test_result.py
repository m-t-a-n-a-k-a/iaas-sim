import pytest

from iaas_sim.result import Err, Ok, Result, and_then, map


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

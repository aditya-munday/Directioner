from __future__ import annotations

import pytest

from directioner.tools import (
    CalculatorError,
    build_default_registry,
    calculator_tool,
    evaluate,
)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2", 3),
        ("2 * (3 + 4)", 14),
        ("10 / 4", 2.5),
        ("10 // 4", 2),
        ("10 % 3", 1),
        ("2 ** 8", 256),
        ("-5 + 3", -2),
    ],
)
def test_evaluate_supported_expressions(expression: str, expected: float) -> None:
    assert evaluate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    ["", "   ", "1 +", "__import__('os')", "abs(-1)", "a + 1"],
)
def test_evaluate_rejects_invalid_expressions(expression: str) -> None:
    with pytest.raises(CalculatorError):
        evaluate(expression)


def test_evaluate_rejects_division_by_zero() -> None:
    with pytest.raises(CalculatorError, match="Division by zero"):
        evaluate("1 / 0")


@pytest.mark.asyncio
async def test_calculator_tool_handler_returns_result() -> None:
    spec = calculator_tool()

    result = await spec.handler({"expression": "6 * 7"})

    assert result == {"expression": "6 * 7", "result": 42}


@pytest.mark.asyncio
async def test_calculator_tool_handler_requires_string_expression() -> None:
    spec = calculator_tool()

    with pytest.raises(CalculatorError):
        await spec.handler({"expression": 123})


def test_default_registry_contains_calculator() -> None:
    registry = build_default_registry()

    names = {tool.name for tool in registry.list()}

    assert "calculator" in names
    assert "web_search" in names
    assert "read_file" in names
    assert "list_directory" in names
    assert registry.get("calculator").name == "calculator"

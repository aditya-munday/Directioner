"""Built-in calculator tool.

Provides a safe arithmetic expression evaluator exposed as a :class:`ToolSpec`
so it can be registered in the :class:`ToolRegistry` and invoked by the
conversation/AI layer.

The evaluator only allows a restricted subset of Python's expression grammar:
numeric literals, the standard binary/unary arithmetic operators, and
parentheses. Names, calls, attribute access, and every other node type are
rejected so arbitrary code cannot be executed.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from .registry import ToolSpec

_BINARY_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorError(ValueError):
    """Raised when an expression is empty, malformed, or not permitted."""


def _evaluate_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculatorError(f"Unsupported literal: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BINARY_OPERATORS.get(type(node.op))
        if op is None:
            raise CalculatorError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_evaluate_node(node.left), _evaluate_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPERATORS.get(type(node.op))
        if op is None:
            raise CalculatorError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_evaluate_node(node.operand))
    raise CalculatorError(f"Unsupported expression element: {type(node).__name__}")


def evaluate(expression: str) -> float:
    """Safely evaluate an arithmetic ``expression`` and return the result."""

    if not expression or not expression.strip():
        raise CalculatorError("Expression must not be empty")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"Invalid expression: {expression!r}") from exc
    try:
        return _evaluate_node(tree.body)
    except ZeroDivisionError as exc:
        raise CalculatorError("Division by zero") from exc


async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
    expression = arguments.get("expression")
    if not isinstance(expression, str):
        raise CalculatorError("A string 'expression' argument is required")
    return {"expression": expression, "result": evaluate(expression)}


def calculator_tool() -> ToolSpec:
    """Return the calculator :class:`ToolSpec`."""

    return ToolSpec(
        name="calculator",
        description=(
            "Evaluate a basic arithmetic expression using +, -, *, /, //, %, "
            "**, parentheses, and numeric literals."
        ),
        handler=_handle,
    )

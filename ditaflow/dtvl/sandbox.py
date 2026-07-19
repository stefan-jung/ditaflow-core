"""Restricted Python eval sandbox for DTVL expressions.

DTVL context expressions, assertion tests, and report tests are Python boolean
expressions evaluated in a sandbox that:
  - permits standard data operations (len, any, all, isinstance, …)
  - blocks imports, file I/O, exec/eval, and dunder attribute access
  - exposes DTF node helpers and metadata via the caller-supplied *context* dict

The sandbox intentionally uses ``eval`` against a controlled namespace rather
than a full process-isolation scheme (which would be far too slow for
authoring-time feedback on every keystroke).
"""

from __future__ import annotations

import ast
from typing import Any

# Names that are never allowed regardless of context.
_FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "open",
        "globals",
        "locals",
        "vars",
        "dir",
        "breakpoint",
        "input",
        "__builtins__",
        "__class__",
        "__subclasses__",
        "__mro__",
    }
)

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,  # useful during rule development
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


class DtvlSandboxError(ValueError):
    """Raised when a DTVL expression violates sandbox constraints or fails to eval."""


def _check_ast(tree: ast.AST, expr: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise DtvlSandboxError(f"Import not allowed in DTVL expressions: {expr!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise DtvlSandboxError(
                f"Dunder attribute '{node.attr}' not allowed in DTVL expressions: {expr!r}"
            )
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise DtvlSandboxError(f"Name '{node.id}' not allowed in DTVL expressions: {expr!r}")


def safe_eval(expr: str, context: dict[str, Any]) -> Any:
    """Evaluate *expr* in a restricted sandbox with *context* as the namespace.

    Returns the result of the expression.
    Raises :exc:`DtvlSandboxError` for security violations or eval errors.
    """
    stripped = expr.strip()
    try:
        tree = ast.parse(stripped, mode="eval")
    except SyntaxError as exc:
        raise DtvlSandboxError(f"Syntax error in DTVL expression {expr!r}: {exc}") from exc

    _check_ast(tree, stripped)

    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, **context}
    try:
        return eval(compile(tree, "<dtvl>", "eval"), namespace)  # noqa: S307
    except DtvlSandboxError:
        raise
    except Exception as exc:
        raise DtvlSandboxError(
            f"Error evaluating DTVL expression {expr!r}: {type(exc).__name__}: {exc}"
        ) from exc


def safe_exec(script: str, context: dict[str, Any]) -> Any:
    """Execute a multi-statement DTVL *script* and return the value of ``result``.

    The script should assign its outcome to a variable named ``result``.
    The same sandbox restrictions as :func:`safe_eval` apply.
    """
    try:
        tree = ast.parse(script.strip(), mode="exec")
    except SyntaxError as exc:
        raise DtvlSandboxError(f"Syntax error in DTVL script: {exc}") from exc

    _check_ast(tree, "<script>")

    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS, "result": None, **context}
    try:
        exec(compile(tree, "<dtvl-script>", "exec"), namespace)  # noqa: S102
    except DtvlSandboxError:
        raise
    except Exception as exc:
        raise DtvlSandboxError(f"Error executing DTVL script: {type(exc).__name__}: {exc}") from exc
    return namespace.get("result")

"""DTF node helper functions exposed to DTVL expressions.

These are available by name inside every context expression, assertion test,
and report test without any import.  They are intentionally simple and
side-effect-free so the sandbox can pass them through without restriction.
"""

from __future__ import annotations

from typing import Any


def text_content(node: dict[str, Any]) -> str:
    """Recursively concatenate all string children into a single string."""
    parts: list[str] = []
    for child in node.get("children", []):
        if isinstance(child, str):
            parts.append(child)
        elif isinstance(child, dict):
            parts.append(text_content(child))
    return "".join(parts)


def word_count(node: dict[str, Any]) -> int:
    """Number of whitespace-separated words in the node's text content."""
    return len(text_content(node).split())


def char_count(node: dict[str, Any]) -> int:
    """Total character count of the node's text content (excluding whitespace)."""
    return len(text_content(node).replace(" ", "").replace("\n", ""))


def get_attr(node: dict[str, Any], attr: str, default: str = "") -> str:
    """Return the value of *attr* from the node's ``attrs`` dict, or *default*."""
    return str(node.get("attrs", {}).get(attr, default))


def has_attr(node: dict[str, Any], attr: str) -> bool:
    """Return True if the node's ``attrs`` dict contains *attr*."""
    return attr in node.get("attrs", {})


def children_of_type(node: dict[str, Any], base_type: str) -> list[dict[str, Any]]:
    """Return direct children whose ``baseType`` matches *base_type*."""
    return [
        c
        for c in node.get("children", [])
        if isinstance(c, dict) and c.get("baseType") == base_type
    ]


def has_child_of_type(node: dict[str, Any], base_type: str) -> bool:
    """Return True if any direct child has the given *base_type*."""
    return any(
        isinstance(c, dict) and c.get("baseType") == base_type for c in node.get("children", [])
    )


def descendant_count(node: dict[str, Any], base_type: str) -> int:
    """Count all descendants (at any depth) whose ``baseType`` is *base_type*."""
    count = 0
    for child in node.get("children", []):
        if isinstance(child, dict):
            if child.get("baseType") == base_type:
                count += 1
            count += descendant_count(child, base_type)
    return count


def has_text(node: dict[str, Any]) -> bool:
    """Return True if the node has any non-empty text content."""
    return bool(text_content(node).strip())


def child_count(node: dict[str, Any]) -> int:
    """Number of children (element or text)."""
    return len(node.get("children", []))


def element_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only element (dict) children — excludes text strings."""
    return [c for c in node.get("children", []) if isinstance(c, dict)]


def is_empty(node: dict[str, Any]) -> bool:
    """Return True if the node has no text content and no element children."""
    return not has_text(node) and not element_children(node)


# Namespace dict injected into every DTVL eval context.
HELPER_NAMESPACE: dict[str, Any] = {
    "text_content": text_content,
    "word_count": word_count,
    "char_count": char_count,
    "get_attr": get_attr,
    "has_attr": has_attr,
    "children_of_type": children_of_type,
    "has_child_of_type": has_child_of_type,
    "descendant_count": descendant_count,
    "has_text": has_text,
    "child_count": child_count,
    "element_children": element_children,
    "is_empty": is_empty,
}

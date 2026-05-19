"""Parse source files into function nodes and call edges with tree-sitter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = {"python", "typescript", "ts", "tsx", "javascript", "js", "jsx"}


@dataclass(slots=True)
class FunctionNode:
    name: str
    language: str
    file_path: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class FunctionCallEdge:
    caller: str
    callee: str
    file_path: str


def parse_file(file_path: str | Path, language: str | None = None) -> tuple[list[FunctionNode], list[FunctionCallEdge]]:
    path = Path(file_path)
    lang = _normalise_language(language or path.suffix.lstrip("."))
    if lang is None:
        return [], []
    source = path.read_text(encoding="utf-8")
    return parse_code(source, language=lang, file_path=str(path))


def parse_code(code: str, *, language: str, file_path: str = "<memory>") -> tuple[list[FunctionNode], list[FunctionCallEdge]]:
    lang = _normalise_language(language)
    if lang is None:
        return [], []

    parser_factory = _load_parser_factory()
    parser = parser_factory(lang)
    tree = parser.parse(code.encode("utf-8"))

    if lang == "python":
        return _parse_python_tree(tree, file_path=file_path, language=lang)
    return _parse_typescript_tree(tree, file_path=file_path, language=lang)


def _parse_python_tree(tree: Any, *, file_path: str, language: str) -> tuple[list[FunctionNode], list[FunctionCallEdge]]:
    root = tree.root_node
    function_nodes: list[FunctionNode] = []
    calls_by_func: dict[str, set[str]] = {}
    defined_names: set[str] = set()

    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            func_name = _node_text(name_node)
            defined_names.add(func_name)
            function_nodes.append(
                FunctionNode(
                    name=func_name,
                    language=language,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
            body = node.child_by_field_name("body")
            calls_by_func[func_name] = _extract_python_calls(body) if body else set()
            continue

        stack.extend(reversed(node.children))

    edges = _resolve_edges(calls_by_func, defined_names, file_path=file_path)
    return function_nodes, edges


def _parse_typescript_tree(
    tree: Any,
    *,
    file_path: str,
    language: str,
) -> tuple[list[FunctionNode], list[FunctionCallEdge]]:
    root = tree.root_node
    function_nodes: list[FunctionNode] = []
    calls_by_func: dict[str, set[str]] = {}
    defined_names: set[str] = set()

    stack = [root]
    while stack:
        node = stack.pop()
        extracted = _extract_ts_function(node)
        if extracted is not None:
            func_name, body = extracted
            defined_names.add(func_name)
            function_nodes.append(
                FunctionNode(
                    name=func_name,
                    language=language,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
            calls_by_func[func_name] = _extract_js_calls(body)
            continue

        stack.extend(reversed(node.children))

    edges = _resolve_edges(calls_by_func, defined_names, file_path=file_path)
    return function_nodes, edges


def _extract_python_calls(node: Any | None) -> set[str]:
    if node is None:
        return set()
    calls: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "call":
            func = current.child_by_field_name("function")
            name = _extract_callable_name(func)
            if name:
                calls.add(name)
        stack.extend(reversed(current.children))
    return calls


def _extract_js_calls(node: Any | None) -> set[str]:
    if node is None:
        return set()
    calls: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "call_expression":
            fn = current.child_by_field_name("function")
            name = _extract_callable_name(fn)
            if name:
                calls.add(name)
        stack.extend(reversed(current.children))
    return calls


def _extract_ts_function(node: Any) -> tuple[str, Any] | None:
    if node.type == "function_declaration":
        name = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if name and body:
            return _node_text(name), body
        return None

    if node.type == "method_definition":
        name = node.child_by_field_name("name")
        body = node.child_by_field_name("body")
        if name and body:
            return _node_text(name), body
        return None

    if node.type != "variable_declarator":
        return None

    name = node.child_by_field_name("name")
    value = node.child_by_field_name("value")
    if name is None or value is None:
        return None

    if value.type == "arrow_function":
        body = value.child_by_field_name("body")
        if body:
            return _node_text(name), body
    if value.type == "function":
        body = value.child_by_field_name("body")
        if body:
            return _node_text(name), body
    return None


def _extract_callable_name(node: Any | None) -> str | None:
    if node is None:
        return None

    if node.type in {"identifier", "property_identifier"}:
        return _node_text(node)

    if node.type in {"attribute", "member_expression"}:
        attr = node.child_by_field_name("attribute") or node.child_by_field_name("property")
        if attr is not None:
            return _node_text(attr)

    for child in node.children:
        name = _extract_callable_name(child)
        if name:
            return name
    return None


def _resolve_edges(calls_by_func: dict[str, set[str]], defined_names: set[str], *, file_path: str) -> list[FunctionCallEdge]:
    edges: list[FunctionCallEdge] = []
    for caller, callees in calls_by_func.items():
        for callee in sorted(callees):
            if callee in defined_names:
                edges.append(FunctionCallEdge(caller=caller, callee=callee, file_path=file_path))
    return edges


def _node_text(node: Any) -> str:
    return node.text.decode("utf-8")


def _normalise_language(language: str) -> str | None:
    lang = language.lower()
    if lang == "python":
        return "python"
    if lang in {"typescript", "ts", "tsx", "javascript", "js", "jsx"}:
        return "typescript"
    return None


def is_supported_file(path: str | Path) -> bool:
    suffix = Path(path).suffix.lstrip(".").lower()
    return suffix in SUPPORTED_LANGUAGES


def _load_parser_factory():
    try:
        from tree_sitter_languages import get_parser
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "tree-sitter dependencies are missing. Install `tree-sitter` and `tree-sitter-languages`."
        ) from exc
    return get_parser

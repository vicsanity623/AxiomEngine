"""Axiom - code_introspector.py

Lightweight, local-only utilities for understanding the Axiom codebase structure.
Used by idle tasks to keep a live in-memory map of modules and HTTP endpoints.
"""

import ast
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """Represent a function's name and line number."""

    name: str
    lineno: int


@dataclass
class ClassInfo:
    """Represent a class's name and line number."""

    name: str
    lineno: int


@dataclass
class ModuleSummary:
    """Represent a module's path and contained functions and classes."""

    path: str
    functions: list[FunctionInfo]
    classes: list[ClassInfo]


def _iter_py_files(root: str) -> list[str]:
    """Iterate over all Python files in the given directory and its subdirectories.

    Args:
        root (str): The root directory to search for Python files.

    Returns:
        list[str]: A list of file paths.

    """
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".py"):
                files.append(os.path.join(dirpath, fname))
    return files


def build_module_map(src_root: str) -> dict[str, ModuleSummary]:
    """Build a map of modules to their functions and classes.

    Args:
        src_root (str): The root directory containing the Python source files.

    Returns:
        dict[str, ModuleSummary]: A dictionary where keys are module paths and values are ModuleSummary objects.

    """
    module_map: dict[str, ModuleSummary] = {}

    for path in _iter_py_files(src_root):
        rel_name = os.path.relpath(path, src_root)
        try:
            with open(path, encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=path)
        except Exception as e:
            logger.error(f"Failed to parse file {path}: {e}")
            continue

        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    FunctionInfo(name=node.name, lineno=node.lineno)
                )
            elif isinstance(node, ast.ClassDef):
                classes.append(ClassInfo(name=node.name, lineno=node.lineno))

        module_map[rel_name] = ModuleSummary(
            path=path,
            functions=functions,
            classes=classes,
        )

    return module_map


def build_endpoint_registry(node_file: str) -> list[dict]:
    """Parse Flask route decorators from the main node module.

    Args:
        node_file (str): The file path to the main node module.

    Returns:
        list[dict]: A list of dictionaries representing endpoint paths, methods, and associated functions.

    """
    if not os.path.exists(node_file):
        return []

    try:
        with open(node_file, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=node_file)
    except Exception:
        return []

    endpoints: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.decorator_list:
            continue

        for dec in node.decorator_list:
            # Look for @app.route(...)
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and getattr(dec.func.value, "id", None) == "app"
                and dec.func.attr == "route"
            ):
                path: str | None = None
                methods: list[str] = []

                # First positional argument is usually the path.
                if dec.args:
                    arg0 = dec.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(
                        arg0.value, str
                    ):
                        path = arg0.value

                # Look for methods kwarg.
                for kw in dec.keywords or []:
                    if kw.arg == "methods" and isinstance(kw.value, ast.List):
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(
                                elt.value, str
                            ):
                                methods.append(elt.value.upper())

                if not methods:
                    methods = ["GET"]

                endpoints.append(
                    {
                        "path": path or "",
                        "methods": methods,
                        "function": node.name,
                    }
                )

    return endpoints

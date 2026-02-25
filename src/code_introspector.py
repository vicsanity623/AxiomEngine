"""
Axiom - code_introspector.py

Lightweight, local-only utilities for understanding the Axiom codebase structure.
Used by idle tasks to keep a live in-memory map of modules and HTTP endpoints.
"""

import ast
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FunctionInfo:
    name: str
    lineno: int


@dataclass
class ClassInfo:
    name: str
    lineno: int


@dataclass
class ModuleSummary:
    path: str
    functions: List[FunctionInfo]
    classes: List[ClassInfo]


def _iter_py_files(root: str) -> List[str]:
    files: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".py"):
                files.append(os.path.join(dirpath, fname))
    return files


def build_module_map(src_root: str) -> Dict[str, ModuleSummary]:
    """
    Build a simple map of module -> (classes, functions).

    This is intentionally shallow and non-invasive: it only parses Python
    source files under src_root and records top-level definitions.
    """
    module_map: Dict[str, ModuleSummary] = {}

    for path in _iter_py_files(src_root):
        rel_name = os.path.relpath(path, src_root)
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=path)
        except Exception:
            continue

        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append(FunctionInfo(name=node.name, lineno=node.lineno))
            elif isinstance(node, ast.AsyncFunctionDef):
                functions.append(FunctionInfo(name=node.name, lineno=node.lineno))
            elif isinstance(node, ast.ClassDef):
                classes.append(ClassInfo(name=node.name, lineno=node.lineno))

        module_map[rel_name] = ModuleSummary(
            path=path,
            functions=functions,
            classes=classes,
        )

    return module_map


def build_endpoint_registry(node_file: str) -> List[dict]:
    """
    Parse Flask route decorators from the main node module.

    Returns a list of dicts: {\"path\": str, \"methods\": [str], \"function\": str}.
    """
    if not os.path.exists(node_file):
        return []

    try:
        with open(node_file, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=node_file)
    except Exception:
        return []

    endpoints: List[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.decorator_list:
            continue

        for dec in node.decorator_list:
            # Look for @app.route(...)
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", None) == "app" and dec.func.attr == "route":
                    path: Optional[str] = None
                    methods: List[str] = []

                    # First positional argument is usually the path.
                    if dec.args:
                        arg0 = dec.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            path = arg0.value

                    # Look for methods kwarg.
                    for kw in dec.keywords or []:
                        if kw.arg == "methods":
                            if isinstance(kw.value, ast.List):
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


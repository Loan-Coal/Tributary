"""
Module: check_layers
Layer: scripts
Purpose: Enforce forbidden cross-layer import rules by grepping source files.
Dependencies: os, sys, re, pathlib
Used by: Makefile check-layers target
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "tributary"

# Documented exemptions to the "no neo4j outside graph/" rule. seed.py is a dev-utility
# seed script superseded by the Wave 2 graph writer (DEC-013, DEC-014, DEC-020). Listed
# explicitly so the checker reports the import honestly rather than missing it by accident.
NEO4J_EXEMPT_FILES: frozenset[str] = frozenset({"ingestion/seed.py"})

VIOLATIONS: list[str] = []


def _rel_posix(path: Path) -> str:
    """Return path relative to SRC_ROOT using forward slashes (OS-independent)."""
    return path.relative_to(SRC_ROOT).as_posix()


def _python_files(directory: Path) -> list[Path]:
    """Return all .py files under a directory recursively."""
    return list(directory.rglob("*.py"))


def _file_contains(path: Path, pattern: str, flags: int = 0) -> bool:
    """Return True if path's text contains the regex pattern."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(pattern, text, flags))


def check_neo4j_outside_graph() -> None:
    """neo4j driver must only be imported inside graph/."""
    graph_dir = SRC_ROOT / "graph"
    for py_file in _python_files(SRC_ROOT):
        if py_file.is_relative_to(graph_dir):
            continue
        if _rel_posix(py_file) in NEO4J_EXEMPT_FILES:
            continue
        if _file_contains(py_file, r"^\s*(?:import neo4j\b|from neo4j\b)", flags=re.MULTILINE):
            VIOLATIONS.append(
                f"neo4j import outside graph/: {py_file}"
            )


def check_anthropic_outside_ai() -> None:
    """anthropic SDK must only be imported inside ai/."""
    ai_dir = SRC_ROOT / "ai"
    for py_file in _python_files(SRC_ROOT):
        if py_file.is_relative_to(ai_dir):
            continue
        if _file_contains(py_file, r"^\s*(?:import anthropic\b|from anthropic\b)", flags=re.MULTILINE):
            VIOLATIONS.append(
                f"anthropic import outside ai/: {py_file}"
            )


def check_ai_does_not_import_engine() -> None:
    """ai/ must not import from engine/."""
    ai_dir = SRC_ROOT / "ai"
    for py_file in _python_files(ai_dir):
        if _file_contains(
            py_file,
            r"from tributary\.engine|import tributary\.engine",
        ):
            VIOLATIONS.append(
                f"ai/ imports engine: {py_file}"
            )


def check_engine_does_not_import_ai() -> None:
    """engine/ must not import from ai/."""
    engine_dir = SRC_ROOT / "engine"
    for py_file in _python_files(engine_dir):
        if _file_contains(
            py_file,
            r"from tributary\.ai|import tributary\.ai",
        ):
            VIOLATIONS.append(
                f"engine/ imports ai: {py_file}"
            )


def main() -> int:
    """Run all layer checks and report violations."""
    check_neo4j_outside_graph()
    check_anthropic_outside_ai()
    check_ai_does_not_import_engine()
    check_engine_does_not_import_ai()

    if VIOLATIONS:
        print("Layer violations found:")
        for v in VIOLATIONS:
            print(f"  VIOLATION: {v}")
        return 1

    print("Layer check passed — no violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

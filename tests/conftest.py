"""Pytest configuration for the mempalace_bot repository.

Ensure the repository root is on sys.path so tests can import the local
package layout consistently from any invocation path.
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARENT_DIR = os.path.abspath(os.path.join(REPO_ROOT, ".."))

paths = [REPO_ROOT]
if os.path.basename(REPO_ROOT) != "mutants":
    paths.append(PARENT_DIR)

for path in paths:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    import importlib.util

    if importlib.util.find_spec("mempalace_bot") is None:
        import types

        package = types.ModuleType("mempalace_bot")
        package.__path__ = [REPO_ROOT]
        sys.modules["mempalace_bot"] = package
except Exception:
    pass

# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2019 gfduszynski
"""Shared test fixtures.

The CLI entry points under scripts/ have no .py extension (they're installed
as setuptools `scripts`, not importable modules), so they need a manual
loader to be exercised in tests.
"""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_script(name):
    path = SCRIPTS_DIR / name
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


@pytest.fixture
def load_script():
    """Return a function that loads one of the scripts/ entry points as a module."""
    return _load_script

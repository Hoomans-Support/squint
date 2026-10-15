"""Dataset profiles: the words and numbers that differ between sample datasets.

The pipeline, the dashboard and the data shape are the same for every dataset; a profile only changes labels, wording and a few
business numbers (which journeys and screens the app has stay the same internal ids). The active profile is chosen with the
environment variable SQUINT_PROFILE (default: wallet), read once when a pipeline module is imported.

A profile module defines PROFILE, a dict. Missing keys fall back to the wallet defaults that live in schema.py and build_results.py.
"""
from __future__ import annotations

import importlib
import os

NAMES = ("wallet", "dining")


def active_name() -> str:
    name = os.environ.get("SQUINT_PROFILE", "wallet").strip() or "wallet"
    if name not in NAMES:
        raise SystemExit(f"unknown profile {name!r}; choose one of {NAMES}")
    return name


def load(name: str | None = None) -> dict:
    return importlib.import_module(f"profiles.{name or active_name()}").PROFILE

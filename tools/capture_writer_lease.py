"""Shared operational writer lease for capture and ordinary Daily."""
from functools import wraps
from inspect import signature
from pathlib import Path


def writer_lease(root):
    from feedback_publication_lock import publication_lock
    return publication_lock(Path(root) / ".stocklookup-production-writer", blocking=False)


def exclusive_writer(function):
    """Same kernel lease for Owner Daily and capture-only; no polling/stale files."""
    parameters = signature(function)
    @wraps(function)
    def guarded(*args, **kwargs):
        bound = parameters.bind(*args, **kwargs)
        bound.apply_defaults()
        with writer_lease(bound.arguments["root"]):
            return function(*args, **kwargs)
    return guarded

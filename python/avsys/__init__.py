"""Audio Validation Systems Lab foundation package."""

from ._version import __version__


def native_version() -> str:
    """Return the linked native component version."""
    from . import _native

    return _native.version()


__all__ = ["__version__", "native_version"]

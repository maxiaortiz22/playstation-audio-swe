"""Audio Validation Systems Lab foundation package."""

from ._version import __version__


def native_version() -> str:
    """Return the linked native component version."""
    from . import _native

    return _native.version()


def native_passthrough(input_buffer, block_size: int = 128):
    """Return a new bit-exact native passthrough copy of interleaved PCM."""
    from . import _native

    return _native.native_passthrough(input_buffer, block_size)


__all__ = ["__version__", "native_passthrough", "native_version"]

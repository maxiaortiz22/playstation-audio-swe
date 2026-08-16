"""Cross-language smoke test intended to run against an installed wheel."""

import avsys


def test_sys_bnd_001_wheel_loads_linked_native_component() -> None:
    assert avsys.__version__ == "0.1.0"
    assert avsys.native_version() == avsys.__version__

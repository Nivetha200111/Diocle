"""Marks the test modules that run the real toolchain (GnuCOBOL cobc, a JDK, the SQLite JDBC jar) with the
`toolchain` marker, registered in pyproject.toml. `scripts/test.sh --fast` deselects them (-m "not toolchain");
the default run, and CI, run everything. Add a module to TOOLCHAIN_MODULES when it starts compiling or running
real COBOL or Java."""
import pytest

TOOLCHAIN_MODULES = {"test_sql_conversion", "test_ksds_conversion", "test_sortgen", "test_pipeline"}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.module.__name__.rsplit(".", 1)[-1] in TOOLCHAIN_MODULES:
            item.add_marker(pytest.mark.toolchain)

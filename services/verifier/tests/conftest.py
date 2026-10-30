"""Marks the test modules that run the real toolchain (GnuCOBOL cobc, a JDK, the SQLite JDBC jar) with the
`toolchain` marker, registered in pyproject.toml. `scripts/test.sh --fast` deselects them (-m "not toolchain");
the default run, and CI, run everything. Add a module to TOOLCHAIN_MODULES when it starts compiling or running
real COBOL or Java."""
import pytest

TOOLCHAIN_MODULES = {"test_ksds", "test_sql", "test_mutate", "test_minimize", "test_buildcheck", "test_stdout_and_update", "test_verify_interest_accrual", "test_transcript_sandbox", "test_reverify", "test_precheck", "test_golden", "test_jobs", "test_claims", "test_sandbox", "test_collation", "test_clock_and_return_code", "test_called_modules"}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.module.__name__.rsplit(".", 1)[-1] in TOOLCHAIN_MODULES:
            item.add_marker(pytest.mark.toolchain)

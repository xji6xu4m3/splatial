"""Root conftest: treat no-tests-collected as success (exit 0)."""
import pytest


def pytest_sessionfinish(session, exitstatus):
    if exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK

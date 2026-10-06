"""Shared test fixtures — keeps every dashboard GET network-free.

Phase 6 wires the Roommate due-check into GET / (build-plan step 2: the
check runs whenever the dashboard loads). Without this fixture every
existing dashboard test would attempt a real LLM call. The autouse
fixture replaces the dashboard route's provider with one that always
raises ProviderError, so the due-check skips cleanly. Phase 6 tests
re-patch the same attribute with their own FakeProvider when they need
canned LLM replies (a test's own monkeypatch wins over the fixture).
"""
import pytest

from app.ai.provider import ProviderError


class NoNetworkProvider:
    def generate(self, system_prompt, user_message):
        raise ProviderError("no LLM calls in tests")


@pytest.fixture(autouse=True)
def _no_roommate_llm(monkeypatch):
    monkeypatch.setattr(
        "app.routes.dashboard.get_provider", lambda: NoNetworkProvider()
    )


@pytest.fixture(autouse=True)
def _restore_settings_env(monkeypatch):
    """POST /settings writes os.environ directly (real behavior, not a test
    seam) — snapshot the two user-editable keys so one test's POST can never
    leak a cadence or pause-default into the next test's DB decisions."""
    monkeypatch.setenv("ROOMMATE_CADENCE_DAYS", "3")
    monkeypatch.delenv("NEW_COURSES_START_PAUSED", raising=False)


@pytest.fixture(autouse=True)
def _auth_as_test_user():
    """Phase 12: every pre-auth test acts as a fixed logged-in user (id=1).

    The learning routes now require get_current_user. Legacy tests exercise
    single-user behavior, so this overrides the dependency to a constant test
    user instead of a real session cookie. Auth/isolation tests that need to
    prove the gate works pop this override and log in for real — see
    tests/test_auth.py and tests/test_tenant_isolation.py.
    """
    from app.main import api
    from app.auth.dependencies import get_current_user

    test_user = {"id": 1, "email": "test@local", "name": "Test User"}
    api.dependency_overrides[get_current_user] = lambda: test_user
    yield
    api.dependency_overrides.pop(get_current_user, None)
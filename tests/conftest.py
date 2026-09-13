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
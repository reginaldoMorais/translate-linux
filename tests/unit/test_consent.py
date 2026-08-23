"""Tests for when consent is required."""

from __future__ import annotations

import pytest

from translate_linux.ui.consent import CONSENT_VERSION, consent_needed


class TestConsentNeeded:
    def test_local_translation_never_asks(self) -> None:
        """Nothing leaves the machine, so there is nothing to consent to."""
        assert consent_needed("local_ct2", 0) is False

    def test_a_fresh_install_choosing_an_online_provider_is_asked(self) -> None:
        assert consent_needed("google_cloud_v2", 0) is True

    def test_an_accepted_version_is_not_asked_again(self) -> None:
        assert consent_needed("google_cloud_v2", CONSENT_VERSION) is False

    def test_newer_terms_ask_again(self) -> None:
        """Raising the version re-asks, which is the point of versioning it."""
        assert consent_needed("google_cloud_v2", CONSENT_VERSION - 1) is True

    def test_a_recorded_version_beyond_the_current_one_is_accepted(self) -> None:
        assert consent_needed("google_cloud_v2", CONSENT_VERSION + 5) is False

    @pytest.mark.parametrize("provider", ["google_cloud_v2", "google_free", "anything_else"])
    def test_every_non_local_provider_requires_consent(self, provider: str) -> None:
        assert consent_needed(provider, 0) is True

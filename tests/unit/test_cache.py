"""Tests for the translation cache, including its self-healing behaviour."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from translate_linux.translate.base import Translation
from translate_linux.translate.cache import (
    TranslationCache,
    cache_key,
)


def translation(text: str = "olá", **overrides: object) -> Translation:
    fields: dict[str, object] = {
        "text": text,
        "detected_source": "en",
        "target": "pt",
        "provider": "local_ct2",
    }
    fields.update(overrides)
    return Translation(**fields)  # type: ignore[arg-type]


@pytest.fixture
def cache(tmp_path: Path) -> TranslationCache:
    return TranslationCache(tmp_path / "cache.db")


class TestCacheKey:
    def test_the_same_request_yields_the_same_key(self) -> None:
        assert cache_key("hi", "en", "pt", "p") == cache_key("hi", "en", "pt", "p")

    @pytest.mark.parametrize(
        "other",
        [
            ("bye", "en", "pt", "p"),
            ("hi", "es", "pt", "p"),
            ("hi", "en", "de", "p"),
            ("hi", "en", "pt", "other"),
        ],
        ids=["text", "source", "target", "provider"],
    )
    def test_every_field_changes_the_key(self, other: tuple[str, str, str, str]) -> None:
        assert cache_key("hi", "en", "pt", "p") != cache_key(*other)

    def test_an_absent_source_differs_from_an_explicit_one(self) -> None:
        """'Detect it' and 'assume English' are different questions."""
        assert cache_key("hi", None, "pt", "p") != cache_key("hi", "en", "pt", "p")

    def test_the_separator_cannot_be_forged_by_the_text(self) -> None:
        assert cache_key("a", "b", "pt", "p") != cache_key("a\x1fb", None, "pt", "p")


class TestRoundTrip:
    def test_an_unknown_request_misses(self, cache: TranslationCache) -> None:
        assert cache.lookup("hello", None, "pt", "local_ct2") is None

    def test_a_stored_translation_is_returned(self, cache: TranslationCache) -> None:
        cache.store("hello", None, translation())
        found = cache.lookup("hello", None, "pt", "local_ct2")

        assert found is not None
        assert found.text == "olá"
        assert found.detected_source == "en"
        assert found.from_cache is True

    def test_a_fresh_translation_is_not_marked_as_cached(self) -> None:
        assert translation().from_cache is False

    def test_a_different_target_does_not_hit(self, cache: TranslationCache) -> None:
        cache.store("hello", None, translation())
        assert cache.lookup("hello", None, "de", "local_ct2") is None

    def test_a_different_provider_does_not_hit(self, cache: TranslationCache) -> None:
        cache.store("hello", None, translation())
        assert cache.lookup("hello", None, "pt", "google_cloud_v2") is None

    def test_restoring_overwrites_rather_than_duplicating(self, cache: TranslationCache) -> None:
        cache.store("hello", None, translation("primeiro"))
        cache.store("hello", None, translation("segundo"))

        found = cache.lookup("hello", None, "pt", "local_ct2")
        assert found is not None
        assert found.text == "segundo"
        assert cache.count() == 1

    def test_the_cache_survives_being_reopened(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.db"
        with TranslationCache(path) as first:
            first.store("hello", None, translation())

        with TranslationCache(path) as second:
            assert second.lookup("hello", None, "pt", "local_ct2") is not None


class TestEviction:
    def test_the_least_recently_used_entry_is_dropped(self, tmp_path: Path) -> None:
        cache = TranslationCache(tmp_path / "cache.db", max_entries=3)
        for index in range(5):
            cache.store(f"text-{index}", None, translation(f"tradução-{index}"))

        assert cache.count() == 3
        assert cache.lookup("text-0", None, "pt", "local_ct2") is None
        assert cache.lookup("text-4", None, "pt", "local_ct2") is not None

    def test_a_recent_hit_protects_an_entry(self, tmp_path: Path) -> None:
        now = [1000.0]
        cache = TranslationCache(tmp_path / "cache.db", max_entries=2, clock=lambda: now[0])

        cache.store("keep", None, translation())
        now[0] += 10
        cache.store("filler", None, translation())
        now[0] += 10
        cache.lookup("keep", None, "pt", "local_ct2")  # refreshes last_used
        now[0] += 10
        cache.store("newest", None, translation())

        assert cache.lookup("keep", None, "pt", "local_ct2") is not None
        assert cache.lookup("filler", None, "pt", "local_ct2") is None


class TestExpiry:
    def test_an_entry_within_the_ttl_still_hits(self, tmp_path: Path) -> None:
        now = [1000.0]
        cache = TranslationCache(tmp_path / "cache.db", ttl_seconds=60, clock=lambda: now[0])
        cache.store("hello", None, translation())
        now[0] += 30

        assert cache.lookup("hello", None, "pt", "local_ct2") is not None

    def test_an_expired_entry_is_dropped_on_lookup(self, tmp_path: Path) -> None:
        now = [1000.0]
        cache = TranslationCache(tmp_path / "cache.db", ttl_seconds=60, clock=lambda: now[0])
        cache.store("hello", None, translation())
        now[0] += 61

        assert cache.lookup("hello", None, "pt", "local_ct2") is None
        assert cache.count() == 0

    def test_a_zero_ttl_disables_expiry(self, tmp_path: Path) -> None:
        cache = TranslationCache(tmp_path / "cache.db", ttl_seconds=0)
        cache.store("hello", None, translation())
        assert cache.lookup("hello", None, "pt", "local_ct2") is not None


class TestResilience:
    def test_a_corrupt_database_is_rebuilt(self, tmp_path: Path) -> None:
        """Derived data: replace it rather than fail the translation."""
        path = tmp_path / "cache.db"
        path.write_bytes(b"this is definitely not a sqlite database" * 20)

        cache = TranslationCache(path)
        cache.store("hello", None, translation())
        assert cache.lookup("hello", None, "pt", "local_ct2") is not None

    def test_a_closed_cache_never_raises_on_use(self, cache: TranslationCache) -> None:
        cache.close()
        assert cache.lookup("hello", None, "pt", "local_ct2") is None
        cache.store("hello", None, translation())  # must not raise
        assert cache.count() == 0

    def test_a_missing_parent_directory_is_created(self, tmp_path: Path) -> None:
        cache = TranslationCache(tmp_path / "deep" / "nested" / "cache.db")
        cache.store("hello", None, translation())
        assert cache.count() == 1

    def test_the_schema_version_is_recorded(self, tmp_path: Path) -> None:
        path = tmp_path / "cache.db"
        TranslationCache(path).close()
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


class TestClear:
    def test_everything_is_forgotten(self, cache: TranslationCache) -> None:
        cache.store("a", None, translation())
        cache.store("b", None, translation())
        cache.clear()
        assert cache.count() == 0

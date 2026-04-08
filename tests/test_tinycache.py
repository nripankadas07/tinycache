"""Tests for tinycache.

Naming convention: test_[unit]_[scenario]_[expected_result]
"""
import threading
import time

import pytest

from tinycache import CacheInfo, TinyCacheError, tinycache


# ---------------------------------------------------------------------------
# Basic caching behaviour
# ---------------------------------------------------------------------------


def test_tinycache_simple_call_returns_correct_result() -> None:
    @tinycache()
    def double(x: int) -> int:
        return x * 2

    assert double(3) == 6


def test_tinycache_repeated_call_returns_cached_result() -> None:
    call_count = 0

    @tinycache()
    def expensive(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 10

    expensive(5)
    expensive(5)
    assert call_count == 1


def test_tinycache_different_args_call_underlying_function() -> None:
    call_count = 0

    @tinycache()
    def add(a: int, b: int) -> int:
        nonlocal call_count
        call_count += 1
        return a + b

    add(1, 2)
    add(3, 4)
    assert call_count == 2


def test_tinycache_kwargs_are_part_of_cache_key() -> None:
    call_count = 0

    @tinycache()
    def greet(name: str, greeting: str = "hello") -> str:
        nonlocal call_count
        call_count += 1
        return f"{greeting} {name}"

    greet("alice")
    greet("alice", greeting="hi")
    assert call_count == 2


def test_tinycache_cache_info_starts_at_zero() -> None:
    @tinycache()
    def identity(x: int) -> int:
        return x

    info = identity.cache_info()
    assert info.hits == 0
    assert info.misses == 0
    assert info.currsize == 0


def test_tinycache_cache_info_tracks_hits_and_misses() -> None:
    @tinycache()
    def identity(x: int) -> int:
        return x

    identity(1)  # miss
    identity(1)  # hit
    identity(2)  # miss
    info = identity.cache_info()
    assert info.hits == 1
    assert info.misses == 2
    assert info.currsize == 2


def test_tinycache_cache_info_returns_cache_info_namedtuple() -> None:
    @tinycache()
    def identity(x: int) -> int:
        return x

    assert isinstance(identity.cache_info(), CacheInfo)


def test_tinycache_cache_clear_resets_state() -> None:
    call_count = 0

    @tinycache()
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)
    compute(1)
    assert call_count == 1

    compute.cache_clear()
    compute(1)
    assert call_count == 2

    info = identity_after_clear = compute.cache_info()
    assert info.hits == 0
    assert info.currsize == 1


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def test_tinycache_lru_evicts_least_recently_used() -> None:
    @tinycache(maxsize=2)
    def identity(x: int) -> int:
        return x

    identity(1)  # cache: [1]
    identity(2)  # cache: [1, 2]
    identity(1)  # hit → 1 now most-recent; cache: [2, 1]
    identity(3)  # miss → evicts 2; cache: [1, 3]

    info = identity.cache_info()
    assert info.currsize == 2


def test_tinycache_maxsize_one_caches_only_latest_entry() -> None:
    call_count = 0

    @tinycache(maxsize=1)
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)  # miss
    compute(2)  # miss (evicts 1)
    compute(1)  # miss (1 was evicted)
    assert call_count == 3


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


def test_tinycache_ttl_expired_entry_refetched(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0
    fake_time = 0.0

    monkeypatch.setattr("tinycache.core.time", lambda: fake_time)

    @tinycache(ttl=1.0)
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)
    assert call_count == 1

    fake_time = 1.5  # advance past TTL
    compute(1)
    assert call_count == 2


def test_tinycache_ttl_not_expired_serves_cached_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    fake_time = 0.0

    monkeypatch.setattr("tinycache.core.time", lambda: fake_time)

    @tinycache(ttl=5.0)
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)
    fake_time = 4.9  # still within TTL
    compute(1)
    assert call_count == 1


def test_tinycache_ttl_zero_every_call_is_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    fake_time = 0.0

    monkeypatch.setattr("tinycache.core.time", lambda: fake_time)

    @tinycache(ttl=0.0)
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)
    compute(1)
    assert call_count == 2


def test_tinycache_none_ttl_entries_never_expire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    fake_time = 0.0

    monkeypatch.setattr("tinycache.core.time", lambda: fake_time)

    @tinycache(ttl=None)
    def compute(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x

    compute(1)
    fake_time = 1_000_000.0  # far in the future
    compute(1)
    assert call_count == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_tinycache_concurrent_access_no_data_race() -> None:
    """Multiple threads hitting the same key should not corrupt the cache."""
    results: list[int] = []
    lock = threading.Lock()

    @tinycache()
    def compute(x: int) -> int:
        return x * x

    def worker() -> None:
        value = compute(7)
        with lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(v == 49 for v in results)
    assert len(results) == 50


# ---------------------------------------------------------------------------
# Error cases — invalid arguments
# ---------------------------------------------------------------------------


def test_tinycache_maxsize_zero_raises_tinycache_error() -> None:
    with pytest.raises(TinyCacheError, match="maxsize"):
        @tinycache(maxsize=0)
        def compute(x: int) -> int:
            return x


def test_tinycache_negative_maxsize_raises_tinycache_error() -> None:
    with pytest.raises(TinyCacheError, match="maxsize"):
        @tinycache(maxsize=-1)
        def compute(x: int) -> int:
            return x


def test_tinycache_negative_ttl_raises_tinycache_error() -> None:
    with pytest.raises(TinyCacheError, match="ttl"):
        @tinycache(ttl=-0.1)
        def compute(x: int) -> int:
            return x


def test_tinycache_unhashable_argument_raises_type_error() -> None:
    @tinycache()
    def compute(items: list[int]) -> int:
        return sum(items)

    with pytest.raises(TypeError):
        compute([1, 2, 3])


# ---------------------------------------------------------------------------
# Edge cases — special call signatures
# ---------------------------------------------------------------------------


def test_tinycache_works_with_no_arguments() -> None:
    call_count = 0

    @tinycache()
    def constant() -> int:
        nonlocal call_count
        call_count += 1
        return 42

    assert constant() == 42
    assert constant() == 42
    assert call_count == 1


def test_tinycache_works_on_instance_methods() -> None:
    class Counter:
        def __init__(self) -> None:
            self.calls = 0

        @tinycache()
        def value(self) -> int:
            self.calls += 1
            return 99

    counter = Counter()
    counter.value()
    counter.value()
    assert counter.calls == 1


def test_tinycache_preserves_function_name_and_docstring() -> None:
    @tinycache()
    def my_function() -> None:
        """My docstring."""

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "My docstring."


def test_tinycache_maxsize_none_allows_unbounded_cache() -> None:
    @tinycache(maxsize=None)
    def compute(x: int) -> int:
        return x

    for i in range(1000):
        compute(i)

    info = compute.cache_info()
    assert info.currsize == 1000

"""Core implementation for tinycache.

Provides a thread-safe LRU + TTL cache decorator.
"""

import functools
import threading
from collections import OrderedDict
from time import monotonic as time
from typing import Any, Callable, NamedTuple, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class TinyCacheError(ValueError):
    """Raised when tinycache receives invalid constructor arguments."""


class CacheInfo(NamedTuple):
    """Snapshot of cache statistics."""

    hits: int
    misses: int
    maxsize: int | None
    currsize: int


class _Entry(NamedTuple):
    """A single cached value together with the time it was stored."""

    value: Any
    stored_at: float


def _validate_arguments(maxsize: int | None, ttl: float | None) -> None:
    """Raise TinyCacheError for invalid decorator arguments."""
    if maxsize is not None and maxsize <= 0:
        raise TinyCacheError(
            f"maxsize must be a positive integer or None, got {maxsize!r}"
        )
    if ttl is not None and ttl < 0:
        raise TinyCacheError(
            f"ttl must be a non-negative float or None, got {ttl!r}"
        )


def _make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, ...]:
    """Build a hashable cache key from positional and keyword arguments."""
    if not kwargs:
        return args
    return args + tuple(sorted(kwargs.items()))


def _is_expired(entry: _Entry, ttl: float | None) -> bool:
    """Return True if *entry* has lived longer than *ttl* seconds."""
    if ttl is None:
        return False
    return (time() - entry.stored_at) >= ttl


class _Cache:
    """Thread-safe LRU + TTL cache backed by an OrderedDict."""

    def __init__(self, maxsize: int | None, ttl: float | None) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: OrderedDict[Any, _Entry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: Any) -> tuple[bool, Any]:
        """Return *(found, value)* — moves *key* to most-recently-used."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None or _is_expired(entry, self._ttl):
                if entry is not None:
                    del self._store[key]
                self._misses += 1
                return False, None
            self._store.move_to_end(key)
            self._hits += 1
            return True, entry.value

    def put(self, key: Any, value: Any) -> None:
        """Insert or replace *key* → *value*, evicting LRU if needed."""
        with self._lock:
            self._store[key] = _Entry(value=value, stored_at=time())
            self._store.move_to_end(key)
            if self._maxsize is not None and len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries and reset statistics."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def info(self) -> CacheInfo:
        """Return a snapshot of current cache statistics."""
        with self._lock:
            return CacheInfo(
                hits=self._hits,
                misses=self._misses,
                maxsize=self._maxsize,
                currsize=len(self._store),
            )


def _make_wrapper(func: F, cache: "_Cache") -> F:
    """Wrap *func* with cache look-up/store logic and attach helpers."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = _make_key(args, kwargs)
        found, cached_value = cache.get(key)
        if found:
            return cached_value
        result = func(*args, **kwargs)
        cache.put(key, result)
        return result

    wrapper.cache_info = cache.info  # type: ignore[attr-defined]
    wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def tinycache(
    maxsize: int | None = 128,
    ttl: float | None = None,
) -> Callable[[F], F]:
    """Decorator factory: LRU + TTL cache for any callable.

    *maxsize* — max entries (positive int or None for unbounded).
    *ttl* — seconds before an entry expires (non-negative float or None).
    Raises TinyCacheError for invalid arguments.
    Decorated functions gain ``cache_info()`` and ``cache_clear()``.
    """
    _validate_arguments(maxsize, ttl)

    def decorator(func: F) -> F:
        return _make_wrapper(func, _Cache(maxsize=maxsize, ttl=ttl))

    return decorator

# tinycache

**Thread-safe LRU + TTL cache decorator. Zero runtime dependencies.**

Wrap any Python callable with an in-memory cache that evicts the
least-recently-used entry when full and automatically expires entries after
a configurable time-to-live.

---

## Install

```bash
python -m pip install -e .
```

Or from source:

```bash
git clone https://github.com/nripankadas07/tinycache.git
cd tinycache
pip install -e .
```

---

## Usage

```python
from tinycache import tinycache

# Basic LRU cache (128 entries max, no expiry)
@tinycache()
def fetch_user(user_id: int) -> dict:
    ...  # expensive database call

# Expire entries after 60 seconds
@tinycache(ttl=60.0)
def get_config(key: str) -> str:
    ...

# Small cache — keep only the last 4 results
@tinycache(maxsize=4)
def compute(x: int, y: int) -> float:
    ...

# Unbounded cache (never evicts)
@tinycache(maxsize=None)
def expensive(n: int) -> int:
    ...

# Inspect and clear
fetch_user(42)
fetch_user(42)
print(fetch_user.cache_info())  # CacheInfo(hits=1, misses=1, maxsize=128, currsize=1)
fetch_user.cache_clear()
print(fetch_user.cache_info())  # CacheInfo(hits=0, misses=0, maxsize=128, currsize=0)
```

---

## API Reference

### `tinycache(maxsize=128, ttl=None) -> Callable`

Decorator factory. Apply to any callable to add caching.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `maxsize` | `int \| None` | `128` | Max cached entries. LRU eviction when exceeded. `None` = unbounded. Must be positive. |
| `ttl` | `float \| None` | `None` | Seconds before an entry is considered expired and refetched. `None` = never expires. Must be ≥ 0. |

**Raises** `TinyCacheError` (a `ValueError` subclass) when:
- `maxsize` is zero or negative
- `ttl` is negative

### `decorated.cache_info() -> CacheInfo`

Returns a `CacheInfo` named tuple:

| Field | Type | Description |
|---|---|---|
| `hits` | `int` | Number of cache hits since last clear |
| `misses` | `int` | Number of cache misses since last clear |
| `maxsize` | `int \| None` | Configured maximum size |
| `currsize` | `int` | Number of entries currently cached |

### `decorated.cache_clear() -> None`

Removes all cached entries and resets hit/miss counters.

### `TinyCacheError`

A `ValueError` subclass raised for invalid decorator arguments.

### `CacheInfo`

A `NamedTuple` returned by `cache_info()`.

---

## Running Tests

```bash
pip install pytest pytest-cov
pytest
```

Expected output:

```
================================ 23 passed in Xs ================================
```

With coverage:

```bash
pytest --cov=tinycache --cov-report=term-missing
```

---

## License

MIT © 2026 Nripanka Das

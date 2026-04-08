"""tinycache — Thread-safe LRU + TTL cache decorator."""

from tinycache.core import CacheInfo, TinyCacheError, tinycache

__all__ = ["tinycache", "CacheInfo", "TinyCacheError"]
__version__ = "0.1.0"

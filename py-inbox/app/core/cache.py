"""Simple in-memory cache for email and calendar data."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class SimpleCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if found and not expired, None otherwise
        """
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if time.time() > expiry:
            # Expired - remove from cache
            del self._cache[key]
            logger.debug(f"[cache] Cache miss (expired): {key}")
            return None

        logger.debug(f"[cache] Cache hit: {key}")
        return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds
        """
        expiry = time.time() + ttl_seconds
        self._cache[key] = (value, expiry)
        logger.debug(f"[cache] Cached: {key} (TTL: {ttl_seconds}s)")

    def invalidate(self, key: str) -> None:
        """Remove a key from cache.
        
        Args:
            key: Cache key to remove
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"[cache] Invalidated: {key}")

    def invalidate_pattern(self, pattern: str) -> None:
        """Remove all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (simple substring match)
        """
        keys_to_remove = [k for k in self._cache if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]
        if keys_to_remove:
            logger.debug(f"[cache] Invalidated {len(keys_to_remove)} keys matching: {pattern}")

    def clear(self) -> None:
        """Clear all cached data."""
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"[cache] Cleared {count} cached items")

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total = len(self._cache)
        expired = sum(1 for _, expiry in self._cache.values() if time.time() > expiry)
        return {
            "total_keys": total,
            "expired_keys": expired,
            "active_keys": total - expired,
        }


# Global cache instance
_cache = SimpleCache()


def get_cache() -> SimpleCache:
    """Get the global cache instance."""
    return _cache


# Cache key builders
def email_list_key(user_id: str, max_results: int) -> str:
    """Build cache key for email list."""
    return f"emails:list:{user_id}:{max_results}"


def email_search_key(user_id: str, query: str, max_results: int) -> str:
    """Build cache key for email search."""
    return f"emails:search:{user_id}:{query}:{max_results}"


def email_detail_key(user_id: str, email_id: str) -> str:
    """Build cache key for email detail."""
    return f"emails:detail:{user_id}:{email_id}"


def calendar_events_key(user_id: str, time_min: str, time_max: str) -> str:
    """Build cache key for calendar events."""
    return f"calendar:events:{user_id}:{time_min}:{time_max}"


def calendar_freebusy_key(user_id: str, time_min: str, time_max: str) -> str:
    """Build cache key for calendar free/busy."""
    return f"calendar:freebusy:{user_id}:{time_min}:{time_max}"


# Cache TTL constants (in seconds)
EMAIL_LIST_TTL = 60  # 1 minute
EMAIL_SEARCH_TTL = 60  # 1 minute
EMAIL_DETAIL_TTL = 300  # 5 minutes (emails don't change often)
CALENDAR_EVENTS_TTL = 300  # 5 minutes
CALENDAR_FREEBUSY_TTL = 300  # 5 minutes


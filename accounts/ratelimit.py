"""Lightweight cache-backed rate limiting for public endpoints.

Uses Django's cache framework. With the default LocMemCache this is per-process
(best-effort across gunicorn workers); point CACHES at Redis/Memcached in
production for a shared counter. Enforcement is skipped while the test suite
runs (settings.TESTING) so cumulative counters don't bleed across tests.
"""
from django.core.cache import cache


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def hit(key, window):
    """Increment the counter for `key` (creating it with a `window`-second TTL)
    and return the new count."""
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # Key expired between add() and incr(); start a fresh window.
        cache.add(key, 1, window)
        return 1


def count(key):
    return cache.get(key, 0)


def reset(key):
    cache.delete(key)

"""Asks bot-verify whether a visitor's IP belongs to the bot its User-Agent names.

bot-verify (https://verify.goodbot-badbot.com) checks a claim against what the
bot's operator publishes: IP lists or reverse-DNS domains. The answer is
"confirmed", "refuted" or "not_checkable". Anything else (a timeout, a 429, an
unknown bot) is no answer at all, stored as NULL, never as refuted.

The IP is needed in plain text, so the question is asked while the request is
in memory; only the answer is stored.
"""
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

BOT_VERIFY_URL = os.getenv("BOT_VERIFY_URL", "https://verify.goodbot-badbot.com")
TIMEOUT_S = 2.0
# bot-verify caches reverse-DNS answers for 15 minutes; asking again sooner
# only spends its rate limit, which all of this site's calls share.
CACHE_TTL_S = 15 * 60
BOTS_TTL_S = 6 * 3600
BOTS_RETRY_S = 5 * 60
RESULTS = frozenset({"confirmed", "refuted", "not_checkable"})
# All of this site's calls share one bucket at bot-verify. A 429 is reported
# at most this often, with the count since the last report, so a flood shows
# in the log without filling it.
RATE_LIMIT_REPORT_S = 60

# goodbot-badbot keys whose bot-verify id differs. Every other key is used as
# is when bot-verify lists it.
ALIASES = {"cloudvertexbot": "google-cloudvertexbot"}


class Verifier:
    def __init__(self, base_url: str, client=None):
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._bots: frozenset[str] = frozenset()
        self._bots_until = 0.0
        self._bots_retry_at = 0.0
        self._cache: dict[tuple[str, str], tuple[float, str]] = {}
        self.max_cache_entries = 10_000
        self._limited = 0
        self._limited_reported_at = float("-inf")
        self._warn = log.warning

    def _http(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_S)
        return self._client

    async def _known_bots(self) -> frozenset[str]:
        now = time.monotonic()
        if now < self._bots_until or now < self._bots_retry_at:
            return self._bots
        try:
            resp = await self._http().get(f"{self.base_url}/v1/bots")
            if resp.status_code != 200:
                raise ValueError(f"status {resp.status_code}")
            self._bots = frozenset(bot["id"] for bot in resp.json())
            self._bots_until = now + BOTS_TTL_S
        except Exception as exc:
            log.warning("bot-verify bot list unavailable: %s", exc)
            self._bots_retry_at = now + BOTS_RETRY_S
        return self._bots

    async def verdict(self, ip: str, bot_key: str | None) -> str | None:
        """The answer for ip and goodbot-badbot's bot key, or None."""
        if not self.base_url or not bot_key or not ip:
            return None
        bot_id = ALIASES.get(bot_key, bot_key)
        if bot_id not in await self._known_bots():
            return None
        key = (ip, bot_id)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and now < cached[0]:
            return cached[1]
        try:
            resp = await self._http().get(f"{self.base_url}/v1/verify", params={"ip": ip, "bot": bot_id})
            if resp.status_code == 429:
                self._rate_limited(now)
            result = resp.json().get("result") if resp.status_code == 200 else None
        except Exception as exc:
            log.warning("bot-verify unavailable: %s", type(exc).__name__)
            return None
        if result not in RESULTS:
            return None
        if len(self._cache) >= self.max_cache_entries:
            self._evict(now)
        self._cache[key] = (now + CACHE_TTL_S, result)
        return result

    def _rate_limited(self, now: float):
        self._limited += 1
        if now - self._limited_reported_at >= RATE_LIMIT_REPORT_S:
            self._warn(f"bot-verify rate limit reached: {self._limited} lookups without an answer "
                       f"since the last report")
            self._limited = 0
            self._limited_reported_at = now

    def _evict(self, now: float):
        for key in [k for k, (until, _) in self._cache.items() if until <= now]:
            del self._cache[key]
        # Still full: drop the oldest half (dicts keep insertion order).
        if len(self._cache) >= self.max_cache_entries:
            for key in list(self._cache)[: max(1, len(self._cache) // 2)]:
                del self._cache[key]


verifier = Verifier(BOT_VERIFY_URL)

import asyncio
import logging
import time
from typing import Optional, Any, Dict
import aiohttp

logger = logging.getLogger(__name__)

class RateLimitedClient:
    """
    Base client for API interactions with built-in:
    - Concurrency limiting (Semaphore)
    - Rate limit handling (HTTP 429)
    - Exponential backoff
    """
    
    def __init__(self, name: str, max_concurrent: int = 3, base_url: str = ""):
        self.name = name
        self.base_url = base_url.rstrip('/')
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_429 = 0.0
        self._backoff_until = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """
        Execute an HTTP request with rate limiting and retries.
        """
        # Respect global backoff (if multiple threads trigger detection)
        now = time.time()
        if now < self._backoff_until:
             wait = self._backoff_until - now
             logger.warning(f"[{self.name}] Global backoff active. Waiting {wait:.1f}s...")
             await asyncio.sleep(wait)

        async with self._semaphore:
            retries = 3
            backoff = 2  # Start with 2 seconds
            
            url = f"{self.base_url}/{endpoint.lstrip('/')}" if self.base_url else endpoint

            for attempt in range(retries):
                try:
                    session = await self._get_session()
                    async with session.request(method, url, **kwargs) as response:
                        
                        # Handle Rate Limits
                        if response.status == 429:
                            retry_after = int(response.headers.get("Retry-After", backoff))
                            logger.warning(f"[{self.name}] Rate limit hit (429). Backing off for {retry_after}s.")
                            
                            # Update global backoff
                            self._backoff_until = time.time() + retry_after
                            await asyncio.sleep(retry_after)
                            
                            # Increase backoff for next loop if no header was present
                            backoff *= 2
                            continue
                            
                        # Handle Server Errors
                        if response.status >= 500:
                            logger.warning(f"[{self.name}] Server error {response.status}. Retrying in {backoff}s...")
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue

                        response.raise_for_status()
                        
                        # Return JSON or Text based on content type
                        if "application/json" in response.headers.get("Content-Type", ""):
                            return await response.json()
                        return await response.text()

                except aiohttp.ClientResponseError as e:
                    if e.status < 500 and e.status != 429:
                        # Client errors (400, 401, 404) are usually fatal
                        logger.error(f"[{self.name}] Request failed: {e}")
                        raise
                except Exception as e:
                    logger.error(f"[{self.name}] Connection error: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        raise

            logger.error(f"[{self.name}] Max retries exceeded for {url}")
            return None

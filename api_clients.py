"""Base classes for external API clients."""

import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TypeVar, Generic
from datetime import datetime, timedelta
from dataclasses import dataclass

from utils import log_error, async_retry


T = TypeVar('T')


@dataclass
class RateLimitInfo:
    """Information about API rate limits."""
    requests_per_second: float
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int = 5
    current_requests: int = 0
    reset_time: Optional[datetime] = None


class APIResponse(Generic[T]):
    """Wrapper for API responses with metadata."""
    
    def __init__(self, data: T, status_code: int, headers: Dict[str, str] = None,
                 rate_limit_info: RateLimitInfo = None, cached: bool = False):
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}
        self.rate_limit_info = rate_limit_info
        self.cached = cached
        self.timestamp = datetime.utcnow()
    
    @property
    def success(self) -> bool:
        """Check if the response was successful."""
        return 200 <= self.status_code < 300
    
    @property
    def rate_limited(self) -> bool:
        """Check if the response indicates rate limiting."""
        return self.status_code == 429


class BaseAPIClient(ABC):
    """Abstract base class for external API clients."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 rate_limit: RateLimitInfo = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.rate_limit = rate_limit or RateLimitInfo(1.0, 60, 3600)
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Session and caching
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self._request_times: List[datetime] = []
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_session(self) -> None:
        """Ensure aiohttp session is created."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                keepalive_timeout=30
            )
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self._get_default_headers()
            )
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            'User-Agent': 'ShootyBot/2.1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if self.api_key:
            headers.update(self._get_auth_headers())
        
        return headers
    
    @abstractmethod
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers (implement in subclass)."""
        pass
    
    def _get_cache_key(self, endpoint: str, params: Dict[str, Any] = None) -> str:
        """Generate cache key for request."""
        param_str = ''
        if params:
            sorted_params = sorted(params.items())
            param_str = '&'.join(f"{k}={v}" for k, v in sorted_params)
        
        return f"{endpoint}?{param_str}" if param_str else endpoint
    
    def _is_cache_valid(self, cache_key: str, ttl_seconds: int = 300) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_ttl:
            return False
        
        expiry = self._cache_ttl[cache_key] + timedelta(seconds=ttl_seconds)
        return datetime.utcnow() < expiry
    
    def _set_cache(self, cache_key: str, data: Any) -> None:
        """Set data in cache."""
        self._cache[cache_key] = data
        self._cache_ttl[cache_key] = datetime.utcnow()
    
    def _get_cache(self, cache_key: str) -> Optional[Any]:
        """Get data from cache."""
        return self._cache.get(cache_key)
    
    def _clear_expired_cache(self) -> None:
        """Clear expired cache entries."""
        now = datetime.utcnow()
        expired_keys = []
        
        for key, timestamp in self._cache_ttl.items():
            if now - timestamp > timedelta(minutes=30):  # 30 min max cache
                expired_keys.append(key)
        
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_ttl.pop(key, None)
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limits."""
        now = datetime.utcnow()
        
        # Clean old request times
        cutoff = now - timedelta(seconds=60)
        self._request_times = [t for t in self._request_times if t > cutoff]
        
        # Check rate limit
        if len(self._request_times) >= self.rate_limit.requests_per_minute:
            oldest_request = min(self._request_times)
            wait_time = 60 - (now - oldest_request).total_seconds()
            
            if wait_time > 0:
                self.logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        # Record this request
        self._request_times.append(now)
    
    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def _make_request(self, method: str, endpoint: str,
                          params: Dict[str, Any] = None,
                          data: Dict[str, Any] = None,
                          use_cache: bool = True,
                          cache_ttl: int = 300) -> APIResponse[Dict[str, Any]]:
        """Make HTTP request with rate limiting and caching."""
        await self._ensure_session()
        
        # Check cache first
        cache_key = self._get_cache_key(endpoint, params)
        if use_cache and self._is_cache_valid(cache_key, cache_ttl):
            cached_data = self._get_cache(cache_key)
            if cached_data is not None:
                return APIResponse(
                    data=cached_data,
                    status_code=200,
                    cached=True
                )
        
        # Check rate limit
        await self._check_rate_limit()
        
        # Make request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self._session.request(
                method=method,
                url=url,
                params=params,
                json=data
            ) as response:
                
                headers = dict(response.headers)
                status_code = response.status
                
                # Parse rate limit info from headers
                rate_limit_info = self._parse_rate_limit_headers(headers)
                
                # Handle different content types
                if 'application/json' in response.headers.get('content-type', ''):
                    response_data = await response.json()
                else:
                    response_data = {'text': await response.text()}
                
                # Handle rate limiting
                if status_code == 429:
                    retry_after = int(headers.get('retry-after', 60))
                    self.logger.warning(f"Rate limited, retry after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=status_code,
                        message="Rate limited"
                    )
                
                # Handle client errors
                if 400 <= status_code < 500:
                    error_msg = response_data.get('message', f"Client error: {status_code}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=status_code,
                        message=error_msg
                    )
                
                # Handle server errors
                if status_code >= 500:
                    error_msg = f"Server error: {status_code}"
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=status_code,
                        message=error_msg
                    )
                
                # Cache successful responses
                if use_cache and 200 <= status_code < 300:
                    self._set_cache(cache_key, response_data)
                
                return APIResponse(
                    data=response_data,
                    status_code=status_code,
                    headers=headers,
                    rate_limit_info=rate_limit_info
                )
                
        except aiohttp.ClientError as e:
            log_error(f"making {method} request to {endpoint}", e)
            raise
        except Exception as e:
            log_error(f"unexpected error in {method} request to {endpoint}", e)
            raise
    
    def _parse_rate_limit_headers(self, headers: Dict[str, str]) -> Optional[RateLimitInfo]:
        """Parse rate limit information from response headers (override in subclass)."""
        return None
    
    async def get(self, endpoint: str, params: Dict[str, Any] = None,
                 use_cache: bool = True, cache_ttl: int = 300) -> APIResponse[Dict[str, Any]]:
        """Make GET request."""
        return await self._make_request('GET', endpoint, params=params,
                                       use_cache=use_cache, cache_ttl=cache_ttl)

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the API is healthy."""
        pass
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._cache_ttl.clear()
        self.logger.info("API cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self._cache)
        now = datetime.utcnow()
        
        fresh_entries = sum(
            1 for timestamp in self._cache_ttl.values()
            if now - timestamp < timedelta(minutes=5)
        )
        
        return {
            'total_entries': total_entries,
            'fresh_entries': fresh_entries,
            'hit_rate': fresh_entries / max(total_entries, 1),
            'oldest_entry': min(self._cache_ttl.values()) if self._cache_ttl else None
        }

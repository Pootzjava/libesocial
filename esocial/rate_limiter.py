"""
esocial/rate_limiter.py - Premium Rate Limiter Implementation

Enterprise-grade rate limiting with multiple algorithms support:
- Token Bucket (default)
- Sliding Window Log
- Fixed Window Counter

Features:
- Thread-safe implementation
- Async support
- Integration with CircuitBreaker
- Dynamic configuration
- Metrics and monitoring
- Distributed-ready architecture
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager, contextmanager

from esocial.models import RateLimiterConfig, RateLimitResult, RateLimitAlgorithm


logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(
        self, 
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
        current_count: int = 0,
        max_count: int = 0,
        reset_time: Optional[datetime] = None
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.current_count = current_count
        self.max_count = max_count
        self.reset_time = reset_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error": "RateLimitExceeded",
            "message": str(self),
            "retry_after_seconds": self.retry_after,
            "current_count": self.current_count,
            "max_count": self.max_count,
            "reset_time": self.reset_time.isoformat() if self.reset_time else None,
            "timestamp": datetime.now().isoformat()
        }


class RateLimiterStrategy(ABC):
    """Abstract base class for rate limiting strategies."""
    
    @abstractmethod
    def acquire(self, tokens: int = 1) -> RateLimitResult:
        """Attempt to acquire tokens. Returns result with success status."""
        pass
    
    @abstractmethod
    def try_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> RateLimitResult:
        """Try to acquire tokens with optional timeout."""
        pass
    
    @abstractmethod
    def get_available_tokens(self) -> float:
        """Get current number of available tokens."""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset the rate limiter state."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        pass


class TokenBucketLimiter(RateLimiterStrategy):
    """
    Token Bucket Algorithm Implementation.
    
    Tokens are added at a constant rate up to a maximum capacity.
    Each request consumes tokens. If not enough tokens, request is rejected.
    
    Advantages:
    - Allows bursting up to bucket capacity
    - Smooth rate limiting over time
    - Simple and efficient
    """
    
    def __init__(
        self,
        capacity: int,
        refill_rate: float,  # tokens per second
        initial_tokens: Optional[int] = None
    ):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(initial_tokens if initial_tokens is not None else capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._rejected_requests = 0
        self._total_tokens_consumed = 0
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        
        tokens_to_add = elapsed * self._refill_rate
        self._tokens = min(self._capacity, self._tokens + tokens_to_add)
        self._last_refill = now
    
    def acquire(self, tokens: int = 1) -> RateLimitResult:
        """Acquire tokens from the bucket."""
        with self._lock:
            self._refill()
            self._total_requests += 1
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._successful_requests += 1
                self._total_tokens_consumed += tokens
                
                return RateLimitResult(
                    allowed=True,
                    remaining_tokens=int(self._tokens),
                    retry_after=None,
                    reset_time=datetime.now() + timedelta(seconds=(self._capacity - self._tokens) / self._refill_rate),
                    algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                    metadata={
                        "capacity": self._capacity,
                        "refill_rate": self._refill_rate,
                        "tokens_consumed": tokens
                    }
                )
            else:
                self._rejected_requests += 1
                wait_time = (tokens - self._tokens) / self._refill_rate
                
                return RateLimitResult(
                    allowed=False,
                    remaining_tokens=int(self._tokens),
                    retry_after=wait_time,
                    reset_time=datetime.now() + timedelta(seconds=wait_time),
                    algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                    metadata={
                        "capacity": self._capacity,
                        "refill_rate": self._refill_rate,
                        "requested_tokens": tokens,
                        "available_tokens": self._tokens
                    }
                )
    
    def try_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> RateLimitResult:
        """Try to acquire tokens with optional timeout."""
        if timeout is None:
            return self.acquire(tokens)
        
        start_time = time.monotonic()
        
        while True:
            result = self.acquire(tokens)
            
            if result.allowed:
                return result
            
            elapsed = time.monotonic() - start_time
            
            if elapsed >= timeout:
                return result
            
            wait_time = min(result.retry_after or 0.1, timeout - elapsed)
            time.sleep(min(wait_time, 0.1))  # Small sleep to avoid busy waiting
    
    def get_available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self._tokens
    
    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        with self._lock:
            self._tokens = float(self._capacity)
            self._last_refill = time.monotonic()
            self._total_requests = 0
            self._successful_requests = 0
            self._rejected_requests = 0
            self._total_tokens_consumed = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            self._refill()
            return {
                "algorithm": "token_bucket",
                "capacity": self._capacity,
                "refill_rate": self._refill_rate,
                "current_tokens": self._tokens,
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "rejected_requests": self._rejected_requests,
                "rejection_rate": (
                    self._rejected_requests / self._total_requests 
                    if self._total_requests > 0 else 0.0
                ),
                "total_tokens_consumed": self._total_tokens_consumed,
                "utilization": self._total_tokens_consumed / (self._total_requests * 1) if self._total_requests > 0 else 0.0
            }


class SlidingWindowLogLimiter(RateLimiterStrategy):
    """
    Sliding Window Log Algorithm Implementation.
    
    Maintains a log of timestamps for all requests within the window.
    More accurate but uses more memory.
    
    Advantages:
    - Precise rate limiting
    - No boundary issues like fixed windows
    - Handles bursts well
    """
    
    def __init__(
        self,
        max_requests: int,
        window_size: float,  # in seconds
    ):
        self._max_requests = max_requests
        self._window_size = window_size
        self._timestamps: deque = deque()
        self._lock = threading.Lock()
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._rejected_requests = 0
    
    def _clean_old_entries(self) -> None:
        """Remove timestamps outside the current window."""
        cutoff = time.monotonic() - self._window_size
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
    
    def acquire(self, tokens: int = 1) -> RateLimitResult:
        """Acquire permission for request(s)."""
        with self._lock:
            self._clean_old_entries()
            self._total_requests += 1
            
            current_count = len(self._timestamps)
            
            if current_count + tokens <= self._max_requests:
                # Add timestamp for each token
                now = time.monotonic()
                for _ in range(tokens):
                    self._timestamps.append(now)
                
                self._successful_requests += 1
                
                return RateLimitResult(
                    allowed=True,
                    remaining_tokens=self._max_requests - len(self._timestamps),
                    retry_after=None,
                    reset_time=datetime.now() + timedelta(seconds=self._window_size),
                    algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG,
                    metadata={
                        "max_requests": self._max_requests,
                        "window_size": self._window_size,
                        "current_count": len(self._timestamps)
                    }
                )
            else:
                self._rejected_requests += 1
                
                # Calculate when oldest entry will expire
                if self._timestamps:
                    oldest = self._timestamps[0]
                    wait_time = (oldest + self._window_size) - time.monotonic()
                    wait_time = max(0.0, wait_time)
                else:
                    wait_time = 0.0
                
                return RateLimitResult(
                    allowed=False,
                    remaining_tokens=self._max_requests - current_count,
                    retry_after=wait_time,
                    reset_time=datetime.now() + timedelta(seconds=wait_time),
                    algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG,
                    metadata={
                        "max_requests": self._max_requests,
                        "window_size": self._window_size,
                        "current_count": current_count,
                        "requested_tokens": tokens
                    }
                )
    
    def try_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> RateLimitResult:
        """Try to acquire with optional timeout."""
        if timeout is None:
            return self.acquire(tokens)
        
        start_time = time.monotonic()
        
        while True:
            result = self.acquire(tokens)
            
            if result.allowed:
                return result
            
            elapsed = time.monotonic() - start_time
            
            if elapsed >= timeout:
                return result
            
            wait_time = min(result.retry_after or 0.1, timeout - elapsed)
            time.sleep(min(wait_time, 0.1))
    
    def get_available_tokens(self) -> float:
        """Get available request slots."""
        with self._lock:
            self._clean_old_entries()
            return max(0, self._max_requests - len(self._timestamps))
    
    def reset(self) -> None:
        """Reset the rate limiter."""
        with self._lock:
            self._timestamps.clear()
            self._total_requests = 0
            self._successful_requests = 0
            self._rejected_requests = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            self._clean_old_entries()
            return {
                "algorithm": "sliding_window_log",
                "max_requests": self._max_requests,
                "window_size": self._window_size,
                "current_count": len(self._timestamps),
                "available_slots": max(0, self._max_requests - len(self._timestamps)),
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "rejected_requests": self._rejected_requests,
                "rejection_rate": (
                    self._rejected_requests / self._total_requests 
                    if self._total_requests > 0 else 0.0
                )
            }


class FixedWindowCounterLimiter(RateLimiterStrategy):
    """
    Fixed Window Counter Algorithm Implementation.
    
    Divides time into fixed windows and counts requests per window.
    Simple but can allow 2x burst at window boundaries.
    
    Advantages:
    - Very simple implementation
    - Memory efficient
    - Good for high-throughput scenarios
    """
    
    def __init__(
        self,
        max_requests: int,
        window_size: float,  # in seconds
    ):
        self._max_requests = max_requests
        self._window_size = window_size
        self._counter = 0
        self._window_start = time.monotonic()
        self._lock = threading.Lock()
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._rejected_requests = 0
    
    def _reset_if_needed(self) -> None:
        """Reset counter if we're in a new window."""
        now = time.monotonic()
        if now - self._window_start >= self._window_size:
            self._window_start = now
            self._counter = 0
    
    def acquire(self, tokens: int = 1) -> RateLimitResult:
        """Acquire permission for request(s)."""
        with self._lock:
            self._reset_if_needed()
            self._total_requests += 1
            
            if self._counter + tokens <= self._max_requests:
                self._counter += tokens
                self._successful_requests += 1
                
                reset_time = datetime.now() + timedelta(
                    seconds=self._window_size - (time.monotonic() - self._window_start)
                )
                
                return RateLimitResult(
                    allowed=True,
                    remaining_tokens=self._max_requests - self._counter,
                    retry_after=None,
                    reset_time=reset_time,
                    algorithm=RateLimitAlgorithm.FIXED_WINDOW_COUNTER,
                    metadata={
                        "max_requests": self._max_requests,
                        "window_size": self._window_size,
                        "current_count": self._counter,
                        "window_start": self._window_start
                    }
                )
            else:
                self._rejected_requests += 1
                
                wait_time = self._window_size - (time.monotonic() - self._window_start)
                wait_time = max(0.0, wait_time)
                
                return RateLimitResult(
                    allowed=False,
                    remaining_tokens=self._max_requests - self._counter,
                    retry_after=wait_time,
                    reset_time=datetime.now() + timedelta(seconds=wait_time),
                    algorithm=RateLimitAlgorithm.FIXED_WINDOW_COUNTER,
                    metadata={
                        "max_requests": self._max_requests,
                        "window_size": self._window_size,
                        "current_count": self._counter,
                        "requested_tokens": tokens
                    }
                )
    
    def try_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> RateLimitResult:
        """Try to acquire with optional timeout."""
        if timeout is None:
            return self.acquire(tokens)
        
        start_time = time.monotonic()
        
        while True:
            result = self.acquire(tokens)
            
            if result.allowed:
                return result
            
            elapsed = time.monotonic() - start_time
            
            if elapsed >= timeout:
                return result
            
            wait_time = min(result.retry_after or 0.1, timeout - elapsed)
            time.sleep(min(wait_time, 0.1))
    
    def get_available_tokens(self) -> float:
        """Get available request slots."""
        with self._lock:
            self._reset_if_needed()
            return max(0, self._max_requests - self._counter)
    
    def reset(self) -> None:
        """Reset the rate limiter."""
        with self._lock:
            self._counter = 0
            self._window_start = time.monotonic()
            self._total_requests = 0
            self._successful_requests = 0
            self._rejected_requests = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            self._reset_if_needed()
            return {
                "algorithm": "fixed_window_counter",
                "max_requests": self._max_requests,
                "window_size": self._window_size,
                "current_count": self._counter,
                "window_start": self._window_start,
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "rejected_requests": self._rejected_requests,
                "rejection_rate": (
                    self._rejected_requests / self._total_requests 
                    if self._total_requests > 0 else 0.0
                )
            }


@dataclass
class RateLimiterState:
    """Represents the current state of a rate limiter."""
    
    algorithm: RateLimitAlgorithm
    available_tokens: float
    max_tokens: int
    last_request_time: Optional[datetime] = None
    total_requests: int = 0
    rejected_requests: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "algorithm": self.algorithm.value,
            "available_tokens": self.available_tokens,
            "max_tokens": self.max_tokens,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "rejection_rate": self.rejected_requests / self.total_requests if self.total_requests > 0 else 0.0
        }


class RateLimiter:
    """
    Premium Rate Limiter with multiple algorithm support.
    
    Features:
    - Pluggable strategy pattern
    - Thread-safe operations
    - Async support
    - Integration with CircuitBreaker
    - Comprehensive metrics
    - Dynamic reconfiguration
    """
    
    def __init__(
        self,
        config: Optional[RateLimiterConfig] = None,
        strategy: Optional[RateLimiterStrategy] = None
    ):
        self._config = config or RateLimiterConfig()
        self._strategy = strategy or self._create_default_strategy()
        self._lock = threading.Lock()
        self._last_request_time: Optional[datetime] = None
        
        # For circuit breaker integration
        self._consecutive_failures = 0
        self._last_failure_time: Optional[datetime] = None
    
    def _create_default_strategy(self) -> RateLimiterStrategy:
        """Create default strategy based on config."""
        if self._config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            return TokenBucketLimiter(
                capacity=self._config.max_requests,
                refill_rate=self._config.refill_rate or (self._config.max_requests / self._config.window_size)
            )
        elif self._config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG:
            return SlidingWindowLogLimiter(
                max_requests=self._config.max_requests,
                window_size=self._config.window_size
            )
        else:  # FIXED_WINDOW_COUNTER
            return FixedWindowCounterLimiter(
                max_requests=self._config.max_requests,
                window_size=self._config.window_size
            )
    
    def acquire(self, tokens: int = 1) -> RateLimitResult:
        """
        Acquire tokens/permission for request(s).
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
        
        Returns:
            RateLimitResult with success status and metadata
        """
        with self._lock:
            result = self._strategy.acquire(tokens)
            
            if result.allowed:
                self._last_request_time = datetime.now()
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                self._last_failure_time = datetime.now()
            
            return result
    
    def try_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> RateLimitResult:
        """
        Try to acquire tokens with optional timeout.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait in seconds
        
        Returns:
            RateLimitResult with success status
        """
        result = self._strategy.try_acquire(tokens, timeout)
        
        if result.allowed:
            with self._lock:
                self._last_request_time = datetime.now()
                self._consecutive_failures = 0
        
        return result
    
    def check(self) -> RateLimitResult:
        """Check if a request would be allowed without consuming tokens."""
        # For most strategies, we need to actually try
        # This is a non-destructive check
        available = self._strategy.get_available_tokens()
        
        return RateLimitResult(
            allowed=available >= 1,
            remaining_tokens=int(available),
            retry_after=None if available >= 1 else 1.0 / (self._config.refill_rate or 1.0),
            reset_time=datetime.now() + timedelta(seconds=self._config.window_size),
            algorithm=self._config.algorithm,
            metadata={"check_only": True}
        )
    
    def reset(self) -> None:
        """Reset the rate limiter state."""
        with self._lock:
            self._strategy.reset()
            self._last_request_time = None
            self._consecutive_failures = 0
            self._last_failure_time = None
    
    def get_state(self) -> RateLimiterState:
        """Get current rate limiter state."""
        stats = self._strategy.get_stats()
        
        return RateLimiterState(
            algorithm=self._config.algorithm,
            available_tokens=self._strategy.get_available_tokens(),
            max_tokens=self._config.max_requests,
            last_request_time=self._last_request_time,
            total_requests=stats.get("total_requests", 0),
            rejected_requests=stats.get("rejected_requests", 0)
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        stats = self._strategy.get_stats()
        
        return {
            **stats,
            "last_request_time": self._last_request_time.isoformat() if self._last_request_time else None,
            "consecutive_failures": self._consecutive_failures,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "config": {
                "algorithm": self._config.algorithm.value,
                "max_requests": self._config.max_requests,
                "window_size": self._config.window_size,
                "refill_rate": self._config.refill_rate
            }
        }
    
    def reconfigure(self, config: RateLimiterConfig) -> None:
        """Dynamically reconfigure the rate limiter."""
        with self._lock:
            self._config = config
            self._strategy = self._create_default_strategy()
            logger.info(f"Rate limiter reconfigured: {config}")
    
    @asynccontextmanager
    async def async_acquire(self, tokens: int = 1):
        """Async context manager for acquiring tokens."""
        result = self.acquire(tokens)
        
        if not result.allowed:
            raise RateLimitExceeded(
                message="Rate limit exceeded",
                retry_after=result.retry_after,
                current_count=self._config.max_requests - int(result.remaining_tokens),
                max_count=self._config.max_requests,
                reset_time=result.reset_time
            )
        
        try:
            yield result
        finally:
            pass  # Cleanup if needed
    
    @contextmanager
    def context_acquire(self, tokens: int = 1):
        """Context manager for acquiring tokens."""
        result = self.acquire(tokens)
        
        if not result.allowed:
            raise RateLimitExceeded(
                message="Rate limit exceeded",
                retry_after=result.retry_after,
                current_count=self._config.max_requests - int(result.remaining_tokens),
                max_count=self._config.max_requests,
                reset_time=result.reset_time
            )
        
        try:
            yield result
        finally:
            pass  # Cleanup if needed


class AsyncRateLimiter:
    """
    Async-compatible rate limiter.
    
    Wraps synchronous rate limiter with async support.
    """
    
    def __init__(
        self,
        config: Optional[RateLimiterConfig] = None,
        strategy: Optional[RateLimiterStrategy] = None
    ):
        self._sync_limiter = RateLimiter(config, strategy)
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> RateLimitResult:
        """Async acquire tokens."""
        async with self._lock:
            return self._sync_limiter.acquire(tokens)
    
    async def try_acquire(
        self, 
        tokens: int = 1, 
        timeout: Optional[float] = None
    ) -> RateLimitResult:
        """Async try acquire with timeout."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                self._sync_limiter.try_acquire, 
                tokens, 
                timeout
            )
    
    async def reset(self) -> None:
        """Async reset."""
        async with self._lock:
            self._sync_limiter.reset()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics (synchronous operation)."""
        return self._sync_limiter.get_stats()
    
    @asynccontextmanager
    async def acquire_context(self, tokens: int = 1):
        """Async context manager for rate limiting."""
        result = await self.acquire(tokens)
        
        if not result.allowed:
            raise RateLimitExceeded(
                message="Rate limit exceeded",
                retry_after=result.retry_after,
                current_count=self._config.max_requests - int(result.remaining_tokens),
                max_count=self._config.max_requests,
                reset_time=result.reset_time
            )
        
        try:
            yield result
        finally:
            pass


def create_rate_limiter_from_config(config: RateLimiterConfig) -> RateLimiter:
    """Factory function to create rate limiter from config."""
    return RateLimiter(config=config)


def create_rate_limiter(
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET,
    max_requests: int = 100,
    window_size: float = 60.0,
    refill_rate: Optional[float] = None
) -> RateLimiter:
    """
    Factory function to create rate limiter with common parameters.
    
    Args:
        algorithm: Rate limiting algorithm to use
        max_requests: Maximum requests per window
        window_size: Window size in seconds
        refill_rate: Token refill rate (for token bucket)
    
    Returns:
        Configured RateLimiter instance
    """
    config = RateLimiterConfig(
        algorithm=algorithm,
        max_requests=max_requests,
        window_size=window_size,
        refill_rate=refill_rate
    )
    
    return create_rate_limiter_from_config(config)

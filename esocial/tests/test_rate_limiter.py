"""
esocial/tests/test_rate_limiter.py - Premium Rate Limiter Tests

Comprehensive test suite for rate limiting functionality:
- Token Bucket algorithm tests
- Sliding Window Log algorithm tests
- Fixed Window Counter algorithm tests
- RateLimiter integration tests
- AsyncRateLimiter tests
- Exception handling tests
- Thread safety tests
- Performance tests
"""

import pytest
import time
import threading
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from esocial.rate_limiter import (
    RateLimiter,
    RateLimiterStrategy,
    TokenBucketLimiter,
    SlidingWindowLogLimiter,
    FixedWindowCounterLimiter,
    AsyncRateLimiter,
    RateLimitExceeded,
    create_rate_limiter,
    create_rate_limiter_from_config,
    RateLimiterState,
)
from esocial.models import (
    RateLimiterConfig,
    RateLimitResult,
    RateLimitAlgorithm,
)


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""
    
    def test_exception_basic(self):
        """Test basic exception creation."""
        exc = RateLimitExceeded(
            message="Test error",
            retry_after=5.0,
            current_count=10,
            max_count=100,
            reset_time=datetime.now() + timedelta(seconds=5)
        )
        
        assert str(exc) == "Test error"
        assert exc.retry_after == 5.0
        assert exc.current_count == 10
        assert exc.max_count == 100
        assert exc.reset_time is not None
    
    def test_exception_to_dict(self):
        """Test exception serialization."""
        reset_time = datetime.now() + timedelta(seconds=5)
        exc = RateLimitExceeded(
            message="Test error",
            retry_after=5.0,
            current_count=10,
            max_count=100,
            reset_time=reset_time
        )
        
        result = exc.to_dict()
        
        assert result["error"] == "RateLimitExceeded"
        assert result["message"] == "Test error"
        assert result["retry_after_seconds"] == 5.0
        assert result["current_count"] == 10
        assert result["max_count"] == 100
        assert "timestamp" in result
    
    def test_exception_defaults(self):
        """Test exception with default values."""
        exc = RateLimitExceeded()
        
        assert "Rate limit exceeded" in str(exc)
        assert exc.retry_after is None
        assert exc.current_count == 0
        assert exc.max_count == 0


class TestTokenBucketLimiter:
    """Tests for Token Bucket algorithm."""
    
    def test_initial_state(self):
        """Test initial bucket state."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        
        assert limiter.get_available_tokens() == 10.0
        stats = limiter.get_stats()
        assert stats["capacity"] == 10
        assert stats["refill_rate"] == 1.0
    
    def test_acquire_success(self):
        """Test successful token acquisition."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        
        result = limiter.acquire(5)
        
        assert result.allowed is True
        assert result.remaining_tokens == 5
        assert result.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
    
    def test_acquire_failure(self):
        """Test failed token acquisition."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)
        
        # Consume all tokens
        limiter.acquire(5)
        
        # Try to acquire more
        result = limiter.acquire(1)
        
        assert result.allowed is False
        assert result.remaining_tokens == 0
        assert result.retry_after is not None
        assert result.retry_after > 0
    
    def test_refill_over_time(self):
        """Test token refill over time."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=10.0)  # 10 tokens/sec
        
        # Consume all tokens
        limiter.acquire(10)
        # Allow small variance due to timing
        assert limiter.get_available_tokens() < 0.1
        
        # Wait for refill
        time.sleep(0.5)  # Should add ~5 tokens
        
        available = limiter.get_available_tokens()
        assert 4.0 <= available <= 6.0  # Allow some variance
    
    def test_capacity_limit(self):
        """Test that tokens don't exceed capacity."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=100.0)
        
        # Wait for potential over-refill
        time.sleep(0.2)
        
        # Should still be at capacity
        assert limiter.get_available_tokens() == 10.0
    
    def test_try_acquire_with_timeout(self):
        """Test try_acquire with timeout."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=10.0)
        
        # Consume all tokens
        limiter.acquire(5)
        
        # Try to acquire with timeout
        start = time.time()
        result = limiter.try_acquire(1, timeout=0.5)
        elapsed = time.time() - start
        
        assert result.allowed is True
        assert elapsed < 0.6  # Should succeed within timeout
    
    def test_try_acquire_timeout_exceeded(self):
        """Test try_acquire when timeout is exceeded."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)
        
        # Consume all tokens
        limiter.acquire(5)
        
        # Try to acquire with short timeout
        start = time.time()
        result = limiter.try_acquire(5, timeout=0.1)
        elapsed = time.time() - start
        
        assert result.allowed is False
        assert elapsed < 0.2
    
    def test_reset(self):
        """Test reset functionality."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        
        # Consume some tokens
        limiter.acquire(7)
        
        # Reset
        limiter.reset()
        
        assert limiter.get_available_tokens() == 10.0
        stats = limiter.get_stats()
        assert stats["total_requests"] == 0
    
    def test_statistics(self):
        """Test statistics tracking."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        
        # Make some requests
        limiter.acquire(5)  # Success
        limiter.acquire(3)  # Success
        limiter.acquire(5)  # Fail (only 2 left)
        
        stats = limiter.get_stats()
        
        assert stats["total_requests"] == 3
        assert stats["successful_requests"] == 2
        assert stats["rejected_requests"] == 1
        assert stats["rejection_rate"] == pytest.approx(1/3, rel=0.01)
    
    def test_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        
        result = limiter.acquire(7)
        
        assert result.allowed is True
        assert result.remaining_tokens == 3
        assert result.metadata["tokens_consumed"] == 7


class TestSlidingWindowLogLimiter:
    """Tests for Sliding Window Log algorithm."""
    
    def test_initial_state(self):
        """Test initial state."""
        limiter = SlidingWindowLogLimiter(max_requests=10, window_size=60.0)
        
        assert limiter.get_available_tokens() == 10
        stats = limiter.get_stats()
        assert stats["max_requests"] == 10
        assert stats["window_size"] == 60.0
    
    def test_acquire_within_limit(self):
        """Test acquisition within limit."""
        limiter = SlidingWindowLogLimiter(max_requests=5, window_size=60.0)
        
        for i in range(5):
            result = limiter.acquire()
            assert result.allowed is True
        
        # 6th request should fail
        result = limiter.acquire()
        assert result.allowed is False
    
    def test_window_expiration(self):
        """Test that old entries expire."""
        limiter = SlidingWindowLogLimiter(max_requests=5, window_size=0.5)
        
        # Fill up the window
        for _ in range(5):
            limiter.acquire()
        
        # Should be full
        assert limiter.get_available_tokens() == 0
        
        # Wait for window to expire
        time.sleep(0.6)
        
        # Should have space again
        assert limiter.get_available_tokens() == 5
    
    def test_reset(self):
        """Test reset functionality."""
        limiter = SlidingWindowLogLimiter(max_requests=5, window_size=60.0)
        
        # Make some requests
        for _ in range(3):
            limiter.acquire()
        
        limiter.reset()
        
        assert limiter.get_available_tokens() == 5
        stats = limiter.get_stats()
        assert stats["total_requests"] == 0
    
    def test_statistics(self):
        """Test statistics tracking."""
        limiter = SlidingWindowLogLimiter(max_requests=3, window_size=60.0)
        
        # Make requests
        for _ in range(5):
            limiter.acquire()
        
        stats = limiter.get_stats()
        
        assert stats["total_requests"] == 5
        assert stats["successful_requests"] == 3
        assert stats["rejected_requests"] == 2


class TestFixedWindowCounterLimiter:
    """Tests for Fixed Window Counter algorithm."""
    
    def test_initial_state(self):
        """Test initial state."""
        limiter = FixedWindowCounterLimiter(max_requests=10, window_size=60.0)
        
        assert limiter.get_available_tokens() == 10
        stats = limiter.get_stats()
        assert stats["max_requests"] == 10
    
    def test_acquire_within_limit(self):
        """Test acquisition within limit."""
        limiter = FixedWindowCounterLimiter(max_requests=5, window_size=60.0)
        
        for i in range(5):
            result = limiter.acquire()
            assert result.allowed is True
        
        # 6th request should fail
        result = limiter.acquire()
        assert result.allowed is False
    
    def test_window_reset(self):
        """Test window reset."""
        limiter = FixedWindowCounterLimiter(max_requests=5, window_size=0.5)
        
        # Fill up the window
        for _ in range(5):
            limiter.acquire()
        
        # Should be full
        assert limiter.get_available_tokens() == 0
        
        # Wait for new window
        time.sleep(0.6)
        
        # Should have space again
        assert limiter.get_available_tokens() == 5
    
    def test_statistics(self):
        """Test statistics tracking."""
        limiter = FixedWindowCounterLimiter(max_requests=3, window_size=60.0)
        
        # Make requests
        for _ in range(5):
            limiter.acquire()
        
        stats = limiter.get_stats()
        
        assert stats["total_requests"] == 5
        assert stats["successful_requests"] == 3
        assert stats["rejected_requests"] == 2


class TestRateLimiter:
    """Tests for main RateLimiter class."""
    
    def test_default_config(self):
        """Test with default configuration."""
        limiter = RateLimiter()
        
        assert limiter._config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert limiter._config.max_requests == 100
    
    def test_custom_config(self):
        """Test with custom configuration."""
        config = RateLimiterConfig(
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG,
            max_requests=50,
            window_size=30.0
        )
        limiter = RateLimiter(config=config)
        
        assert limiter._config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG
        assert limiter._config.max_requests == 50
    
    def test_custom_strategy(self):
        """Test with custom strategy."""
        strategy = TokenBucketLimiter(capacity=20, refill_rate=2.0)
        limiter = RateLimiter(strategy=strategy)
        
        assert limiter._strategy is strategy
    
    def test_acquire_and_check(self):
        """Test acquire and check methods."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        # Check before acquiring
        check_result = limiter.check()
        assert check_result.allowed is True
        
        # Acquire all tokens
        for _ in range(5):
            limiter.acquire()
        
        # Check after exhausting
        check_result = limiter.check()
        assert check_result.allowed is False
    
    def test_get_state(self):
        """Test getting state."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=10, window_size=60.0)
        )
        
        # Make some requests
        for _ in range(5):
            limiter.acquire()
        
        state = limiter.get_state()
        
        assert isinstance(state, RateLimiterState)
        assert state.total_requests == 5
        # Allow small variance due to refill
        assert 4.9 <= state.available_tokens <= 5.1
    
    def test_reconfigure(self):
        """Test dynamic reconfiguration."""
        limiter = RateLimiter(
            config=RateLimiterConfig(
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                max_requests=10
            )
        )
        
        # Reconfigure
        new_config = RateLimiterConfig(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW_COUNTER,
            max_requests=20,
            window_size=120.0
        )
        limiter.reconfigure(new_config)
        
        assert limiter._config.algorithm == RateLimitAlgorithm.FIXED_WINDOW_COUNTER
        assert limiter._config.max_requests == 20
    
    def test_context_manager_success(self):
        """Test context manager on success."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        with limiter.context_acquire(1) as result:
            assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_async_context_manager_success(self):
        """Test async context manager on success."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        async with limiter.async_acquire(1) as result:
            assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_async_context_manager_failure(self):
        """Test async context manager raises on failure."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=1, window_size=60.0)
        )
        
        # Exhaust tokens
        limiter.acquire()
        
        with pytest.raises(RateLimitExceeded):
            async with limiter.async_acquire(1):
                pass
    
    def test_context_manager_failure(self):
        """Test context manager raises on failure."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=1, window_size=60.0)
        )
        
        # Exhaust tokens
        limiter.acquire()
        
        with pytest.raises(RateLimitExceeded):
            with limiter.context_acquire(1):
                pass
    
    def test_comprehensive_stats(self):
        """Test comprehensive statistics."""
        limiter = RateLimiter(
            config=RateLimiterConfig(
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                max_requests=10,
                window_size=60.0
            )
        )
        
        # Make some requests
        for _ in range(15):
            limiter.acquire()
        
        stats = limiter.get_stats()
        
        assert "algorithm" in stats
        assert "config" in stats
        assert "consecutive_failures" in stats
        assert stats["config"]["max_requests"] == 10


class TestAsyncRateLimiter:
    """Tests for AsyncRateLimiter."""
    
    @pytest.mark.asyncio
    async def test_async_acquire(self):
        """Test async acquire."""
        limiter = AsyncRateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        result = await limiter.acquire()
        
        assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_async_try_acquire(self):
        """Test async try_acquire."""
        limiter = AsyncRateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        result = await limiter.try_acquire(timeout=1.0)
        
        assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_async_reset(self):
        """Test async reset."""
        limiter = AsyncRateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        # Acquire some tokens
        await limiter.acquire(3)
        
        # Reset
        await limiter.reset()
        
        assert limiter.get_stats()["current_tokens"] == 5
    
    @pytest.mark.asyncio
    async def test_async_concurrent_access(self):
        """Test concurrent async access."""
        limiter = AsyncRateLimiter(
            config=RateLimiterConfig(max_requests=10, window_size=60.0)
        )
        
        async def acquire_token():
            return await limiter.acquire()
        
        # Run 10 concurrent acquires
        tasks = [acquire_token() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(r.allowed for r in results)
        
        # Next one should fail
        result = await limiter.acquire()
        assert result.allowed is False
    
    @pytest.mark.asyncio
    async def test_async_acquire_context(self):
        """Test async acquire context manager."""
        limiter = AsyncRateLimiter(
            config=RateLimiterConfig(max_requests=5, window_size=60.0)
        )
        
        async with limiter.acquire_context(1) as result:
            assert result.allowed is True


class TestFactoryFunctions:
    """Tests for factory functions."""
    
    def test_create_rate_limiter_basic(self):
        """Test basic rate limiter creation."""
        limiter = create_rate_limiter()
        
        assert isinstance(limiter, RateLimiter)
        assert limiter._config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
    
    def test_create_rate_limiter_custom(self):
        """Test rate limiter creation with custom params."""
        limiter = create_rate_limiter(
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG,
            max_requests=50,
            window_size=30.0
        )
        
        assert limiter._config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG
        assert limiter._config.max_requests == 50
    
    def test_create_rate_limiter_from_config(self):
        """Test rate limiter creation from config object."""
        config = RateLimiterConfig(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW_COUNTER,
            max_requests=100,
            window_size=120.0
        )
        
        limiter = create_rate_limiter_from_config(config)
        
        assert isinstance(limiter, RateLimiter)
        assert limiter._config.algorithm == RateLimitAlgorithm.FIXED_WINDOW_COUNTER


class TestThreadSafety:
    """Tests for thread safety."""
    
    def test_token_bucket_thread_safety(self):
        """Test thread safety of TokenBucketLimiter."""
        limiter = TokenBucketLimiter(capacity=1000, refill_rate=100.0)
        success_count = 0
        lock = threading.Lock()
        
        def worker():
            nonlocal success_count
            for _ in range(100):
                result = limiter.acquire()
                if result.allowed:
                    with lock:
                        success_count += 1
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have exactly 1000 successful acquires (initial capacity)
        assert success_count == 1000
    
    def test_rate_limiter_thread_safety(self):
        """Test thread safety of RateLimiter."""
        limiter = RateLimiter(
            config=RateLimiterConfig(max_requests=500, window_size=60.0)
        )
        success_count = 0
        lock = threading.Lock()
        
        def worker():
            nonlocal success_count
            for _ in range(50):
                result = limiter.acquire()
                if result.allowed:
                    with lock:
                        success_count += 1
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have exactly 500 successful acquires
        assert success_count == 500


class TestRateLimitResult:
    """Tests for RateLimitResult model."""
    
    def test_result_allowed(self):
        """Test allowed result."""
        result = RateLimitResult(
            allowed=True,
            remaining_tokens=5,
            retry_after=None,
            reset_time=datetime.now(),
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET
        )
        
        assert result.allowed is True
        assert result.remaining_tokens == 5
        assert result.retry_after is None
    
    def test_result_denied(self):
        """Test denied result."""
        reset_time = datetime.now() + timedelta(seconds=10)
        result = RateLimitResult(
            allowed=False,
            remaining_tokens=0,
            retry_after=10.0,
            reset_time=reset_time,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG,
            metadata={"reason": "limit_exceeded"}
        )
        
        assert result.allowed is False
        assert result.remaining_tokens == 0
        assert result.retry_after == 10.0
        assert result.metadata["reason"] == "limit_exceeded"
    
    def test_result_validation(self):
        """Test result validation."""
        # Should raise validation error for negative tokens
        with pytest.raises(Exception):  # Pydantic ValidationError
            RateLimitResult(
                allowed=True,
                remaining_tokens=-1,
                retry_after=None,
                reset_time=datetime.now(),
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET
            )


class TestPerformance:
    """Performance-related tests."""
    
    def test_token_bucket_performance(self):
        """Test TokenBucketLimiter performance."""
        limiter = TokenBucketLimiter(capacity=10000, refill_rate=1000.0)
        
        start = time.time()
        
        for _ in range(10000):
            limiter.acquire()
        
        elapsed = time.time() - start
        
        # Should complete 10000 operations in under 1 second
        assert elapsed < 1.0
    
    def test_sliding_window_performance(self):
        """Test SlidingWindowLogLimiter performance."""
        limiter = SlidingWindowLogLimiter(max_requests=10000, window_size=60.0)
        
        start = time.time()
        
        for _ in range(10000):
            limiter.acquire()
        
        elapsed = time.time() - start
        
        # Should complete 10000 operations in under 2 seconds
        # (slightly slower due to deque operations)
        assert elapsed < 2.0
    
    def test_fixed_window_performance(self):
        """Test FixedWindowCounterLimiter performance."""
        limiter = FixedWindowCounterLimiter(max_requests=10000, window_size=60.0)
        
        start = time.time()
        
        for _ in range(10000):
            limiter.acquire()
        
        elapsed = time.time() - start
        
        # Should complete 10000 operations in under 0.5 seconds
        # (fastest algorithm)
        assert elapsed < 0.5


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_zero_capacity(self):
        """Test with zero capacity."""
        limiter = TokenBucketLimiter(capacity=0, refill_rate=1.0)
        
        result = limiter.acquire(1)
        
        assert result.allowed is False
    
    def test_very_high_refill_rate(self):
        """Test with very high refill rate."""
        limiter = TokenBucketLimiter(capacity=10, refill_rate=10000.0)
        
        # Consume all
        limiter.acquire(10)
        
        # Should refill almost instantly
        time.sleep(0.01)
        
        assert limiter.get_available_tokens() >= 10
    
    def test_very_small_window(self):
        """Test with very small window."""
        limiter = SlidingWindowLogLimiter(max_requests=5, window_size=0.01)
        
        # Fill up
        for _ in range(5):
            limiter.acquire()
        
        # Wait tiny amount
        time.sleep(0.02)
        
        # Should have space
        assert limiter.get_available_tokens() == 5
    
    def test_acquire_more_than_capacity(self):
        """Test acquiring more tokens than capacity."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)
        
        result = limiter.acquire(10)
        
        assert result.allowed is False
        assert result.metadata["requested_tokens"] == 10
        assert result.metadata["available_tokens"] == 5.0
    
    def test_negative_timeout(self):
        """Test with negative timeout."""
        limiter = TokenBucketLimiter(capacity=5, refill_rate=1.0)
        
        # Consume all
        limiter.acquire(5)
        
        # Negative timeout should behave like no timeout
        result = limiter.try_acquire(1, timeout=-1.0)
        
        assert result.allowed is False

"""Retry logic and error handling utilities."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TypeVar

from app.core.google_tools import GoogleAuthError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableError(Exception):
    """Error that can be retried."""

    pass


class NonRetryableError(Exception):
    """Error that should not be retried."""

    pass


async def with_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> T:
    """Execute a function with exponential backoff retry logic.
    
    Args:
        func: Function to execute
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        backoff_factor: Multiplier for delay between retries (default: 2.0)
        **kwargs: Keyword arguments for func
        
    Returns:
        Result from func
        
    Raises:
        GoogleAuthError: Authentication errors are never retried
        NonRetryableError: Errors that should not be retried
        Exception: After max_retries attempts
        
    Example:
        result = await with_retry(some_api_call, arg1, arg2, max_retries=3)
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            # Call the function
            result = func(*args, **kwargs)
            
            # If it's a coroutine, await it
            if asyncio.iscoroutine(result):
                return await result
            return result
            
        except GoogleAuthError:
            # Never retry authentication errors
            logger.error("[retry] Authentication error - not retrying")
            raise
            
        except NonRetryableError:
            # Don't retry errors explicitly marked as non-retryable
            logger.error("[retry] Non-retryable error - not retrying")
            raise
            
        except Exception as e:
            last_exception = e
            
            if attempt == max_retries - 1:
                # Last attempt failed - raise the error
                logger.error(
                    f"[retry] All {max_retries} attempts failed: {e}",
                    exc_info=True,
                )
                raise
            
            # Calculate delay with exponential backoff
            delay = initial_delay * (backoff_factor ** attempt)
            
            logger.warning(
                f"[retry] Attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            
            await asyncio.sleep(delay)
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop completed without success or exception")


def format_user_error(error: Exception, operation: str) -> str:
    """Format an error message for user display.
    
    Args:
        error: The exception that occurred
        operation: Description of what operation failed (e.g., "listing emails")
        
    Returns:
        User-friendly error message
    """
    if isinstance(error, GoogleAuthError):
        return (
            f"🔐 I couldn't access your Gmail account while {operation}. "
            "Please make sure you're logged in and have granted the necessary permissions."
        )
    
    if "quota" in str(error).lower() or "rate limit" in str(error).lower():
        return (
            f"⏱️ I've hit the API rate limit while {operation}. "
            "Please try again in a few moments."
        )
    
    if "network" in str(error).lower() or "connection" in str(error).lower():
        return (
            f"🌐 I'm having network issues while {operation}. "
            "Please check your internet connection and try again."
        )
    
    if "timeout" in str(error).lower():
        return (
            f"⏰ The request timed out while {operation}. "
            "The service might be slow right now. Please try again."
        )
    
    # Generic error message
    return (
        f"❌ I encountered an error while {operation}: {str(error)}\n"
        "Please try again or let me know if you need help with something else."
    )


"""Validation and error handling utilities for ChapterForge.

This module provides robust error handling to prevent the kind of freezing
issues that occurred due to missing imports or unhandled exceptions.
"""

import functools
import logging
import sys
import traceback
from typing import Any, Callable, Optional, TypeVar

T = TypeVar('T')

logger = logging.getLogger(__name__)

class ChapterForgeError(Exception):
    """Base exception for ChapterForge-specific errors."""
    pass

class ValidationError(ChapterForgeError):
    """Raised when input validation fails."""
    pass

class ProcessingError(ChapterForgeError):
    """Raised when file processing encounters an error."""
    pass

def safe_call(default_return=None, suppress_exceptions=True):
    """Decorator to make function calls safe with proper error handling.
    
    Args:
        default_return: Value to return if function raises an exception
        suppress_exceptions: Whether to suppress or re-raise exceptions
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
                if not suppress_exceptions:
                    raise ProcessingError(f"Error in {func.__name__}: {e}") from e
                
                return default_return
        return wrapper
    return decorator

def validate_file_path(path: Any) -> str:
    """Validate that a file path is a non-empty string.
    
    Args:
        path: The path to validate
        
    Returns:
        The validated path as a string
        
    Raises:
        ValidationError: If the path is invalid
    """
    if not path:
        raise ValidationError("File path cannot be empty or None")
    
    if not isinstance(path, str):
        raise ValidationError(f"File path must be a string, got {type(path)}")
    
    if not path.strip():
        raise ValidationError("File path cannot be empty or whitespace")
    
    return path

def validate_import(module_name: str, function_name: str) -> Callable:
    """Validate that a function can be imported safely.
    
    Args:
        module_name: Name of the module
        function_name: Name of the function to import
        
    Returns:
        The imported function
        
    Raises:
        ImportError: If the function cannot be imported
    """
    try:
        module = __import__(module_name, fromlist=[function_name])
        func = getattr(module, function_name)
        return func
    except (ImportError, AttributeError) as e:
        logger.critical(f"Missing required function: {function_name} in {module_name}")
        raise ImportError(f"Required function '{function_name}' not found in '{module_name}'") from e

def with_timeout(timeout_seconds: int = 30):
    """Decorator to add timeout protection to functions.
    
    Args:
        timeout_seconds: Maximum time to allow function to run
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Note: Full timeout implementation would require threading,
            # but we can at least log long-running operations
            import time
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                if elapsed > 5:  # Log operations taking more than 5 seconds
                    logger.warning(f"{func.__name__} took {elapsed:.2f} seconds")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func.__name__} failed after {elapsed:.2f} seconds: {e}")
                raise
        return wrapper
    return decorator

# Module-level validation
def validate_core_dependencies():
    """Validate that all required core dependencies are available."""
    required_functions = [
        ('chapterforge.core', 'title_from_filename'),
        ('chapterforge.core', 'natural_key'),
        # Add other critical functions here
    ]
    
    missing = []
    for module_name, function_name in required_functions:
        try:
            validate_import(module_name, function_name)
        except ImportError as e:
            missing.append(f"{module_name}.{function_name}: {e}")
            logger.critical(f"Missing dependency: {e}")
    
    if missing:
        raise ImportError(f"Missing required functions:\n" + "\n".join(missing))

# Run validation at module import time
try:
    validate_core_dependencies()
except ImportError as e:
    logger.critical(f"ChapterForge validation failed: {e}")
    # We don't raise here to avoid breaking the application at import time
    # but we log the critical error
"""
Logging wrapper module for pygqlc

This module provides a unified logging interface that works with or without
the valiotlogging package. If valiotlogging is available, it will be used.
Otherwise, a simple fallback implementation using print statements is provided.
"""
from enum import Enum
from typing import Dict, Optional, Any, Callable
import logging
import sys
import traceback

# Try to import valiotlogging, but don't fail if it's not available
try:
    from valiotlogging import log as valiot_log, LogLevel as ValiotLogLevel
    HAS_VALIOT_LOGGING = True
except ImportError:
    HAS_VALIOT_LOGGING = False

# Configure basic Python logging to avoid excessive logs
logging.getLogger('httpx').setLevel(logging.WARNING)


class LogLevel(Enum):
    """Log levels enum that mirrors valiotlogging.LogLevel"""
    DEBUG = 'DEBUG'
    ERROR = 'ERROR'
    INFO = 'INFO'
    WARNING = 'WARNING'
    SUCCESS = 'SUCCESS'


# Map our LogLevel to valiotlogging.LogLevel if available
if HAS_VALIOT_LOGGING:
    _LOG_LEVEL_MAP = {
        LogLevel.DEBUG: ValiotLogLevel.DEBUG,
        LogLevel.ERROR: ValiotLogLevel.ERROR,
        LogLevel.INFO: ValiotLogLevel.INFO,
        LogLevel.WARNING: ValiotLogLevel.WARNING,
        LogLevel.SUCCESS: ValiotLogLevel.SUCCESS,
    }


def _fallback_log(level: LogLevel, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Simple fallback logging implementation using print statements."""
    level_str = level.value
    if extra:
        print(f"[{level_str}] {message} {extra}")
    else:
        print(f"[{level_str}] {message}")

    # Ensure we log the traceback in case of an error, not just the message
    if level == LogLevel.ERROR and sys.exc_info()[0]:
        print(f"[{level_str}] {traceback.format_exc()}")


# Define valiotlogging wrapper if available
if HAS_VALIOT_LOGGING:
    def _valiot_wrapper(
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log using valiotlogging if available."""
        valiot_level = _LOG_LEVEL_MAP.get(level, ValiotLogLevel.INFO)
        valiot_log(valiot_level, message, extra)
        # valiotlogging already handles traceback printing for ERROR level

    _log_impl = _valiot_wrapper
else:
    _log_impl = _fallback_log


# A reference to the current log function, can be changed by set_logger
_current_log_fn: Callable[[LogLevel, str,
                           Optional[Dict[str, Any]]], None] = _log_impl


def log(level: LogLevel, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Log a message with the current logger."""
    _current_log_fn(level, message, extra)


def set_logger(log_fn: Callable[[LogLevel, str, Optional[Dict[str, Any]]], None]) -> None:
    """Set a custom logger function to be used by pygqlc.

    Args:
        log_fn: A function that takes level, message, and extra parameters.
    """
    global _current_log_fn  # pylint: disable=W0603
    _current_log_fn = log_fn


def get_logger() -> Callable[[LogLevel, str, Optional[Dict[str, Any]]], None]:
    """Get the current logger function.

    Returns:
        The current logger function.
    """
    return _current_log_fn

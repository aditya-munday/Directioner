"""Alias module that re-exports the native Rust extension.

This module provides backward compatibility for code that imports
from directioner._native instead of directioner_native.
"""

from directioner_native import *  # noqa: F401, F403
from directioner_native import __all__  # noqa: F401

"""Configuration errors."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Raised when required environment configuration is missing or invalid."""


class MigrationError(Exception):
    """Raised when a database migration fails."""


class DatabaseError(Exception):
    """Raised for database operation failures."""

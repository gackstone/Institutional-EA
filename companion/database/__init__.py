"""Embedded SQLite persistence layer for the Institutional EA Companion Control Centre."""

from companion.database.migrations import init_database, get_connection
from companion.database.repository import CompanionRepository

__all__ = ["init_database", "get_connection", "CompanionRepository"]

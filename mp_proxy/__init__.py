"""Reusable client for a WeChat publishing proxy."""

from .client import DEFAULT_BASE_URL, MPErr, RemoteMP

__all__ = ["RemoteMP", "MPErr", "DEFAULT_BASE_URL"]

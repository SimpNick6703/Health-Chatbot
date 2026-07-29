"""Pytest configuration and shared fixtures for backend tests."""

import os
import sys
import pytest

# Add backend directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

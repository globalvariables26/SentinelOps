"""Pytest configuration and database test isolation fixtures."""
import pytest
from app.db.seed import seed_database


@pytest.fixture(autouse=True)
def clean_db():
    """Reset database before each test to ensure clean state and isolated cryptographic chains."""
    seed_database(reset=True)
    yield

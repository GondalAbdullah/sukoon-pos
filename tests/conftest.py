"""Shared pytest fixtures. Per Development Specification Section 10: integration
tests use pytest-flask against a real app instance — no mocking framework."""
import pytest

from sukoon.app import create_app


@pytest.fixture
def app():
    application = create_app("testing")
    yield application


@pytest.fixture
def client(app):
    return app.test_client()

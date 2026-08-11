import pytest
from django.test import Client

from core.models import Todo


@pytest.fixture
def api_client():
    """Provide a Django test client for API requests."""
    return Client()


@pytest.fixture
def todo(db):
    """A single saved todo, for tests that need one to act on."""
    return Todo.objects.create(title='Buy milk')

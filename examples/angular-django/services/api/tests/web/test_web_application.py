"""
End-to-end tests for the Django web application.

These tests verify that the main web endpoints work correctly.
"""
import pytest


@pytest.mark.django_db
class TestWebEndpoints:
    """Test suite for web application endpoints."""

    def test_health_check(self, api_client):
        """Test that the health-check endpoint loads successfully."""
        response = api_client.get('/')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'

    def test_admin_page_requires_authentication(self, api_client):
        """Test that the admin page requires authentication."""
        response = api_client.get('/admin/')
        # Should redirect to the login page
        assert response.status_code == 302
        assert '/admin/login/' in response.url

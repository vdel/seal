"""
Pytest configuration for the API tests.

This file configures pytest to work with Django and sets up fixtures
for integration and end-to-end tests.
"""
import os

# Set up Django settings before importing any Django modules
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Import pytest_django plugin
pytest_plugins = ['pytest_django']

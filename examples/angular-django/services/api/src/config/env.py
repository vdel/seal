import os

from config.env_utils import load_secrets


load_secrets()

# Set DEBUG to True if set to '1'
DEBUG = os.getenv('DEBUG', '') == '1'

# Database connection string for the PostgreSQL database
DATABASE_URL = os.getenv('DATABASE_URL')

"""WSGI entry point used by Gunicorn in production."""

from app import app


application = app

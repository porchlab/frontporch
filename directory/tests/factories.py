"""Explicit account fixtures for domain tests that do not exercise login."""

from uuid import uuid4
from django.contrib.auth.models import User


def create_user(**kwargs):
    kwargs.setdefault("username", f"test_{uuid4().hex}")
    return User.objects.create_user(**kwargs)

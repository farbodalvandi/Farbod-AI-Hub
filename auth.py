# -*- coding: utf-8 -*-
from functools import wraps
from flask import session, redirect, url_for, abort, request
import database as db

ROLE_LEVEL = db.ROLE_LEVEL  # operator:0  manager:2  admin:3


def current_user():
    username = session.get("username")
    if not username:
        return None
    user = db.get_user(username)
    if not user or not user["active"]:
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(min_role):
    """Usage: @role_required('editor')  -> editor, manager, admin allowed."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL.get(min_role, 99):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

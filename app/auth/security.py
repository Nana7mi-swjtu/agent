from __future__ import annotations

from functools import wraps

from flask import session


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return {"ok": False, "error": "unauthorized"}, 401
        return view_func(*args, **kwargs)

    return wrapped

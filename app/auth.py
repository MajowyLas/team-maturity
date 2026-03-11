"""Simple shared-password authentication.

Protected routes: /, /admin, /dashboard (and sub-routes).
Open routes: /survey/{token} (team members fill these without a password),
             /static, /login, /logout.

Set APP_PASSWORD env var to enable. When unset, all routes are open
(convenient for local development).
"""

import hashlib
import hmac
import os

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ─── Configuration ───────────────────────────────────────────────────────────

APP_PASSWORD: str | None = os.environ.get("APP_PASSWORD") or None
_COOKIE_NAME = "maturity_auth"

# Routes that do NOT require a password (prefixes).
_PUBLIC_PREFIXES = ("/survey/", "/login", "/logout", "/static/")


def _make_token(password: str) -> str:
    """Create an HMAC token from the password (used as cookie value)."""
    return hmac.new(
        password.encode(), b"maturity-authenticated", hashlib.sha256
    ).hexdigest()


def is_authenticated(request: Request) -> bool:
    """Check whether the request carries a valid auth cookie."""
    if APP_PASSWORD is None:
        return True  # no password configured → everyone is authenticated
    cookie = request.cookies.get(_COOKIE_NAME, "")
    expected = _make_token(APP_PASSWORD)
    return hmac.compare_digest(cookie, expected)


def set_auth_cookie(response: RedirectResponse) -> None:
    """Attach the auth cookie to a response."""
    if APP_PASSWORD is None:
        return
    token = _make_token(APP_PASSWORD)
    response.set_cookie(
        _COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days
    )


def clear_auth_cookie(response: RedirectResponse) -> None:
    """Remove the auth cookie."""
    response.delete_cookie(_COOKIE_NAME)


# ─── Middleware ──────────────────────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users to /login for protected routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public routes
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip if no password is configured
        if APP_PASSWORD is None:
            return await call_next(request)

        # Check cookie
        if is_authenticated(request):
            return await call_next(request)

        # Not authenticated → redirect to login (preserve original URL)
        return RedirectResponse(url=f"/login?next={path}", status_code=302)

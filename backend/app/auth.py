"""HTTP Basic Auth gate for single-user deployments.

When APP_PASSWORD is unset (default for local dev), auth is disabled so
contributors don't need to set up credentials. In production set
APP_PASSWORD via `fly secrets set` and the dependency rejects any request
without the right Authorization header.
"""

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic(auto_error=False, realm="ChatARPES")

APP_USERNAME = os.getenv("APP_USERNAME", "supervisor")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)):
    if not APP_PASSWORD:
        return  # auth disabled

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="ChatARPES"'},
        )

    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"), APP_USERNAME.encode("utf-8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"), APP_PASSWORD.encode("utf-8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="ChatARPES"'},
        )

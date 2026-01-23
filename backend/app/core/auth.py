from __future__ import annotations

from auth0_fastapi import Auth0Client, Auth0ClientConfig

from app.core.config import settings

auth_config = Auth0ClientConfig(
    domain=settings.AUTH0_DOMAIN,
    client_id=settings.AUTH0_CLIENT_ID,
    client_secret=settings.AUTH0_CLIENT_SECRET,
    secret=settings.AUTH0_SECRET,
    base_url=settings.APP_BASE_URL,
    audience=settings.AUTH0_AUDIENCE or None,
    scopes=[
        "openid",
        "profile",
        "email",
        "offline_access",
    ],
)

auth_client = Auth0Client(config=auth_config)

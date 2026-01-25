from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agent, auth, chat, user

api_router = APIRouter()

api_router.include_router(agent.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(user.router)

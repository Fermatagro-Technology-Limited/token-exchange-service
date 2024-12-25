from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.config import settings

settings.init_sentry()

app = FastAPI(
    title="Token Exchange Service",
    description="Service for Hortiview external user authorization",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
    # max_age=3600,  # Cache preflight requests for 1 hour
)

app.include_router(auth_router)

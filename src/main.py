from fastapi import FastAPI

from src.auth.router import router as auth_router

app = FastAPI(
    title="Token Exchange Service",
    description="Service for Hortiview external user authorization",
    version="1.0.0"
)

app.include_router(auth_router)

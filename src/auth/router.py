from fastapi import APIRouter, Depends, Security, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .schemas import ExchangeTokenResponse
from .service import ExchangeTokenService

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

cors_headers = {
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Origin": "*",
}

@router.post("/exchange-token", response_model=ExchangeTokenResponse)
async def exchange_token(
        response: Response,
        credentials: HTTPAuthorizationCredentials = Security(security),
        exchange_token_service: ExchangeTokenService = Depends(),
):
    # Add custom CORS headers to the response
    for key, value in cors_headers.items():
        response.headers[key] = value

    org_id, user_id = await exchange_token_service.decode_token(credentials.credentials)
    response = await exchange_token_service.login_to_org(org_id, user_id, credentials.credentials)
    return ExchangeTokenResponse(**response)

from fastapi import APIRouter, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .schemas import ExchangeTokenResponse
from .service import ExchangeTokenService

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


@router.post("/exchange-token", response_model=ExchangeTokenResponse)
async def exchange_token(
        credentials: HTTPAuthorizationCredentials = Security(security),
        exchange_token_service: ExchangeTokenService = Depends(),
):
    org_id, user_id = await exchange_token_service.decode_token(credentials.credentials)
    response = await exchange_token_service.login_to_org(org_id, user_id, credentials.credentials)
    return ExchangeTokenResponse(**response)

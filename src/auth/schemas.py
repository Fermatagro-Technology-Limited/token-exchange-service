from pydantic import BaseModel, Field


class ExchangeTokenResponse(BaseModel):
    token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    session_data: str = Field(..., description="Session data")
    main_api_url: str = Field(..., description="MainAPI URL")

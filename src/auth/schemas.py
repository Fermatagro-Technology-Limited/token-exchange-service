from pydantic import BaseModel


class Token(BaseModel):
    token: str


class ExchangeTokenResponse(BaseModel):
    token: str
    refresh_token: str
    session_data: str
    main_api_url: str


class ModuleRolesAndPermissions(BaseModel):
    FarmOrganizationId: str
    UserId: str


class JWTPayload(BaseModel):
    ModuleRolesAndPermissions: ModuleRolesAndPermissions

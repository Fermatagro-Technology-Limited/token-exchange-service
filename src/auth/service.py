import json
import logging
from typing import Dict, Tuple

import httpx
import jwt
from async_lru import alru_cache
from cachetools import TTLCache
from consul import Consul
from fastapi import HTTPException, status

from src.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)

consul_client = Consul(
    host=settings.CONSUL_HOST,
    port=settings.CONSUL_PORT
)

access_token_cache = TTLCache(maxsize=1, ttl=300)
refresh_token_cache = TTLCache(maxsize=1, ttl=60)


class ExchangeTokenService:
    @alru_cache(maxsize=1, ttl=settings.API_URLS_CACHE_TTL)
    async def _get_api_urls(self) -> dict[str, str]:
        index, data = consul_client.kv.get('hortiview/mainApiByOrgId.json')
        if not data or not data['Value']:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not load organization mappings from Consul"
            )

        try:
            return json.loads(data['Value'].decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Invalid organization mappings format in Consul"
            )

    async def _get_org_api_url(self, org_id: str) -> str:
        api_urls = await self._get_api_urls()
        api_url = api_urls.get(org_id)
        if not api_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No API URL found for organization {org_id}"
            )

        return api_url

    @classmethod
    async def get_public_key(cls) -> bytes:
        async with httpx.AsyncClient(base_url=settings.HORTIVIEW_API_URL) as client:
            logger.info(f"Fetching public key")
            response = await client.get("pem?api-version=1.0")
            response.raise_for_status()
            return response.content

    async def decode_token(self, token: str) -> Tuple[str, str]:
        public_key = await self.get_public_key()
        logger.debug("Got public key, attempting to decode token")
        try:
            decoded_token = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )
        except jwt.ExpiredSignatureError:
            logger.error("Token is expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            logger.error(f"Token is invalid: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error decoding token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing token"
            )

        module_info = decoded_token.get("ModuleRolesAndPermissions", {})
        org_id = module_info.get("FarmOrganizationId")
        user_id = module_info.get("UserId")

        if not org_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing organization or user ID"
            )

        logger.info(f"Successfully decoded token for org_id: {org_id}, user_id: {user_id}")
        return org_id, user_id

    @staticmethod
    async def _auth_to_main_api(client: httpx.AsyncClient) -> str:
        if access_token_cache.get(client.base_url):
            logger.info("Using cached access token")
            return access_token_cache[client.base_url]
        elif refresh_token_cache.get(client.base_url):
            logger.info("Using cached refresh token to get new access token")
            response = await client.post(
                "refresh",
                json={
                    "refresh_token": refresh_token_cache[client.base_url],
                },
                timeout=10.0
            )
            response.raise_for_status()
            response_data = response.json()

            access_token_cache[client.base_url] = response_data["token"]
            refresh_token_cache[client.base_url] = response_data["refresh_token"]

            return response_data["token"]
        else:
            logger.info("Authenticating to MainAPI")
            response = await client.post(
                "login",
                json={
                    "username": settings.MAIN_API_USERNAME,
                    "password": settings.MAIN_API_PASSWORD
                },
                timeout=10.0
            )
            response.raise_for_status()
            response_data = response.json()

            access_token_cache[client.base_url] = response_data["token"]
            refresh_token_cache[client.base_url] = response_data["refresh_token"]

            return response_data["token"]

    async def login_to_org(self, org_id: str, user_id: str, token: str) -> Dict:
        base_url = await self._get_org_api_url(org_id)
        logger.info(f"Getting auth token from {base_url}/login")

        async with httpx.AsyncClient(base_url=base_url) as client:
            try:
                bearer_token = await self._auth_to_main_api(client)

                # Then make the external_login request with the bearer token
                logger.info("Authorizing external user")

                response = await client.post(
                    "external_login",
                    json={
                        "token": token,
                        "user_id": user_id
                    },
                    headers={
                        "Authorization": f"Bearer {bearer_token}"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                return {**response.json(), "main_api_url": base_url}

            except httpx.HTTPError as e:
                logger.error(f"Error communicating with organization API {base_url}: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Error communicating with organization API: {str(e)}"
                )

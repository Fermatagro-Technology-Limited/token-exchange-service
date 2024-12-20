import json
import logging
from base64 import urlsafe_b64decode
from typing import Dict, Tuple

# noinspection PyPackageRequirements
import consul
import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from fastapi import HTTPException, status

from src.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(settings.LOG_LEVEL)


class ExchangeTokenService:
    def __init__(self):
        self._public_key = None
        self._consul = consul.Consul(
            host=settings.CONSUL_HOST,
            port=settings.CONSUL_PORT
        )
        self._api_urls_cache = None

    @staticmethod
    def _jwk_to_pem(jwk: dict) -> bytes:
        """Convert a JWK to PEM format"""
        # Decode the JWK components
        e = int.from_bytes(urlsafe_b64decode(jwk['e'] + '==='), byteorder='big')
        n = int.from_bytes(urlsafe_b64decode(jwk['n'] + '==='), byteorder='big')

        # Create RSA public numbers
        public_numbers = RSAPublicNumbers(e=e, n=n)
        public_key = public_numbers.public_key()

        # Convert to PEM
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return pem

    def _get_org_api_url(self, org_id: str) -> str:
        if self._api_urls_cache is None:
            index, data = self._consul.kv.get('hortiview/mainApiByOrgId.json')
            if not data or not data['Value']:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not load organization mappings from Consul"
                )

            try:
                self._api_urls_cache = json.loads(data['Value'].decode('utf-8'))
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Invalid organization mappings format in Consul"
                )

        api_url = self._api_urls_cache.get(org_id)
        if not api_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No API URL found for organization {org_id}"
            )

        return api_url

    async def get_public_key(self) -> bytes:
        if not self._public_key:
            async with httpx.AsyncClient() as client:
                jwks_url = f"{settings.HORTIVIEW_API_URL}/jwks?api-version=1.0"
                logger.info(f"Fetching JWKS from {jwks_url}")
                response = await client.get(jwks_url)
                response.raise_for_status()
                jwks = response.json()

                if not jwks.get('keys'):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="No keys found in JWKS response"
                    )

                try:
                    self._public_key = self._jwk_to_pem(jwks['keys'][0])
                    logger.info("Successfully converted JWK to PEM")
                except (KeyError, ValueError) as e:
                    logger.error(f"Error converting JWK to PEM: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Invalid key format in JWKS response"
                    )

        return self._public_key

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

    async def login_to_org(self, org_id: str, user_id: str, token: str) -> Dict:
        base_url = self._get_org_api_url(org_id)
        logger.info(f"Getting auth token from {base_url}/login")

        async with httpx.AsyncClient() as client:
            try:
                # First authenticate to get the bearer token
                auth_response = await client.post(
                    f"{base_url}/login",
                    json={
                        "username": settings.MAIN_API_USERNAME,
                        "password": settings.MAIN_API_PASSWORD
                    },
                    timeout=10.0
                )
                auth_response.raise_for_status()
                bearer_token = auth_response.json()["token"]

                # Then make the external_login request with the bearer token
                login_url = f"{base_url}/external_login"
                logger.info(f"Forwarding login request to {login_url}")

                response = await client.post(
                    login_url,
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
                logger.error(f"Error communicating with organization API {base_url}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Error communicating with organization API: {str(e)}"
                )

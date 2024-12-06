from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from httpx import HTTPError, Request, Response

from src.auth.service import ExchangeTokenService

TEST_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJNb2R1bGVSb2xlc0FuZFBlcm1pc3Npb25zIjp7IkZhcm1Pcmdhbml6YXRpb25JZCI6ImI3ZGNlMjQ5LTVkMTctNGFkMy1hNDFhLTQyZjYzY2UzZWJhOCIsIlVzZXJJZCI6IjYyNzA3NzAzLWE0ODMtNDFmYi04ZjJmLTRjNzRkMjg4OTc4NiJ9fQ.signature"
TEST_ORG_ID = "b7dce249-5d17-4ad3-a41a-42f63ce3eba8"
TEST_USER_ID = "62707703-a483-41fb-8f2f-4c74d2889786"


def create_response(status_code: int, json_data: dict) -> Response:
    response = Response(
        status_code=status_code,
        json=json_data,
    )
    # Set required request instance
    response._request = Request("POST", "https://test.com")
    return response


@pytest.fixture
def mock_consul():
    with patch('consul.Consul') as mock:
        consul_instance = Mock()
        mock.return_value = consul_instance

        # Mock KV response
        consul_instance.kv.get.return_value = (
            None,
            {'Value': b'{"b7dce249-5d17-4ad3-a41a-42f63ce3eba8": "https://api-dev.fermata.cloud/api/v1"}'}
        )
        yield mock


@pytest.fixture
def mock_httpx_client():
    with patch('httpx.AsyncClient') as mock:
        client_instance = Mock()

        async def mock_post(*args, **kwargs):
            if args[0].endswith('/login'):
                return create_response(200, {"token": "mock_bearer_token"})
            elif args[0].endswith('/external_login'):
                return create_response(200, {"access_token": "new_token"})
            return create_response(404, {})

        async def mock_get(*args, **kwargs):
            if args[0].endswith('/jwks'):
                # noinspection SpellCheckingInspection
                return create_response(200, {
                    "keys": [{
                        "kty": "RSA",
                        "e": "AQAB",
                        "n": "sample_key"
                    }]
                })
            return create_response(404, {})

        client_instance.post = mock_post
        client_instance.get = mock_get
        mock.return_value.__aenter__.return_value = client_instance
        yield client_instance


@pytest.fixture
def mock_jwt_decode():
    with patch('src.auth.service.jwt.decode') as mock:
        mock.return_value = {
            "ModuleRolesAndPermissions": {
                "FarmOrganizationId": TEST_ORG_ID,
                "UserId": TEST_USER_ID
            }
        }
        yield mock


@pytest.mark.asyncio
async def test_get_org_api_url(mock_consul):
    service = ExchangeTokenService()
    url = service._get_org_api_url(TEST_ORG_ID)
    assert url == "https://api-dev.fermata.cloud/api/v1"
    mock_consul.return_value.kv.get.assert_called_once_with('hortiview/mainApiByOrgId.json')


@pytest.mark.asyncio
async def test_get_org_api_url_not_found(mock_consul):
    service = ExchangeTokenService()
    with pytest.raises(HTTPException) as exc_info:
        url = service._get_org_api_url("nonexistent-org")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_login_to_org_success(mock_consul, mock_httpx_client):
    service = ExchangeTokenService()
    result = await service.login_to_org(TEST_ORG_ID, TEST_USER_ID, TEST_TOKEN)
    assert result == {"access_token": "new_token"}


@pytest.mark.asyncio
async def test_login_to_org_auth_failure(mock_consul, mock_httpx_client):
    async def mock_post_failure(*args, **kwargs):
        raise HTTPError("Auth failed")

    mock_httpx_client.post = mock_post_failure

    service = ExchangeTokenService()
    with pytest.raises(HTTPException) as exc_info:
        await service.login_to_org(TEST_ORG_ID, TEST_USER_ID, TEST_TOKEN)

    assert exc_info.value.status_code == 502
    assert "Auth failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_decode_token_missing_info(mock_httpx_client, mock_jwt_decode):
    service = ExchangeTokenService()

    # Override the mock to return data without required fields
    mock_jwt_decode.return_value = {"some": "data"}

    # Mock get_public_key so it doesn't try to fetch JWKS
    with patch.object(service, 'get_public_key', return_value="mock_public_key"):
        with pytest.raises(HTTPException) as exc_info:
            await service.decode_token(TEST_TOKEN)

        assert exc_info.value.status_code == 401
        assert "missing organization or user ID" in str(exc_info.value.detail)

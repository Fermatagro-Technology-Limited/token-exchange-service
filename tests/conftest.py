import pytest

from src.config import Settings


@pytest.fixture
def settings():
    return Settings(
        HORTIVIEW_API_URL="https://api-test.example.com",
        CONSUL_HOST="localhost",
        CONSUL_PORT=8500,
        MAIN_API_USERNAME="test_user",
        MAIN_API_PASSWORD="test_pass"
    )
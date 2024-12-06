import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HORTIVIEW_API_URL: str
    CONSUL_HOST: str
    CONSUL_PORT: int = 8500
    LOG_LEVEL: str = "INFO"
    MAIN_API_USERNAME: str
    MAIN_API_PASSWORD: str


# noinspection PyArgumentList
settings = Settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger(__name__)

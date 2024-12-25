import logging

import sentry_sdk
from pydantic_settings import BaseSettings
from sentry_sdk.integrations.logging import LoggingIntegration


class Settings(BaseSettings):
    HORTIVIEW_API_URL: str
    CONSUL_HOST: str
    CONSUL_PORT: int = 8500
    LOG_LEVEL: str = logging.getLevelName(logging.INFO)
    MAIN_API_USERNAME: str
    MAIN_API_PASSWORD: str
    ENV: str | None = None
    SENTRY_DSN: str | None = None

    def init_sentry(self) -> None:
        if self.SENTRY_DSN and self.ENV:
            sentry_sdk.init(
                dsn=self.SENTRY_DSN,
                environment=self.ENV,
                traces_sample_rate=1.0,
                profiles_sample_rate=1.0,
                integrations=[
                    LoggingIntegration(level=logging.INFO, event_level=logging.WARNING),
                ],
                _experiments={
                    # Set continuous_profiling_auto_start to True
                    # to automatically start the profiler on when
                    # possible.
                    "continuous_profiling_auto_start": True,
                },
            )


# noinspection PyArgumentList
settings = Settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger(__name__)

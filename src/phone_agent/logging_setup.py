import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_file = settings.logs_dir / "phone-agent.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=10),
            logging.StreamHandler(),
        ],
    )

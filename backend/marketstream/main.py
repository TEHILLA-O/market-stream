"""Process entrypoint."""

from __future__ import annotations

import uvicorn

from marketstream.core.config import Settings
from marketstream.core.logging import configure_logging


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "marketstream.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()

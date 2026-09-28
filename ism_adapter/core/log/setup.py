"""loguru 초기화. 배치 실행 단위(1회 push)를 로그에서 추적하기 쉽도록
파일 로테이션 없이 실행마다 표준 출력 + 파일(append)로 남긴다.
"""

import sys

from loguru import logger

from ism_adapter.core.config import settings


def setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if settings.app.debug else "INFO")
    logger.add(
        f"{settings.log.default_path}/{settings.log.filename}",
        rotation=settings.log.rotation,
        retention=settings.log.retention,
        compression=settings.log.compression,
        level="INFO",
    )

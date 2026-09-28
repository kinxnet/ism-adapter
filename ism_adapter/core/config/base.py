"""App config"""

import os
from functools import lru_cache
from urllib.parse import quote_plus

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings as _BaseSettings
from pydantic_settings import SettingsConfigDict

from ism_adapter.core.config.kmsclient import get_secret


class BaseSettings(_BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")


class AppConfig(BaseSettings):
    debug: bool = Field(default=False)
    description: str = Field(default="metering-api usage → ISM push 어댑터")
    environment: str = Field(default="prod")
    timezone: str = Field(default="UTC")
    master_apikey: str = Field(default="")


class DatabaseConfig(BaseSettings):
    """portal_db(project) 연결.

    ⚠️ 별도 읽기 전용 계정이 없어 ixcs-api-service와 동일한 일반(쓰기 가능)
    계정을 그대로 쓴다(2026-09-15 확인) — "project 테이블에 쓰지 않는다"는
    지금은 DB 권한이 아니라 코드 레벨 약속일 뿐이다. 이 서비스는 project
    테이블의 소유자가 아니므로 repositories/project_repository.py 밖에서
    이 연결로 쓰기 쿼리를 실행하지 않는다.
    (ism-adapter-project-decisions 메모리 참고: 장기적으로는 ixcs-api-service의
    조회 전용 API로 대체 예정 — 지금은 파이프라인 검증을 위한 임시 방편.
    읽기 전용 계정 발급도 별도 후속 과제로 남겨둠)

    billing_url은 계약 push(contract)의 할인(discount) 정보 조회 전용 — portal_url과
    같은 서버, 스키마만 다르다(2026-09-17 dev 실측: 둘 다 1.201.137.199:3306,
    계정 kinx, portal은 `ixcloud` 스키마, billing은 `ixcloud_billing` 스키마).
    **옵션(필수 아님)** — dev에는 이 테이블 데이터가 비어있어 discount 없이도
    계약 push 개발/검증이 가능해야 한다는 사용자 결정(2026-09-17)에 따라,
    비어있으면 validate_config에서 죽이지 않고 discount만 빈 배열로 폴백한다
    (contract_repository.py에서 처리 예정). prod KMS 경로는 아직 확인 안 됨 —
    portal-db(common/databases/portal-db)와 동일 패턴일 것으로 예상되나 착수 시
    실제 경로 확인 필요.
    """

    portal_url: str | None = Field(default=None)
    billing_url: str | None = Field(default=None)


class SentryConfig(BaseSettings):
    dsn: str = Field(default="")


class EndpointConfig(BaseSettings):
    """metering_api/ism_api는 환경(dev/stage/prod)마다 값이 달라 KMS가 아닌
    환경변수(METERING_API_HOST / ISM_API_HOST, Helm values env)로 주입한다.
    master_apikey만 공통 시크릿이라 KMS(common/api-keys)에서 로드한다.
    """

    metering_api: str = Field(default="")
    ism_api: str = Field(default="")


class LogConfig(BaseSettings):
    default_path: str = Field(default="./logs")
    filename: str = Field(default="ism_adapter.log")
    rotation: str = Field(default="00:00")
    retention: str = Field(default="365 days")
    compression: str = Field(default="tar.gz")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    sentry: SentryConfig = Field(default_factory=SentryConfig)
    endpoint: EndpointConfig = Field(default_factory=EndpointConfig)
    log: LogConfig = Field(default_factory=LogConfig)

    def get_summary(self) -> dict:
        """설정 요약을 반환한다 (민감정보는 마스킹)."""
        try:
            return {
                "app_config": {
                    "environment": self.app.environment,
                    "timezone": self.app.timezone,
                    "master_apikey": "****" if self.app.master_apikey else "not set",
                },
                "database_config": {
                    "portal_url": (
                        "set (****)" if self.database.portal_url else "not set"
                    ),
                    "billing_url": (
                        "set (****)" if self.database.billing_url else "not set (optional)"
                    ),
                },
                "endpoint_config": {
                    "metering_api": self.endpoint.metering_api or "not set",
                    "ism_api": self.endpoint.ism_api or "not set",
                },
                "sentry_config": {
                    "dsn": "****" if self.sentry.dsn else "not set",
                },
            }
        except Exception as e:
            logger.error("Failed to generate configuration summary: {}", e)
            return {"error": str(e), "status": "failed"}


def _load_endpoint_hosts(config: Settings) -> None:
    """metering-api/ISM 엔드포인트를 환경변수에서 로드.

    환경(dev/stage/prod)마다 달라 KMS가 아닌 values-*.yaml의 env로 주입한다.
    이미 ENDPOINT__METERING_API / ENDPOINT__ISM_API로 채워진 값이 있으면 우선한다.

    ism_api는 legacy(ism/*.py)와 ixcs-portal-stack values.yaml 전 환경에서
    평문 사설 IP(http://1.201.138.223:8303/v1)로 관리되고 있고 인증 헤더 자체가
    없다 — 이 무인증 방식을 그대로 이어받을지는 별도로 인프라/보안팀과 상의 필요
    (ism-adapter-project-decisions 메모리 참고).
    """
    if not config.endpoint.metering_api:
        metering_api_host = os.environ.get("METERING_API_HOST")
        if metering_api_host and metering_api_host.strip():
            config.endpoint.metering_api = metering_api_host.strip()
        else:
            logger.warning("env METERING_API_HOST is not set")

    if not config.endpoint.ism_api:
        ism_api_host = os.environ.get("ISM_API_HOST")
        if ism_api_host and ism_api_host.strip():
            config.endpoint.ism_api = ism_api_host.strip()
        else:
            logger.warning("env ISM_API_HOST is not set")


def _load_secrets(config: Settings) -> None:
    """KMS에서 시크릿 로드.

    실패 시 warning만 남기고 계속 진행한다 (개별 필드는 빈 값으로 남음).
    필수 필드가 비어있으면 validate_config()가 기동 시점에 명확히 죽인다.
    """
    try:
        # ⚠️ 이 KMS 경로(common/databases/portal-db)는 ixcs-api-service가 쓰는
        # 것과 동일한 일반(쓰기 가능) 계정이다 — project 테이블 전용 읽기 전용
        # 계정이 별도로 존재하지 않는다(2026-09-15 확인). 즉 "이 서비스는
        # project 테이블에 쓰지 않는다"는 지금은 DB 권한이 아니라 코드 레벨
        # 약속일 뿐이다. repositories/project_repository.py 밖에서 이 엔진으로
        # 쓰기 쿼리를 실행하지 않도록 각별히 주의할 것 — 별도 읽기 전용 계정
        # 발급은 ism-adapter-project-decisions 메모리에 후속 과제로 남겨둔다.
        db = get_secret("common/databases/portal-db")
        if isinstance(db, dict):
            host = db.get("host")
            port = db.get("port")
            user = db.get("user")
            password = db.get("password")
            database = db.get("database")
            if all(
                v not in (None, "") for v in (host, port, user, password, database)
            ):
                config.database.portal_url = (
                    f"mysql+pymysql://{user}:{quote_plus(str(password))}"
                    f"@{host}:{port}/{database}"
                )
            else:
                logger.warning("KMS: missing fields in 'common/databases/portal-db'")
        else:
            logger.warning("KMS: No data returned for 'common/databases/portal-db'")
    except Exception as e:
        logger.warning("Failed to load 'common/databases/portal-db' from KMS: {}", e)

    try:
        # billing_url은 옵션(2026-09-17 결정) — 실패해도 warning만 남기고
        # 계약 push는 discount를 빈 배열로 폴백해 계속 동작한다.
        db = get_secret("common/databases/billing-db")
        if isinstance(db, dict):
            host = db.get("host")
            port = db.get("port")
            user = db.get("user")
            password = db.get("password")
            database = db.get("database")
            if all(
                v not in (None, "") for v in (host, port, user, password, database)
            ):
                config.database.billing_url = (
                    f"mysql+pymysql://{user}:{quote_plus(str(password))}"
                    f"@{host}:{port}/{database}"
                )
            else:
                logger.warning("KMS: missing fields in 'common/databases/billing-db'")
        else:
            logger.warning("KMS: No data returned for 'common/databases/billing-db'")
    except Exception as e:
        logger.warning("Failed to load 'common/databases/billing-db' from KMS: {}", e)

    try:
        master_apikey = get_secret("common/api-keys", "master_apikey")
        if isinstance(master_apikey, str) and master_apikey:
            config.app.master_apikey = master_apikey
        else:
            logger.warning("KMS: 'master_apikey' not found in 'common/api-keys'")
    except Exception as e:
        logger.warning("Failed to load 'common/api-keys' from KMS: {}", e)

    _load_endpoint_hosts(config)


def validate_config(config: Settings) -> None:
    """필수 설정값 검증 — 누락 시 RuntimeError 발생 (Fail Fast)."""
    if config.app.environment == "test":
        return

    errors: list[str] = []
    if not config.database.portal_url:
        errors.append(
            "database.portal_url (KMS common/databases/portal-db) is not set"
        )
    if not config.app.master_apikey:
        errors.append(
            "app.master_apikey (KMS common/api-keys.master_apikey) is not set"
        )
    if not config.endpoint.metering_api:
        errors.append("endpoint.metering_api (env METERING_API_HOST) is not set")
    if not config.endpoint.ism_api:
        errors.append("endpoint.ism_api (env ISM_API_HOST) is not set")

    if errors:
        for err in errors:
            logger.error("Configuration error: {}", err)
        raise RuntimeError(
            "Required configuration is missing:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


@lru_cache
def get_config() -> Settings:
    root_settings: Settings = Settings(_env_file=".env")  # type: ignore[call-arg]
    _load_secrets(root_settings)
    return root_settings


settings = get_config()

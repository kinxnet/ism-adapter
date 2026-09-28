"""KMS 클라이언트 모듈(vault 연동)"""

import os

from hvac import Client
from hvac.api.auth_methods import Kubernetes
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# K8s가 Pod에 자동 마운트하는 ServiceAccount 토큰 기본 경로.
# 이 파일이 존재하면 클러스터 내부로 간주하고 Kubernetes auth를 사용한다.
_DEFAULT_K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

_client: Client | None = None


class KmsSettings(BaseSettings):
    """KMS 관련 환경변수.

    .env 파일과 OS 환경변수를 모두 자동으로 읽는다 (pydantic-settings 규칙).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    build_type: str = Field(default="local")

    # Dev (local)
    dev_kms_endpoint: str | None = Field(default=None)
    dev_kms_engine: str | None = Field(default=None)
    dev_kms_role_id: str | None = Field(default=None)
    dev_kms_role_secret: str | None = Field(default=None)

    # Prod/Staging
    kms_endpoint: str | None = Field(default=None)
    kms_engine: str | None = Field(default=None)
    kms_role_id: str | None = Field(default=None)
    kms_role_secret: str | None = Field(default=None)

    # Kubernetes auth (클러스터 내부에서 ServiceAccount 토큰으로 Vault 로그인)
    # role 이름은 K8s ConfigMap(KMS_K8S_AUTH_ROLE)으로 주입한다.
    kms_k8s_auth_role: str | None = Field(default=None)
    kms_k8s_auth_mount: str = Field(default="kubernetes")
    kms_k8s_token_path: str = Field(default=_DEFAULT_K8S_TOKEN_PATH)


def _get_settings() -> KmsSettings:
    """매번 새로 읽는다. 테스트에서 환경변수 변경 후 즉시 반영되도록."""
    return KmsSettings()  # type: ignore[call-arg]


def vault_client(
    role_id: str | None,
    secret_id: str | None,
    api_url: str | None,
) -> Client | None:
    if not role_id or not secret_id or not api_url:
        logger.error("KMS credentials are missing (role_id/secret_id/api_url)")
        return None

    client = Client(url=api_url)
    try:
        client.auth.approle.login(role_id, secret_id)
    except Exception as e:
        logger.error(e)
        return None

    return client


def vault_client_k8s(
    role: str | None,
    api_url: str | None,
    token_path: str,
    mount_point: str,
) -> Client | None:
    """ServiceAccount JWT로 Vault Kubernetes auth 로그인.

    클러스터가 Pod에 마운트한 토큰 파일을 읽어 인증한다 (secret_id 불필요).
    """
    if not role or not api_url:
        logger.error("KMS k8s auth config is missing (role/api_url)")
        return None

    try:
        with open(token_path, encoding="utf-8") as f:
            jwt = f.read().strip()
    except OSError as e:
        logger.error("Failed to read ServiceAccount token from {}: {}", token_path, e)
        return None

    client = Client(url=api_url)
    try:
        Kubernetes(client.adapter).login(role=role, jwt=jwt, mount_point=mount_point)
    except Exception as e:
        logger.error(e)
        return None

    return client


def _make_client() -> Client | None:
    s = _get_settings()
    if s.build_type == "local":
        return vault_client(
            s.dev_kms_role_id,
            s.dev_kms_role_secret,
            s.dev_kms_endpoint,
        )

    # prod: ServiceAccount 토큰 파일이 있으면 Kubernetes auth, 없으면 AppRole로 fallback.
    if os.path.exists(s.kms_k8s_token_path):
        return vault_client_k8s(
            s.kms_k8s_auth_role,
            s.kms_endpoint,
            s.kms_k8s_token_path,
            s.kms_k8s_auth_mount,
        )
    return vault_client(
        s.kms_role_id,
        s.kms_role_secret,
        s.kms_endpoint,
    )


def _get_engine() -> str | None:
    s = _get_settings()
    if s.build_type == "local":
        return s.dev_kms_engine
    return s.kms_engine


def _get_client() -> Client | None:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


def get_secret(secret_name: str, secret_key: str | None = None) -> dict | str | None:
    client = _get_client()
    if client is None:
        logger.error("Vault client is not initialized")
        return None
    try:
        secret_result = client.secrets.kv.v2.read_secret_version(
            path=secret_name,
            mount_point=_get_engine(),
        )

        secret_data = secret_result["data"]["data"]
        if secret_key is not None:
            if secret_key in secret_data:
                return secret_data[secret_key]
            logger.error(
                "Secret key '{}' not found in secret '{}'", secret_key, secret_name
            )
            return None

        return secret_data
    except Exception as e:
        logger.error(e)
        return None

"""CLI 진입점.

k8s CronJob이 인자 없이 매일 호출하면 "어제 하루" 기간으로 정기 배치를
수행한다. 운영자가 특정 기간을 지정해 재실행하면(예: metering 결측 발견 후
수동 재전송) 그 기간만 다시 push한다 — 정기 배치와 수동 재전송이 같은
push_resource_type()을 인자만 다르게 호출하는 동일 경로다.

2026-09-17 서브커맨드 도입: account push(accounts)는 resource/metering push
(resources)와 성격이 다르다 — 기간 개념이 없고(매번 전체 대상 계정을 다시
push), 자원 타입 구분도 없다. 억지로 같은 인자 체계에 끼워 넣기보다
서브커맨드로 나눈다. legacy 실행 순서(account → contract → resource →
metering)대로, CronJob은 `accounts`를 `resources`보다 먼저 호출해야 한다.

사용 예:
    # 계정 push (정기 배치, 항상 전체 대상)
    python -m ism_adapter.cli accounts

    # 계약 push (정기 배치, 항상 전체 대상) — account 다음, resource 이전에 실행
    python -m ism_adapter.cli contracts

    # 자원/사용량 정기 배치 (매일 자정 직후 크론이 호출, 전일 하루치)
    python -m ism_adapter.cli resources --resource-type=network,router

    # 특정 기간 재전송 (운영자 수동 실행)
    python -m ism_adapter.cli resources --resource-type=network \\
        --period-start=2026-09-01T00:00:00 --period-end=2026-09-02T00:00:00
"""

import argparse
import sys
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import create_engine

from ism_adapter.clients.ism_client import ISMClient
from ism_adapter.clients.metering_api_client import MeteringAPIClient
from ism_adapter.core.config import settings, validate_config
from ism_adapter.core.log import setup_logging
from ism_adapter.repositories.account_repository import AccountRepository
from ism_adapter.repositories.contract_repository import ContractRepository
from ism_adapter.repositories.project_repository import ProjectRepository
from ism_adapter.repositories.tables import project_table
from ism_adapter.services.account_service import push_accounts
from ism_adapter.services.contract_service import push_contracts
from ism_adapter.services.push_service import push_resource_type
from ism_adapter.transformers import TRANSFORMERS

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _default_period() -> tuple[str, str]:
    """미지정 시 "어제 00:00 ~ 오늘 00:00" (하루치)를 기본값으로 쓴다."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    return yesterday.strftime(_ISO_FORMAT), today.strftime(_ISO_FORMAT)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_start, default_end = _default_period()

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "accounts", help="계정 push (project를 가진 전체 계정 대상, 기간 없음)"
    )

    subparsers.add_parser(
        "contracts", help="계약 push (provider/account 조건을 만족하는 전체 project 대상, 기간 없음)"
    )

    resources_parser = subparsers.add_parser(
        "resources", help="자원/사용량 push (기존 network/router 등)"
    )
    resources_parser.add_argument(
        "--resource-type",
        default=",".join(sorted(TRANSFORMERS)),
        help=f"콤마로 구분된 자원 타입 (지원: {sorted(TRANSFORMERS)})",
    )
    resources_parser.add_argument(
        "--period-start",
        default=default_start,
        help=f"기간 시작 (기본값: 전일 00:00, ISO 형식). 예: {default_start}",
    )
    resources_parser.add_argument(
        "--period-end",
        default=default_end,
        help=f"기간 종료 (기본값: 오늘 00:00, ISO 형식). 예: {default_end}",
    )

    return parser.parse_args(argv)


def _run_accounts(args: argparse.Namespace) -> int:
    engine = create_engine(settings.database.portal_url, pool_pre_ping=True)
    account_repo = AccountRepository(engine)

    with ISMClient(settings.endpoint.ism_api) as ism_client:
        try:
            push_accounts(account_repo, ism_client)
        except Exception:
            logger.exception("Failed to push accounts")
            return 1
    return 0


def _run_contracts(args: argparse.Namespace) -> int:
    portal_engine = create_engine(settings.database.portal_url, pool_pre_ping=True)

    billing_engine = None
    if settings.database.billing_url:
        billing_engine = create_engine(settings.database.billing_url, pool_pre_ping=True)
    else:
        logger.warning(
            "database.billing_url is not set — discount 없이 계약 push를 진행합니다"
        )

    contract_repo = ContractRepository(portal_engine, billing_engine)

    with ISMClient(settings.endpoint.ism_api) as ism_client:
        try:
            push_contracts(contract_repo, ism_client)
        except Exception:
            logger.exception("Failed to push contracts")
            return 1
    return 0


def _run_resources(args: argparse.Namespace) -> int:
    resource_types = [rt.strip() for rt in args.resource_type.split(",") if rt.strip()]

    logger.info(
        "Starting ISM resource push: resource_types={} period=[{}, {})",
        resource_types,
        args.period_start,
        args.period_end,
    )

    engine = create_engine(settings.database.portal_url, pool_pre_ping=True)
    project_repo = ProjectRepository(engine, project_table)

    exit_code = 0
    with (
        MeteringAPIClient(
            settings.endpoint.metering_api, settings.app.master_apikey
        ) as metering_client,
        ISMClient(settings.endpoint.ism_api) as ism_client,
    ):
        for resource_type in resource_types:
            try:
                push_resource_type(
                    resource_type,
                    args.period_start,
                    args.period_end,
                    metering_client,
                    project_repo,
                    ism_client,
                )
            except Exception:
                logger.exception("Failed to push resource_type={}", resource_type)
                exit_code = 1

    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    setup_logging()
    validate_config(settings)

    if args.command == "accounts":
        return _run_accounts(args)
    if args.command == "contracts":
        return _run_contracts(args)
    if args.command == "resources":
        return _run_resources(args)

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())

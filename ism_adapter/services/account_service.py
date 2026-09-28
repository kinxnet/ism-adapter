"""portal_db 계정 정보 → ISM(THAAD) 계정 push 파이프라인.

legacy `ixc_daemon_ism.py`의 `ism/account.py::AccountClass.register_accounts()`를
재현한다. resource/metering push(push_service.py)와 실행 모델은 같지만(상태 없이
매번 전체 대상을 다시 push), 전송 단위가 다르다 — account는 20건 배치가 아니라
**계정 1건당 1회 개별 POST**다(ism_client.py::put_account 참고).

**2026-09-17 결정: 첫 실패 시 즉시 중단한다.** legacy account.py는 원래
계정별로 예외를 격리해 계속 진행했지만, contract.py(B)는 반대로 project 하나가
실패하면 즉시 raise해서 전체를 중단시켰다 — 두 파이프라인의 실패 동작이 서로
다르면 운영 중 오류를 파악하기 어렵다는 판단에 따라, A/B 모두 "첫 실패 시 즉시
중단"으로 통일하기로 함(legacy와 다른 지점, ism-adapter-project-decisions
메모리 참고).

이 서비스는 resource/metering push보다 먼저 실행되어야 한다(legacy 실행 순서:
account → contract → resource → metering) — 계약(tContract/tServiceMap)이
계정을 참조하므로, 계정이 없으면 계약 push가 실패한다.
"""

from dataclasses import dataclass

from loguru import logger

from ism_adapter.clients.ism_client import ISMClient
from ism_adapter.repositories.account_repository import AccountRepository
from ism_adapter.transformers.account import AccountTransformer


class AccountPushError(Exception):
    """계정 push가 실패했을 때(HTTP 오류 또는 ISM 응답의 error 필드) 발생.

    발생 즉시 나머지 계정 push를 중단시킨다 — 호출부(cli.py)가 그대로 전파받아
    비정상 종료(exit code 1)로 이어진다.
    """


@dataclass
class AccountPushResult:
    total_accounts: int
    success: int


def push_accounts(
    account_repo: AccountRepository,
    ism_client: ISMClient,
) -> AccountPushResult:
    transformer = AccountTransformer()

    account_ids = account_repo.get_account_ids_with_project()
    accounts = account_repo.get_accounts(account_ids)

    success = 0

    for account in accounts:
        payload = transformer.to_account_payload(account)
        try:
            result = ism_client.put_account(payload)
        except Exception as e:
            logger.error("Failed to push account_id={} to ISM: {}", account.account_id, e)
            raise AccountPushError(f"account_id={account.account_id} push failed") from e

        if isinstance(result, dict) and result.get("error"):
            logger.error(
                "ISM rejected account_id={}: {}",
                account.account_id,
                result.get("error"),
            )
            raise AccountPushError(
                f"account_id={account.account_id} rejected by ISM: {result.get('error')}"
            )

        success += 1

    result = AccountPushResult(total_accounts=len(accounts), success=success)
    logger.info(
        "Pushed accounts: total={} success={}",
        result.total_accounts,
        result.success,
    )
    return result

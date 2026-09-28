"""portal_db(+billing_db) 계약 정보 → ISM(THAAD) 계약 push 파이프라인.

legacy `ixc_daemon_ism.py`의 `ism/contract.py::ContractClass.main()`을
재현한다. 계약도 account처럼 project 1건당 1회 개별 POST다(20건 배치 아님 —
legacy `requests.post(url, json=[project_data])`).

**첫 실패 시 즉시 중단한다** — legacy contract.py 원본 동작(한 project 실패 시
즉시 raise)과 일치하며, account_service.py(A)도 2026-09-17에 이 방식으로
통일했다(ism-adapter-project-decisions 메모리 참고, account.py 원래는 계정별
예외 격리였으나 A/B 실패 동작을 통일하기 위해 변경).

이 서비스는 account push(A) 다음, resource/metering push보다 먼저 실행되어야
한다(legacy 실행 순서: account → contract → resource → metering) — 계약이
tServiceMap(sType='Account')으로 계정을 참조하므로, 계정이 먼저 있어야 한다.
"""

from dataclasses import dataclass

from loguru import logger

from ism_adapter.clients.ism_client import ISMClient
from ism_adapter.repositories.contract_repository import ContractRepository
from ism_adapter.transformers.account import ContractTransformer


class ContractPushError(Exception):
    """계약 push가 실패했을 때(HTTP 오류 또는 ISM 응답의 error 필드) 발생.

    발생 즉시 나머지 project push를 중단시킨다.
    """


@dataclass
class ContractPushResult:
    total_projects: int
    success: int


def push_contracts(
    contract_repo: ContractRepository,
    ism_client: ISMClient,
) -> ContractPushResult:
    transformer = ContractTransformer()

    projects = contract_repo.get_projects()

    success = 0

    for project in projects:
        payload = transformer.to_contract_payload(project)
        try:
            result = ism_client.put_contract(payload)
        except Exception as e:
            logger.error("Failed to push project_id={} to ISM: {}", project.project_id, e)
            raise ContractPushError(f"project_id={project.project_id} push failed") from e

        if isinstance(result, dict) and result.get("error"):
            logger.error(
                "ISM rejected project_id={}: {}",
                project.project_id,
                result.get("error"),
            )
            raise ContractPushError(
                f"project_id={project.project_id} rejected by ISM: {result.get('error')}"
            )

        success += 1

    result = ContractPushResult(total_projects=len(projects), success=success)
    logger.info(
        "Pushed contracts: total={} success={}",
        result.total_projects,
        result.success,
    )
    return result

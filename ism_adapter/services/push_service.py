"""metering-api usage → ISM push 파이프라인.

상태를 갖지 않는다(2026-09-15 결정) — 매 실행마다 지정된 기간의 전체 usage를
metering-api에서 조회해 ISM에 다시 push한다. 여러 자원으로 확장되며 "어디까지
push했는지" 추적이 필요한 공통 패턴이 보이면 자체 상태 저장소를 추가하기로
보류함(ism-adapter-project-decisions 메모리 참고).

resources push → meterings push 순서를 반드시 지킨다 — THAAD는 metering push
시 동일 mID로 등록된 resource를 먼저 찾아야 처리하므로(2026-09-15 실측 확인),
순서가 바뀌면 metering push가 전부 실패한다.
"""

from dataclasses import dataclass

from loguru import logger

from ism_adapter.clients.ism_client import ISMClient
from ism_adapter.clients.metering_api_client import MeteringAPIClient
from ism_adapter.repositories import ProjectRepository
from ism_adapter.transformers import TRANSFORMERS


@dataclass
class PushResult:
    resource_type: str
    total_usages: int
    pushed: int
    skipped_no_project: int
    skipped_excluded: int
    resource_errors: int
    metering_errors: int


def _count_errors(results: list[dict]) -> int:
    """THAAD 응답 항목 중 error를 포함한 것의 개수.

    2026-09-15 실측: list 요청은 항목별 개별 try/catch로 처리되고, 실패한
    항목은 HTTP 에러가 아니라 응답 배열 안의 개별 error로 나타난다
    (helper_make_error_message 결과가 섞여 반환됨).
    """
    return sum(1 for r in results if isinstance(r, dict) and r.get("error"))


def push_resource_type(
    resource_type: str,
    period_start: str,
    period_end: str,
    metering_client: MeteringAPIClient,
    project_repo: ProjectRepository,
    ism_client: ISMClient,
) -> PushResult:
    transformer = TRANSFORMERS.get(resource_type)
    if transformer is None:
        raise ValueError(
            f"Unsupported resource_type: {resource_type} "
            f"(supported: {sorted(TRANSFORMERS)})"
        )

    usages = metering_client.list_metering(resource_type, period_start, period_end)

    tenant_ids = list({u["tenant_id"] for u in usages if u.get("tenant_id")})
    projects = project_repo.get_by_tenant_ids(tenant_ids)

    resource_items = []
    metering_items = []
    skipped = 0
    excluded = 0

    for usage in usages:
        if hasattr(transformer, "is_excluded") and transformer.is_excluded(usage):
            excluded += 1
            continue

        tenant_id = usage.get("tenant_id")
        project = projects.get(tenant_id) if tenant_id else None
        if project is None:
            logger.warning(
                "No project mapping for tenant_id={} (resource_id={}), skipping",
                tenant_id,
                usage.get("resource_id"),
            )
            skipped += 1
            continue

        payload = transformer.to_resource_payload(usage, project)
        resource_items.append(payload.resource_item)
        metering_items.append(payload.metering_item)

    resource_results = ism_client.put_resources(resource_items)
    metering_results = ism_client.put_meterings(metering_items)

    result = PushResult(
        resource_type=resource_type,
        total_usages=len(usages),
        pushed=len(metering_items),
        skipped_no_project=skipped,
        skipped_excluded=excluded,
        resource_errors=_count_errors(resource_results),
        metering_errors=_count_errors(metering_results),
    )
    logger.info(
        "Pushed resource_type={}: total={} pushed={} skipped_no_project={} "
        "skipped_excluded={} resource_errors={} metering_errors={}",
        result.resource_type,
        result.total_usages,
        result.pushed,
        result.skipped_no_project,
        result.skipped_excluded,
        result.resource_errors,
        result.metering_errors,
    )
    return result

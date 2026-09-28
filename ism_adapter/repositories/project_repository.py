"""portal_db(project)를 조회하는 repository.

주의: project 테이블은 이 서비스가 소유하지 않는다(ixcs-api-service도
migration을 소유하지 않는 것으로 조사됨 — 진짜 스키마 주인은 2026-09-15 기준
불명). 이 모듈이 project 접근의 유일한 경로여야 하며, 절대 쓰기를 시도하지
않는다 — 단, 이 DB 계정 자체는 읽기 전용이 아니라 ixcs-api-service와 동일한
쓰기 가능 계정이라(2026-09-15 확인), 이 약속은 DB 권한이 아닌 코드 레벨
약속일 뿐이다.

이 repository는 나중에 ixcs-api-service의 조회 전용 API로 교체하기 쉽도록
반환 타입(ProjectInfo)을 "이미 API 응답인 것처럼" 고정해서 설계했다 — 상세
근거는 ism-adapter-project-decisions 메모리 참고.

2026-09-15 THAAD/legacy 실측 결과, ISM push(network/router)에 실제로 쓰이는
project 필드는 `project.id`(contract_service_map.sServiceKey)와
`project.provider_id`(metering.sProviderId) 둘 뿐이다. no_pay/insider_use는
이 push 스펙과 무관해 제거했다(THAAD 실측 — no_pay는 별도 /v1/contracts
계약 레벨 속성, insider_use는 THAAD에 아예 없는 개념).

⚠️ 컬럼명 2026-09-15 실측 정정(사용자 DB 직접 확인): metering-api usage의
`tenant_id`와 매칭하는 컬럼은 `project.provider_project_id`다 — `project.
tenant_id`라는 컬럼은 존재하지 않는다(최초 구현 시 잘못 가정했다가 실제
쿼리 실패로 정정). `project.provider_id`는 테넌트 식별자가 아니라 provider
자체의 ID이며 그대로 유효하다.
"""

from dataclasses import dataclass

from sqlalchemy import Table, select
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ProjectInfo:
    project_id: str
    tenant_id: str
    provider_id: str


class ProjectRepository:
    def __init__(self, engine: Engine, project_table: Table):
        self._engine = engine
        self._project = project_table

    def get_by_tenant_id(self, tenant_id: str) -> ProjectInfo | None:
        results = self.get_by_tenant_ids([tenant_id])
        return results.get(tenant_id)

    def get_by_tenant_ids(self, tenant_ids: list[str]) -> dict[str, ProjectInfo]:
        """tenant_id(=provider_project_id) -> ProjectInfo 매핑. 존재하지 않는
        tenant_id는 결과에서 빠진다.

        `apps/ism/resources/services.py`의 벌크 조회 패턴(tenant_id__in)과
        동일하게, 자원 목록 전체를 한 번에 매핑해 N+1 쿼리를 피한다.
        """
        if not tenant_ids:
            return {}

        stmt = select(
            self._project.c.id.label("project_id"),
            self._project.c.provider_project_id.label("tenant_id"),
            self._project.c.provider_id,
        ).where(self._project.c.provider_project_id.in_(tenant_ids))

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return {
            row["tenant_id"]: ProjectInfo(
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
                provider_id=row["provider_id"],
            )
            for row in rows
        }

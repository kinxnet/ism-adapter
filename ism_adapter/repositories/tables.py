"""portal_db의 project 테이블 중, 이 서비스가 실제로 쓰는 컬럼만 명시적으로
선언한다 (전체 스키마를 autoload/reflect하지 않는다).

이 서비스는 project 테이블의 소유자가 아니므로, 스키마 전체를 신뢰하고
가져오기보다 "우리가 쓰는 컬럼만 안다"는 최소 계약을 코드로 명시하는 편이 더
안전하다 — ixcs-api-service가 스키마를 바꾸면 여기서 쓰는 컬럼이 없어졌을 때
바로 에러로 드러나야 한다(자세한 근거는 ism-adapter-project-decisions 메모리).

2026-09-15 실측(사용자 DB 직접 확인)으로 컬럼명 정정:
- `provider_project_id` — OpenStack 등 provider 쪽 project/tenant UUID.
  metering-api usage의 `tenant_id`와 매칭하는 키. legacy(`ism/resource.py`
  `run_network`)의 `provider_project_id == tenant_id` 매칭과 동일한 개념.
- `provider_id` — provider(플랫폼) 자체의 ID. ISM metering payload의
  `sProviderId`에 쓰인다. **테넌트 식별자가 아니다** — 최초 구현 시
  `tenant_id`라는 이름으로 잘못 가정했다가 실측 후 정정.

2026-09-16 타입 정정(사용자 DB 직접 `SHOW COLUMNS` 확인): `project.id`는
Integer가 아니라 **varchar(255)의 UUID 문자열**이다(예:
`a9518e45-bd5e-493a-b78c-57778a69cb51`). CommonModel(ixcs-api-service
공통 베이스, `id = CharField(pk, default=uuid4)`)을 상속하는 모든 테이블이
동일하다 — account/user/role/paymethod/account_extend/provider 전부 포함.
이전에 `Column("id", Integer, ...)`로 잘못 선언했던 건 SQLAlchemy가 실제
컬럼 타입(varchar)을 따라 문자열을 그대로 반환해줘서 데이터가 깨지진
않았지만(THAAD로 보낸 sServiceKey 값 자체는 올바른 UUID였음), 타입 선언
자체는 버그였다 — String으로 정정.
"""

from sqlalchemy import Column, MetaData, String, Table

metadata = MetaData()

project_table = Table(
    "project",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("provider_project_id", String(255)),
    Column("provider_id", String(255)),
)

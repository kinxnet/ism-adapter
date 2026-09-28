"""portal_db의 계정/계약 관련 테이블 중, 이 서비스가 실제로 쓰는 컬럼만
명시적으로 선언한다 (`tables.py`와 동일 원칙 — 전체 스키마 reflect 안 함).

2026-09-16 사용자 DB 직접 `SHOW COLUMNS` 확인으로 전부 실측 검증됨. 모든 PK/FK는
ixcs-api-service의 `CommonModel`(id = CharField(pk, default=uuid4))을 상속해
**varchar(255)의 UUID 문자열**이다 — Integer 아님(tables.py의 project_table도
2026-09-16에 동일한 이유로 정정됨).

Django 모델과 실제 DB 컬럼명이 다른 경우만 표로 정리:
- Account → 테이블 `account`
- AccountMember(Django 클래스명) → 테이블 `account_user` (legacy AccountUser와 동일)
- User → 테이블 `user`. name/phone/cellphone은 평문(`name` 등, Django property로는
  `_name`)과 암호화(`name_encrypted` 등, AES-256-GCM + ixcs-api-service 전용
  `settings.ENCRYPT_KEY`) 컬럼이 공존. **2026-09-16 결정: 평문 컬럼만 읽고
  `*_encrypted`는 무시한다** — 암호화 키가 ism-adapter 스코프 밖(별도 secret)일
  뿐 아니라, 설령 키를 확보해도 암호문을 그대로 THAAD에 넘기는 건 의미가 없다
  (THAAD tAccountMember 저장 코드는 이미 죽어있어 지금 당장 영향 없고, "나중에
  API 전환 시 자동으로 정확해진다"는 이 필드를 채우는 원래 취지도 암호문을 넣으면
  깨진다 — API 전환 시점엔 API가 이미 복호화된 값을 내려줄 것이므로 지금 암호문을
  선반영할 이유가 없다). 결과적으로 최근(암호화 전환 이후) 가입한 사용자는
  이름/전화가 빈 값으로 나갈 수 있으나, 실질적 영향 없음.
- Role → 테이블 `role`
- Paymethod → 테이블 `paymethod`. `is_active`(CommonModel 공통 필드)와
  `is_confirm`(Paymethod 고유 필드)이 **둘 다 존재** — legacy `Paymethod.is_active==1`은
  전자를 가리킴(둘을 혼동하지 말 것).
- AccountExtent(Django 클래스명, 오타 포함) → 테이블 `account_extend`
- Project → tables.py의 project_table과 별개로 여기서는 계약 생성에 필요한
  넓은 컬럼 세트로 다시 선언(같은 테이블, 다른 용도의 별도 쿼리 — project_repository.py
  설계 때와 동일 원칙).
- Provider(legacy 이름) = Zone(Django 모델명) → 테이블 `provider`. B(계약 push)
  착수 시 `name`(provider 이름, THAAD 계약 payload의 `provider_name`) 컬럼 추가.
- StabilizationProject(legacy 전용, Django 모델 없음/portal_db 자체 테이블) →
  테이블 `stabilization_project`. **2026-09-17 실측(SHOW COLUMNS)** — legacy
  SQLAlchemy 모델(`models_ixcloud.py`)과 타입이 대체로 일치하나
  `project_id`만 legacy 선언(`String(36)`)과 달리 실제로는 `varchar(255)`라
  실측값 기준으로 선언함(project.id가 UUID라 36자로 충분하지만, 컬럼 자체는
  더 넓게 잡혀 있음 — 실사용엔 영향 없음).
"""

from sqlalchemy import Column, DateTime, MetaData, SmallInteger, String, Table

metadata = MetaData()

account_table = Table(
    "account",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(255)),
    Column("created_at", DateTime),
    Column("is_active", SmallInteger),
    Column("is_deleted", SmallInteger),
)

account_user_table = Table(
    "account_user",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("account_id", String(36)),
    Column("user_id", String(36)),
    Column("role_id", String(255)),
    Column("accounting", SmallInteger),
)

user_table = Table(
    "user",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(255)),
    Column("hashed_password", String(255)),
    Column("salt", String(255)),
    Column("confirm", SmallInteger),
    # name/phone/cellphone: 평문 + 암호화 컬럼 공존. 값 결정 로직은
    # account_repository.py에서 name_encrypted 우선으로 재현.
    Column("name", String(150)),
    Column("name_encrypted", String(255)),
    Column("phone", String(150)),
    Column("phone_encrypted", String(255)),
    Column("cellphone", String(150)),
    Column("cellphone_encrypted", String(255)),
    Column("email", String(150)),
)

role_table = Table(
    "role",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("is_master", SmallInteger),
)

paymethod_table = Table(
    "paymethod",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("account_id", String(36)),
    Column("is_active", SmallInteger),
    Column("method", String(150)),
    Column("payment_key", String(255)),
)

account_extend_table = Table(
    "account_extend",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("account_id", String(36)),
    Column("ceo_name", String(150)),
)

# 계약(Contract) 생성용 — tables.py의 project_table(자원 push 전용, 3개 필드)과
# 별개로, 계약에 필요한 넓은 컬럼 세트를 다시 선언한다.
contract_project_table = Table(
    "project",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("name", String(255)),
    Column("account_id", String(36)),
    Column("provider_project_id", String(255)),
    Column("provider_id", String(255)),
    Column("created_at", DateTime),
    Column("disabled_at", DateTime),
    Column("deleted_at", DateTime),
    Column("is_active", SmallInteger),
    Column("is_deleted", SmallInteger),
    Column("no_pay", SmallInteger),
)

provider_table = Table(
    "provider",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("name", String(150)),
    Column("is_deleted", SmallInteger),
)

stabilization_project_table = Table(
    "stabilization_project",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("is_active", SmallInteger),
    Column("period_start", DateTime),
    Column("period_end", DateTime),
    Column("account_id", String(36)),
    Column("project_id", String(255)),
    Column("resource_type", String(50)),
)

"""billing DB(ixcloud_billing 스키마, portal_db와 별개 엔진)의 테이블 중, 이
서비스가 실제로 쓰는 컬럼만 명시적으로 선언한다 (account_tables.py/tables.py와
동일 원칙).

2026-09-17 dev 환경 실측(`SHOW COLUMNS`) 기반. 같은 서버(1.201.137.199:3306,
계정 kinx)에 있지만 스키마가 다르므로(portal은 `ixcloud`, billing은
`ixcloud_billing`) SQLAlchemy Engine을 portal_url과 별개로 하나 더 연다
(DatabaseConfig.billing_url, 옵션 — 없으면 discount는 빈 배열로 폴백).

charge_project_discount_month_policy: legacy `models_billing.py::
ChargeProjectDiscountPolicy`와 동일 테이블. 이 서비스가 쓰는 컬럼만 선언.
"""

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, SmallInteger, String, Table

metadata = MetaData()

charge_project_discount_policy_table = Table(
    "charge_project_discount_month_policy",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("is_active", SmallInteger),
    Column("usage_month", String(6)),
    Column("charge_month", String(6)),
    Column("account_id", String(36)),
    Column("project_id", String(255)),
    Column("resource_type", String(50)),
    Column("discount_type", String(50)),
    Column("amount", Float),
    Column("name", String(255)),
    Column("inserted_at", DateTime),
)

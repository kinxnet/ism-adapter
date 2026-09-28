"""portal_db(project/provider) + billing_db(discount) 조회 repository.

legacy `ixcloud_service/common/ixcdaemon/ism/contract.py::ContractClass`의
`get_projects()`, `mk_stabilization()`, `mk_discount_policy()`(discount 부분)를
SQLAlchemy Core로 재현한다.

billing 쪽 조회(get_discounts)는 billing_engine이 None이면(설정 없음, 2026-09-17
결정: 옵션) 빈 결과를 반환한다 — 계약 push 자체는 discount 없이도 동작해야
한다.
"""

from dataclasses import dataclass, field

import arrow
from sqlalchemy import select
from sqlalchemy.engine import Engine

from ism_adapter.repositories.account_tables import (
    account_table,
    contract_project_table,
    provider_table,
    stabilization_project_table,
)
from ism_adapter.repositories.billing_tables import charge_project_discount_policy_table


@dataclass(frozen=True)
class StabilizationInfo:
    resource_type: str
    period_start: object
    period_end: object
    is_active: int


@dataclass(frozen=True)
class DiscountInfo:
    resource_type: str
    discount_type: str
    amount: float
    usage_month: str
    name: str | None


@dataclass(frozen=True)
class ProjectContractInfo:
    project_id: str
    name: str | None
    account_id: str
    provider_project_id: str | None
    provider_id: str
    provider_name: str | None
    created_at: object
    disabled_at: object
    deleted_at: object
    is_active: int
    is_deleted: int
    no_pay: int | None
    stabilizations: list[StabilizationInfo] = field(default_factory=list)
    discounts: list[DiscountInfo] = field(default_factory=list)


class ContractRepository:
    def __init__(self, portal_engine: Engine, billing_engine: Engine | None = None):
        self._portal_engine = portal_engine
        self._billing_engine = billing_engine

    def get_projects(self) -> list[ProjectContractInfo]:
        """계약 push 대상 project 전체.

        legacy: `Project JOIN Provider JOIN Account, WHERE provider.is_deleted
        == False AND account.is_active == True` (project 자체의 is_active/
        is_deleted는 필터하지 않는다 — 삭제/비활성 project도 대상에 포함해서
        status를 'S'로 push하기 위함, mk_data()의 status 계산 참고).
        """
        stmt = (
            select(
                contract_project_table.c.id.label("project_id"),
                contract_project_table.c.name,
                contract_project_table.c.account_id,
                contract_project_table.c.provider_project_id,
                contract_project_table.c.provider_id,
                provider_table.c.name.label("provider_name"),
                contract_project_table.c.created_at,
                contract_project_table.c.disabled_at,
                contract_project_table.c.deleted_at,
                contract_project_table.c.is_active,
                contract_project_table.c.is_deleted,
                contract_project_table.c.no_pay,
            )
            .select_from(contract_project_table)
            .join(provider_table, provider_table.c.id == contract_project_table.c.provider_id)
            .join(account_table, account_table.c.id == contract_project_table.c.account_id)
            .where(
                provider_table.c.is_deleted == 0,
                account_table.c.is_active == 1,
            )
        )

        with self._portal_engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        project_ids = [row["project_id"] for row in rows]
        stabilizations_by_project = self._get_stabilizations(project_ids)
        discounts_by_project = self._get_discounts(project_ids)

        return [
            ProjectContractInfo(
                project_id=row["project_id"],
                name=row["name"],
                account_id=row["account_id"],
                provider_project_id=row["provider_project_id"],
                provider_id=row["provider_id"],
                provider_name=row["provider_name"],
                created_at=row["created_at"],
                disabled_at=row["disabled_at"],
                deleted_at=row["deleted_at"],
                is_active=row["is_active"],
                is_deleted=row["is_deleted"],
                no_pay=row["no_pay"],
                stabilizations=stabilizations_by_project.get(row["project_id"], []),
                discounts=discounts_by_project.get(row["project_id"], []),
            )
            for row in rows
        ]

    def _get_stabilizations(self, project_ids: list[str]) -> dict[str, list[StabilizationInfo]]:
        """legacy `mk_stabilization()`: project_id로 stabilization_project 조회,
        필터 없이 전부 가져온다(resource_type=='lbs' 제외는 transformer가 담당 —
        legacy도 조회가 아니라 payload 조합 단계에서 걸렀다).
        """
        if not project_ids:
            return {}

        stmt = select(
            stabilization_project_table.c.project_id,
            stabilization_project_table.c.resource_type,
            stabilization_project_table.c.period_start,
            stabilization_project_table.c.period_end,
            stabilization_project_table.c.is_active,
        ).where(stabilization_project_table.c.project_id.in_(project_ids))

        with self._portal_engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        result: dict[str, list[StabilizationInfo]] = {}
        for row in rows:
            result.setdefault(row["project_id"], []).append(
                StabilizationInfo(
                    resource_type=row["resource_type"],
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    is_active=row["is_active"],
                )
            )
        return result

    def _get_discounts(self, project_ids: list[str]) -> dict[str, list[DiscountInfo]]:
        """legacy `mk_discount_policy()`: project_id + 이번달(charge_month) +
        is_active==True로 필터. billing_engine이 없으면(옵션 미설정) 빈 dict.
        """
        if not project_ids or self._billing_engine is None:
            return {}

        charge_month = arrow.utcnow().to("Asia/Seoul").format("YYYYMM")

        stmt = select(
            charge_project_discount_policy_table.c.project_id,
            charge_project_discount_policy_table.c.resource_type,
            charge_project_discount_policy_table.c.discount_type,
            charge_project_discount_policy_table.c.amount,
            charge_project_discount_policy_table.c.usage_month,
            charge_project_discount_policy_table.c.name,
        ).where(
            charge_project_discount_policy_table.c.project_id.in_(project_ids),
            charge_project_discount_policy_table.c.charge_month == charge_month,
            charge_project_discount_policy_table.c.is_active == 1,
        )

        with self._billing_engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        result: dict[str, list[DiscountInfo]] = {}
        for row in rows:
            result.setdefault(row["project_id"], []).append(
                DiscountInfo(
                    resource_type=row["resource_type"],
                    discount_type=row["discount_type"],
                    amount=row["amount"],
                    usage_month=row["usage_month"],
                    name=row["name"],
                )
            )
        return result

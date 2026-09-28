"""portal_db(account/account_user/user/role/paymethod/account_extend)를 조회하는
repository. legacy `ixc_daemon_ism.py`의 `ism/account.py`가 하던 대상 선정과
동일한 로직을 SQLAlchemy Core로 재현한다.

project_repository.py와 동일 원칙: project를 소유하지 않듯 이 서비스는
account/user 등도 소유하지 않으므로, 쓰는 컬럼만 최소 계약으로 선언한
account_tables.py 위에서 동작한다.

User.name/phone/cellphone의 암호화 컬럼(name_encrypted 등)은 읽지 않는다 —
근거는 account_tables.py 상단 docstring과 ism-adapter-project-decisions 메모리
참고. 평문 컬럼만 읽으므로 최근 가입한 사용자는 이름/전화가 빈 값일 수 있다.
"""

from dataclasses import dataclass, field

from sqlalchemy import distinct, func, select
from sqlalchemy.engine import Engine

from ism_adapter.repositories.account_tables import (
    account_extend_table,
    account_table,
    account_user_table,
    contract_project_table,
    paymethod_table,
    role_table,
    user_table,
)


@dataclass(frozen=True)
class MemberInfo:
    account_user_id: str
    accounting: int | None
    username: str
    hashed_password: str | None
    salt: str | None
    name: str | None
    phone: str | None
    cellphone: str | None
    email: str | None
    is_master: bool


@dataclass(frozen=True)
class AccountInfo:
    account_id: str
    name: str | None
    created_at: object
    is_active: int
    is_deleted: int
    payment_key: str | None
    ceo_name: str | None
    members: list[MemberInfo] = field(default_factory=list)


class AccountRepository:
    def __init__(self, engine: Engine):
        self._engine = engine

    def get_account_ids_with_project(self) -> list[str]:
        """project를 1개 이상 가진 account_id 목록.

        legacy: `Account JOIN Project GROUP BY Account.id HAVING count(Project.id) > 0`.
        project_table을 여기서 다시 선언하지 않고 account_tables.py의
        contract_project_table(계약용으로 이미 선언된 넓은 project)을 재사용한다.
        """
        stmt = (
            select(account_table.c.id)
            .select_from(account_table)
            .join(
                contract_project_table,
                contract_project_table.c.account_id == account_table.c.id,
            )
            .group_by(account_table.c.id)
            .having(func.count(distinct(contract_project_table.c.id)) > 0)
        )

        with self._engine.connect() as conn:
            return [row[0] for row in conn.execute(stmt)]

    def get_accounts(self, account_ids: list[str]) -> list[AccountInfo]:
        """account_id 목록에 대해 계정 + 담당자(confirm==1인 멤버만) + 결제수단 +
        대표자명을 한 번에 조회한다.

        members가 0명인 계정은 legacy(`_mk_add_data`가 None을 반환)와 동일하게
        결과에서 제외한다 — 호출부(account_service.py 예정)에서 별도 skip 처리
        불필요.
        """
        if not account_ids:
            return []

        accounts = self._get_account_rows(account_ids)
        members_by_account = self._get_members_by_account(account_ids)
        payment_key_by_account = self._get_payment_keys(account_ids)
        ceo_name_by_account = self._get_ceo_names(account_ids)

        results = []
        for account_id, row in accounts.items():
            members = members_by_account.get(account_id, [])
            if not members:
                continue
            results.append(
                AccountInfo(
                    account_id=account_id,
                    name=row["name"],
                    created_at=row["created_at"],
                    is_active=row["is_active"],
                    is_deleted=row["is_deleted"],
                    payment_key=payment_key_by_account.get(account_id),
                    ceo_name=ceo_name_by_account.get(account_id),
                    members=members,
                )
            )
        return results

    def _get_account_rows(self, account_ids: list[str]) -> dict[str, dict]:
        stmt = select(
            account_table.c.id,
            account_table.c.name,
            account_table.c.created_at,
            account_table.c.is_active,
            account_table.c.is_deleted,
        ).where(account_table.c.id.in_(account_ids))

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return {row["id"]: dict(row) for row in rows}

    def _get_members_by_account(self, account_ids: list[str]) -> dict[str, list[MemberInfo]]:
        """user.confirm == 1인 멤버만. role.is_master 여부도 함께 가져와서
        상위(account_service.py)에서 master 선정에 쓸 수 있게 한다.

        legacy는 `member.role.is_master`가 role_id가 없을 때(NULL FK)도 접근
        가능했지만, 여기서는 LEFT JOIN으로 role이 없는 멤버도 유실 없이 포함하고
        is_master는 False로 취급한다.
        """
        stmt = (
            select(
                account_user_table.c.account_id,
                account_user_table.c.id.label("account_user_id"),
                account_user_table.c.accounting,
                user_table.c.username,
                user_table.c.hashed_password,
                user_table.c.salt,
                user_table.c.name,
                user_table.c.phone,
                user_table.c.cellphone,
                user_table.c.email,
                role_table.c.is_master,
            )
            .select_from(account_user_table)
            .join(user_table, user_table.c.id == account_user_table.c.user_id)
            .outerjoin(role_table, role_table.c.id == account_user_table.c.role_id)
            .where(
                account_user_table.c.account_id.in_(account_ids),
                user_table.c.confirm == 1,
            )
        )

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        members_by_account: dict[str, list[MemberInfo]] = {}
        for row in rows:
            members_by_account.setdefault(row["account_id"], []).append(
                MemberInfo(
                    account_user_id=row["account_user_id"],
                    accounting=row["accounting"],
                    username=row["username"],
                    hashed_password=row["hashed_password"],
                    salt=row["salt"],
                    name=row["name"],
                    phone=row["phone"],
                    cellphone=row["cellphone"],
                    email=row["email"],
                    is_master=bool(row["is_master"]),
                )
            )
        return members_by_account

    def _get_payment_keys(self, account_ids: list[str]) -> dict[str, str]:
        """is_active==1 AND method=='card-auto' AND payment_key 존재하는 첫 건.

        legacy: `[p for p in account.paymethod if p.is_active==1 and
        p.method=='card-auto' and len(p.payment_key)>0][0]`와 동일 — 여러 건이면
        임의의 하나(정렬 보장 없음, legacy도 정렬 없이 첫 건이었으므로 동일 특성).
        """
        stmt = select(
            paymethod_table.c.account_id,
            paymethod_table.c.payment_key,
        ).where(
            paymethod_table.c.account_id.in_(account_ids),
            paymethod_table.c.is_active == 1,
            paymethod_table.c.method == "card-auto",
            paymethod_table.c.payment_key.isnot(None),
            paymethod_table.c.payment_key != "",
        )

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        payment_key_by_account: dict[str, str] = {}
        for row in rows:
            payment_key_by_account.setdefault(row["account_id"], row["payment_key"])
        return payment_key_by_account

    def _get_ceo_names(self, account_ids: list[str]) -> dict[str, str]:
        """legacy: `account.extend[0].ceo_name if account.extend else None`.
        account_extend는 계정당 0~1건을 전제(legacy도 리스트의 첫 건만 사용).
        """
        stmt = select(
            account_extend_table.c.account_id,
            account_extend_table.c.ceo_name,
        ).where(account_extend_table.c.account_id.in_(account_ids))

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        ceo_name_by_account: dict[str, str] = {}
        for row in rows:
            ceo_name_by_account.setdefault(row["account_id"], row["ceo_name"])
        return ceo_name_by_account

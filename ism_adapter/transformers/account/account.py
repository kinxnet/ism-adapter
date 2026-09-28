"""portal_db 계정 정보(AccountInfo) -> THAAD `/v1/accounts` push payload 변환.

legacy `ixcloud_service/common/ixcdaemon/ism/account.py::_mk_add_data()`를
그대로 재현한다. 원본은 SQLAlchemy ORM 관계(`account.member`, `member.user`,
`member.role`, `account.paymethod`, `account.extend`)를 직접 순회했지만, 여기서는
account_repository.py가 이미 조회·필터링(user.confirm==1, paymethod 조건,
extend 등)을 끝낸 AccountInfo/MemberInfo를 받아 payload 조합만 담당한다.

**결정적으로 다른 점 하나**: User.name/phone/cellphone의 암호화 컬럼
(name_encrypted 등)은 repository 단계에서부터 읽지 않는다 — legacy는 애초에
이 컬럼이 없던 시절 코드라 이 문제 자체가 없었지만, 지금은 최근 가입자의
이름/전화가 빈 값으로 나갈 수 있다(ism-adapter-project-decisions 메모리 참고,
실질 영향 없음 — THAAD tAccountMember 저장 경로 자체가 죽어있음).

**account payload 구조** (`ism/account.py::_mk_add_data`):
    {
      "service_type": "cloud",
      "account": {
          "sName": <account.name>,
          "sAccountID": <master.user.username>,
          "sPassword": <master.user.hashed_password>,
          "sSalt": <master.user.salt>,
          "sCustomerType": "A",
          "dtRegister": <account.created_at, "YYYY-MM-DD HH:mm:ss">,
          "sStatus": <"Y"|"S"|"W">,
          "sPaymentKey": <payment_key or None>,
          "sRemark": "클라우드 자동등록",
      },
      "account_members": [ {sDutyType, sName, sPhone, sMobile, sEmail, sReferrer}, ... ],
      "customer": {
          "sName": <account.name>, "sType": "C",
          "sOwnerNm": <extend.ceo_name or "">, "sStatus": <위와 동일>,
      },
      "service_map": {"sService": "cloud", "sServiceKey": <account.id>},
    }

members가 0명인 계정은 account_repository.py가 이미 결과에서 제외하므로 여기서는
항상 1명 이상을 전제로 한다(legacy의 `if len(members): ... else: account_data=None`
분기 중 None 쪽은 repository가 대신 처리).
"""

import arrow

from ism_adapter.repositories.account_repository import AccountInfo, MemberInfo

_STATUS_DELETED = "S"
_STATUS_INACTIVE = "W"
_STATUS_ACTIVE = "Y"

_DUTY_BILLING = "C"  # 요금담당자
_DUTY_BUSINESS = "E"  # 업무담당자


def _resolve_status(account: AccountInfo) -> str:
    if account.is_deleted == 1:
        return _STATUS_DELETED
    if account.is_active == 0:
        return _STATUS_INACTIVE
    return _STATUS_ACTIVE


def _resolve_master(members: list[MemberInfo]) -> MemberInfo:
    masters = [member for member in members if member.is_master]
    return masters[0] if masters else members[0]


def _mk_member_item(member: MemberInfo, duty_type: str) -> dict:
    return {
        "sDutyType": duty_type,
        "sName": member.name,
        "sPhone": member.phone,
        "sMobile": member.cellphone,
        "sEmail": member.email or member.username,
        "sReferrer": member.account_user_id,
    }


def _mk_account_members(members: list[MemberInfo]) -> list[dict]:
    if len(members) == 1:
        member = members[0]
        # legacy: 멤버가 1명뿐이면 요금담당자/업무담당자 둘 다로 동일 멤버를 중복 등록
        account_members = [
            _mk_member_item(member, _DUTY_BILLING),
            _mk_member_item(member, _DUTY_BUSINESS),
        ]
    else:
        account_members = [
            _mk_member_item(member, _DUTY_BILLING if member.accounting == 1 else _DUTY_BUSINESS)
            for member in members
        ]

    # 과금 담당자가 하나도 지정 안 되어 있으면 첫 번째를 강제로 과금담당자로 지정
    if not any(item["sDutyType"] == _DUTY_BILLING for item in account_members):
        account_members[0]["sDutyType"] = _DUTY_BILLING

    return account_members


class AccountTransformer:
    def to_account_payload(self, account: AccountInfo) -> dict:
        master = _resolve_master(account.members)
        status = _resolve_status(account)

        return {
            "service_type": "cloud",
            "account": {
                "sName": account.name,
                "sAccountID": master.username,
                "sPassword": master.hashed_password,
                "sSalt": master.salt,
                "sCustomerType": "A",
                "dtRegister": arrow.get(account.created_at).format("YYYY-MM-DD HH:mm:ss"),
                "sStatus": status,
                "sPaymentKey": account.payment_key,
                "sRemark": "클라우드 자동등록",
            },
            "account_members": _mk_account_members(account.members),
            "customer": {
                "sName": account.name,
                "sType": "C",
                "sOwnerNm": account.ceo_name or "",
                "sStatus": status,
            },
            "service_map": {
                "sService": "cloud",
                "sServiceKey": account.account_id,
            },
        }

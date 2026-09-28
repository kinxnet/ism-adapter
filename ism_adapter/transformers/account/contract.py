"""portal_db 계약(project) 정보(ProjectContractInfo) -> THAAD `/v1/contracts`
push payload 변환.

legacy `ixcloud_service/common/ixcdaemon/ism/contract.py::ContractClass.
mk_data()`(+ `mk_stabilization()`, `mk_discount_policy()`)를 그대로 재현한다.
repository(contract_repository.py)가 이미 대상 선정·stabilization/discount
조회를 끝낸 ProjectContractInfo를 받아 payload 조합만 담당한다.

**payload 구조** (`ism/contract.py::mk_data`):
    {
      "service_type": "cloud",
      "service_map": {"sService": "cloud", "sType": "Contract", "sServiceKey": <project.id>},
      "account_service_map": {"sService": "cloud", "sType": "Account", "sServiceKey": <project.account_id>},
      "contract": {
          "dtStart": <project.created_at, KST, YYYY-MM-DD>,
          "dtCharge": <dtStart와 동일>,
          "dtEnd": <상태에 따라 계산>,
          "dtStatus": <종료 상태일 때만 dtEnd와 동일, 그 외 None>,
          "sName": <project.name>,
          "sStatus": <"Y"|"S">,
          "nBillDataType": 5,
          "arDetailInfo": {"setting": [{"billtype": "time"}], "project": {...}},
          "arDiscountOpt": {"stabilization": [...], "discount": [...]},
      },
    }

**status/dtEnd 계산** (project.is_deleted 우선, 그다음 is_active, 그 외 정상):
- is_deleted==1: sStatus='S', dtEnd=deleted_at(없으면 이번달 말일), dtStatus=dtEnd
- is_active==0:  sStatus='S', dtEnd=disabled_at(없으면 이번달 말일), dtStatus=dtEnd
- 그 외:         sStatus='Y', dtEnd=이번달 말일, dtStatus=None

**자원 타입 매핑(RESOURCE_TYPES)**: stabilization/discount의 resource_type은
legacy 자원 타입 키(예: 'instances')를 ism-adapter 자원 타입(예: 'instance')으로
변환한다. 매핑에 없는 값은 그대로 통과시킨다. 'lbs'(CloudJ 로드밸런서)는
전달하지 않는다(legacy 그대로).
"""

import arrow

from ism_adapter.repositories.contract_repository import DiscountInfo, ProjectContractInfo, StabilizationInfo

_KST = "Asia/Seoul"

_STATUS_ENDED = "S"
_STATUS_ACTIVE = "Y"

# legacy ContractClass.RESOURCE_TYPES — (ism-adapter 자원 타입, 안정화 설명) 매핑.
# discount에는 설명을 쓰지 않지만 stabilization과 동일 매핑을 공유한다.
_RESOURCE_TYPES: dict[str, tuple[str, str]] = {
    "instances": ("instance", "안정화(인스턴스)"),
    "images": ("os_image", "안정화(이미지)"),
    "image_snapshots": ("image_snapshot", "안정화(이미지스냅샷)"),
    "networks": ("network", "안정화(네트워크)"),
    "traffic": ("traffic", "안정화(트래픽)"),
    "floating_ips": ("floating_ip", "안정화(공인아이피)"),
    "volumes": ("volume", "안정화(볼륨)"),
    "backup_agents": ("backup_agent", "안정화(백업에이전트)"),
    "backup_storage": ("backup_storage", "안정화(백업스토리지)"),
    "lbs": ("lbaas", "안정화(로드밸런서-CloudJ)"),
    "lbaas_pools": ("lbaas", "안정화(로드밸런서-CloudK)"),
    "volume_snapshots": ("volume_snapshot", "안정화(볼륨스냅샷)"),
    "routers": ("router", "안정화(라우터)"),
    "k8s_cluster": ("k8s_cluster", "안정화(쿠버네티스 클러스터)"),
    "icr_registry": ("icr_registry", "안정화(컨테이너 레지스트리)"),
}

_DISCOUNT_TYPE_MAP = {"percentage": "percent", "price": "currency"}


def _to_kst_date(value: object | None) -> str | None:
    if value is None:
        return None
    return arrow.get(value).to(_KST).format("YYYY-MM-DD")


def _to_utc_isoformat(value: object | None) -> str | None:
    """legacy `model_to_dict()`의 DATETIME 변환(`arrow.get(v).replace(tzinfo=
    'UTC').isoformat()`)과 동일 — arDetailInfo.project에 실을 값은 KST 변환 없이
    UTC 그대로 ISO 문자열화한다(다른 필드의 KST 변환과 다른 지점, legacy 그대로)."""
    if value is None:
        return None
    return arrow.get(value).replace(tzinfo="UTC").isoformat()


def _month_end_kst() -> str:
    return arrow.utcnow().to(_KST).span("month")[1].format("YYYY-MM-DD")


def _resolve_status_and_end(project: ProjectContractInfo) -> tuple[str, str, str | None]:
    """(sStatus, dtEnd, dtStatus) 반환."""
    if project.is_deleted == 1:
        dt_end = _to_kst_date(project.deleted_at) or _month_end_kst()
        return _STATUS_ENDED, dt_end, dt_end
    if project.is_active == 0:
        dt_end = _to_kst_date(project.disabled_at) or _month_end_kst()
        return _STATUS_ENDED, dt_end, dt_end
    return _STATUS_ACTIVE, _month_end_kst(), None


def _mk_stabilization_items(stabilizations: list[StabilizationInfo]) -> list[dict]:
    items = []
    for s in stabilizations:
        if s.resource_type == "lbs":
            continue
        resource_type, description = _RESOURCE_TYPES.get(
            s.resource_type, (s.resource_type, f"안정화({s.resource_type})")
        )
        items.append(
            {
                "resource_type": resource_type,
                "start": _to_kst_date(s.period_start),
                "end": _to_kst_date(s.period_end),
                "is_active": s.is_active,
                "description": description,
            }
        )
    return items


def _mk_discount_items(discounts: list[DiscountInfo]) -> list[dict]:
    items = []
    for d in discounts:
        if d.resource_type == "lbs":
            continue
        resource_type, _ = _RESOURCE_TYPES.get(d.resource_type, (d.resource_type, ""))
        discount_type = _DISCOUNT_TYPE_MAP.get(d.discount_type, d.discount_type)
        items.append(
            {
                "resource_type": resource_type,
                "start": arrow.get(d.usage_month, "YYYYMM").format("YYYY-MM"),
                "end": "9999-12",
                "unit": discount_type,
                "amount": d.amount,
                "description": d.name,
            }
        )
    return items


class ContractTransformer:
    def to_contract_payload(self, project: ProjectContractInfo) -> dict:
        dt_start = _to_kst_date(project.created_at)
        status, dt_end, dt_status = _resolve_status_and_end(project)

        project_data = {
            "id": project.project_id,
            "name": project.name,
            "account_id": project.account_id,
            "provider_project_id": project.provider_project_id,
            "provider_id": project.provider_id,
            "provider_name": project.provider_name,
            "created_at": _to_utc_isoformat(project.created_at),
            "disabled_at": _to_utc_isoformat(project.disabled_at),
            "deleted_at": _to_utc_isoformat(project.deleted_at),
            "is_active": project.is_active,
            "is_deleted": project.is_deleted,
            "no_pay": project.no_pay,
        }

        return {
            "service_type": "cloud",
            "service_map": {
                "sService": "cloud",
                "sType": "Contract",
                "sServiceKey": project.project_id,
            },
            "account_service_map": {
                "sService": "cloud",
                "sType": "Account",
                "sServiceKey": project.account_id,
            },
            "contract": {
                "dtStart": dt_start,
                "dtCharge": dt_start,
                "dtEnd": dt_end,
                "dtStatus": dt_status,
                "sName": project.name,
                "sStatus": status,
                "nBillDataType": 5,
                "arDetailInfo": {
                    "setting": [{"billtype": "time"}],
                    "project": project_data,
                },
                "arDiscountOpt": {
                    "stabilization": _mk_stabilization_items(project.stabilizations),
                    "discount": _mk_discount_items(project.discounts),
                },
            },
        }

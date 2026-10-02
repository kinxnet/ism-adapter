"""instance usage -> THAAD push payload 변환.

mID 포맷은 legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_instance`
재현: `{resource_id}-flavor::{flavor_id}-charge_type::{charge_type}`.
`EncodedMidResourceTransformer`(transformers/base.py)를 상속해 `mid_fields`로
조합 순서만 선언한다.

**charge_type 정규화**: metering-api `usage["price_type"]`은 원문 그대로 온다
(표기 불일치 존재 — `On_Demand`/`On_demand` 혼재, 또는 `None`). legacy 월
리포트 판정 방식과 동일하게 대소문자 무시·공백 제거 후 `reserved`/`on_demand`로
시작하는지로 매칭해 legacy 실측 포맷(`meter.charge_type.title()` 결과)과 동일한
`Reserved`/`On_Demand`로 통일한다. null 또는 해석 불가 값은 legacy 포탈 API
`ResourcePriceType` 없을 때와 동일하게 `Reserved`로 폴백한다(`_normalize_charge_type`).

mID에 들어갈 `charge_type`은 usage의 원본 필드가 아니라 정규화를 거친 값이어야
하므로, `to_resource_payload()`에서 정규화 함수를 먼저 호출해 usage dict의
사본에 정규화된 `charge_type` 키를 추가한 뒤 `build_mid()`에 넘긴다.

**duration 필드**: metering-api `InstanceMeteringDTO`는 상태별 duration을
별도 필드로 제공한다(`active_duration_sec`, `pause_duration_sec`,
`suspend_duration_sec`, `power_off_duration_sec`). THAAD push 스펙에는
nActiveSec/nSuspendSec 두 필드만 있어(network/router와 동일 스펙, `base.py`
참고) `active_duration_sec`/`suspend_duration_sec`만 반영한다 —
`pause_duration_sec`/`power_off_duration_sec`에 대응하는 THAAD 필드는 없어
push하지 않는다(legacy도 이 두 상태를 별도로 과금 반영하지 않았다).
"""

from loguru import logger

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import (
    EncodedMidResourceTransformer,
    ResourcePayload,
    _to_kst,
)

_VALID_CHARGE_TYPES = {
    "reserved": "Reserved",
    "on_demand": "On_Demand",
}


def _normalize_charge_type(price_type: str | None) -> str:
    """`usage["price_type"]`을 legacy mID 포맷(`Reserved`/`On_Demand`)으로 정규화한다.

    대소문자 무시, 앞뒤 공백 제거 후 `reserved`/`on_demand`로 시작하는지로
    판정한다(legacy 월 리포트 판정 방식과 동일). `None`은 "Price type 미상"인
    정상 케이스라 로그 없이 `Reserved`로 폴백하고, 해석 불가능한 비어있지 않은
    문자열만 경고 로그를 남기고 동일하게 `Reserved`로 폴백한다.
    """
    normalized = (price_type or "").strip().lower()

    for prefix, canonical in _VALID_CHARGE_TYPES.items():
        if normalized.startswith(prefix):
            return canonical

    if normalized:
        logger.warning(
            "instance price_type을 해석할 수 없어 Reserved로 폴백합니다: {!r}",
            price_type,
        )
    return "Reserved"


class InstanceTransformer(EncodedMidResourceTransformer):
    resource_type = "instance"
    mid_fields = (
        ("flavor", "instance_flavor_id"),
        ("charge_type", "charge_type"),
    )

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        resource_id = usage["resource_id"]
        charge_type = _normalize_charge_type(usage.get("price_type"))
        mid = self.build_mid({**usage, "charge_type": charge_type})

        resource_item = {
            "service_type": "cloud",
            "contract_service_map": {
                "sService": "cloud",
                "sType": "Contract",
                "sServiceKey": project.project_id,
            },
            "resource": {
                "mID": mid,
                "sServiceType": "I",
                "dtStart": _to_kst(usage["created_at"]),
                "dtEnd": _to_kst(usage.get("deleted_at")),
                "arDetailInfo": {
                    "detail": {
                        "created_at": usage["created_at"],
                        "deleted_at": usage.get("deleted_at"),
                        "tenant_id": usage["tenant_id"],
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "resource_type": self.resource_type,
                        "instance_flavor_id": usage.get("instance_flavor_id"),
                        "charge_type": charge_type,
                    }
                },
            },
        }

        metering_item = {
            "service_type": "cloud",
            "metering": {
                "sResourceId": mid,
                "sProviderId": project.provider_id,
                "sTenantId": usage["tenant_id"],
                "dtPeriodStart": _to_kst(usage["min_started_at"]),
                "dtPeriodEnd": _to_kst(usage["max_ended_at"]),
                "nActiveSec": int(usage.get("active_duration_sec", 0)),
                "nSuspendSec": int(usage.get("suspend_duration_sec", 0)),
                "arDetailInfo": {
                    "detail": {
                        "period_start": usage["min_started_at"],
                        "period_end": usage["max_ended_at"],
                        "created_at": usage["created_at"],
                        "tenant_id": usage["tenant_id"],
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage.get("active_duration_sec", 0),
                        "resource_type": self.resource_type,
                        "instance_flavor_id": usage.get("instance_flavor_id"),
                        "charge_type": charge_type,
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid, resource_item=resource_item, metering_item=metering_item
        )

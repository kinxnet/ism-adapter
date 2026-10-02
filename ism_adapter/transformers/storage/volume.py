"""volume usage -> THAAD push payload 변환.

mID 포맷은 legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_volume`
재현: `{resource_id}-size::{size}-mIOPS::{max_iops}-bIOPS::{burst_iops}`.
`EncodedMidResourceTransformer`(transformers/base.py)를 상속해 `mid_fields`로
조합 순서만 선언한다.

metering-api `VolumeMeteringDTO`의 usage dict 키는 `size_gib`/`max_iops`/
`burst_iops`이지만, mID 라벨은 legacy 그대로 `size`/`mIOPS`/`bIOPS`다 — 라벨과
usage 키 이름이 다르다는 점에 주의.

**max_iops/burst_iops 0 치환**: 둘 다 볼륨 타입에 따라 IOPS 제한이 없으면
`None`으로 온다. legacy `max_IOPS or 0` / `burst_IOPS or 0`과 동일하게, mID
조립 전에만 usage 사본에서 두 값을 `0`으로 치환한다(`_zero_if_none`).
`arDetailInfo.detail`에는 원본 값을 그대로 싣는다(아래 참고).

volume은 resize로 size/IOPS가 바뀌면 metering-api가 구간을 나눠 별도 usage
row로 주므로(volume_history 설계), instance처럼 상태별 duration 분리가 필요
없다 — network/router와 동일하게 존재 기간(`durations["total"]["seconds"]`)
하나만 쓴다. volume에는 charge_type 구분(on-demand/reserved) 자체가 없어
network/router와 동일하게 metering detail에 `"Reserved"`를 고정값으로 싣는다.

**detail 필드**: `volume_type_id`/`volume_type_name`/`size_gib`/`max_iops`/
`burst_iops`는 0 치환 없이 usage에 있는 그대로 반영한다(legacy가 DB 컬럼을
그대로 싣는 원칙, `base.py` docstring 참고) — legacy의
`billing_max_IOPS`/`billing_burst_IOPS`처럼 metering-api에 없는 필드는
만들지 않는다.
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import (
    EncodedMidResourceTransformer,
    ResourcePayload,
    _to_kst,
)


def _zero_if_none(value: int | None) -> int:
    return value or 0


class VolumeTransformer(EncodedMidResourceTransformer):
    resource_type = "volume"
    mid_fields = (
        ("size", "size_gib"),
        ("mIOPS", "max_iops"),
        ("bIOPS", "burst_iops"),
    )

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        resource_id = usage["resource_id"]
        mid = self.build_mid(
            {
                **usage,
                "max_iops": _zero_if_none(usage.get("max_iops")),
                "burst_iops": _zero_if_none(usage.get("burst_iops")),
            }
        )

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
                        "volume_type_id": usage.get("volume_type_id"),
                        "volume_type_name": usage.get("volume_type_name"),
                        "size_gib": usage.get("size_gib"),
                        "max_iops": usage.get("max_iops"),
                        "burst_iops": usage.get("burst_iops"),
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
                "nActiveSec": int(usage["durations"]["total"]["seconds"]),
                "nSuspendSec": 0,
                "arDetailInfo": {
                    "detail": {
                        "period_start": usage["min_started_at"],
                        "period_end": usage["max_ended_at"],
                        "created_at": usage["created_at"],
                        "tenant_id": usage["tenant_id"],
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage["durations"]["total"]["seconds"],
                        "resource_type": self.resource_type,
                        "volume_type_id": usage.get("volume_type_id"),
                        "volume_type_name": usage.get("volume_type_name"),
                        "size_gib": usage.get("size_gib"),
                        "max_iops": usage.get("max_iops"),
                        "burst_iops": usage.get("burst_iops"),
                        "charge_type": "Reserved",
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid, resource_item=resource_item, metering_item=metering_item
        )

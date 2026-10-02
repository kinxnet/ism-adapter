"""share(NAS) usage -> THAAD push payload 변환.

mID 포맷은 legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_share`
재현: `{resource_id}-size::{size}`. `EncodedMidResourceTransformer`
(transformers/base.py)를 상속해 `mid_fields`로 조합 순서만 선언한다.

**resource_type 이중 표기**: 이 클래스의 `resource_type` 속성(`"share"`)은
metering-api 쪽 자원 키 이름이다(다른 transformer들과 동일하게 TRANSFORMERS
dict의 키, 로깅 등에 쓰임). 반면 THAAD로 나가는 `arDetailInfo.detail.resource_type`
값은 legacy `run_share`/`ism/metering.py::run_share`가 실제로 보내던 값인
`"nas"`로 고정한다 — `SimpleResourceTransformer`(network/router)가
`self.resource_type`을 그대로 detail에 쓰는 것과 달리, 이 자원은 두 이름이
다르므로 detail에는 하드코딩된 `"nas"`를 쓴다.

**size 절삭**: metering-api `ShareMeteringDTO.size_gib`는 usage dict에서
`size_gib` 키로 온다(라벨은 legacy 그대로 `size`). legacy `run_share`는
`int(float(meter.size))`로 소수점을 내림 처리하므로 동일하게 처리한다
(`_normalize_size`). `size_gib`가 `None`인 경우는 legacy에 대응 사례가 없다
(legacy는 `MeteringDayShare.size`가 항상 존재하는 질의 결과만 순회해
`None`을 만나면 `int(float(None))`에서 예외가 나 해당 자원 처리가 중단된다) —
이 adapter는 그 자리에서 전체 배치를 멈추지 않도록 0으로 폴백하고 경고를
남긴다.
"""

from loguru import logger

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import (
    EncodedMidResourceTransformer,
    ResourcePayload,
    _to_kst,
)

_THAAD_RESOURCE_TYPE = "nas"


def _normalize_size(size_gib: float | int | None) -> int:
    """`usage["size_gib"]`를 legacy mID 포맷(정수, 내림 처리)으로 정규화한다."""
    if size_gib is None:
        logger.warning("share size_gib가 없어 0으로 폴백합니다")
        return 0
    return int(float(size_gib))


class ShareTransformer(EncodedMidResourceTransformer):
    resource_type = "share"
    mid_fields = (("size", "size"),)

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        resource_id = usage["resource_id"]
        size = _normalize_size(usage.get("size_gib"))
        mid = self.build_mid({**usage, "size": size})

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
                        "resource_type": _THAAD_RESOURCE_TYPE,
                        "size": size,
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
                        "resource_type": _THAAD_RESOURCE_TYPE,
                        "charge_type": "Reserved",
                        "size": size,
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid,
            resource_item=resource_item,
            metering_item=metering_item,
        )

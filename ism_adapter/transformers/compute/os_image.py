"""os_image usage(dict) -> ISM(THAAD) push payload 변환.

os_image는 "이미지 사용량"이 아니라 **Windows 라이선스 과금**이다 — legacy
`ixcloud_service/common/ixcdaemon/ism/resource.py::run_os_image`,
`ism/metering.py::run_os_image`가 애초에 `os_type IN ('windows', 'windosw',
'winddows', 'window')`로 조회 자체를 필터링해 Linux 등은 대상에서 제외한다
(2026-10-02 dev→stage 실전 검증에서 linux os_image push가 전부 THAAD
`Product not found`로 실패해 발견). metering-api는 이 필터를 걸지 않고 모든
OS 이미지를 노출하므로, 필터링은 여기(`is_excluded`)에서 한다 — "어떤 자원을
과금 대상으로 볼지"는 billing/policy 영역이고 metering-api가 이미 주는
`base_image_name`/`os_type`만으로 판단 가능해 metering-api를 고칠 이유가
없다.

os_image는 instance_history를 (resource_id, base_image_ref) 기준으로 재집계한
인스턴스 파생 자원이라, metering-api usage에는 별도 image_id 필드가 없다 —
`usage["resource_id"]`가 곧 instance_id다(`OsImageMeteringDTO` 참고).

legacy가 실제로 쓰던 mID 포맷(`"os_image-instance_id::{instance_id}"`, 이미지
참조는 인코딩하지 않음)을 그대로 재현한다. 리빌드 등으로 인스턴스의 이미지가
바뀌어도 동일 mID로 push되어 이전 기간을 덮어쓰는 것 역시 legacy와 동일한
동작이다(의도적 재현이지 버그가 아니다).

현재는 legacy와 동일하게 instance_id만 인코딩한다. THAAD는 mID를 opaque
문자열로 취급해 포맷 검증을 하지 않으므로, 추후 base_image_ref를 추가
인코딩해 이미지별 기간을 분리 보존하는 개선이 가능함(이번 스코프 아님).

resource/metering item 구조 자체는 `base.py::SimpleResourceTransformer`
(network/router)와 동일하다 — mID 조립 방식만 달라 새 베이스 클래스를 두지
않고 `ResourcePayload`/`_to_kst` 헬퍼만 재사용해 여기서 직접 조합한다.

`arDetailInfo.detail`에는 `base_image_ref`/`base_image_name`/`os_type`뿐
아니라 THAAD 상품 매칭에 실제로 쓰이는 `windows_type`/`server_type`/
`server_version`/`sql_type`/`sql_version`도 싣는다 — legacy는 이 값을 자체
가격표(`PriceUsage.category_name`, base_image_ref로 조회)에서 우선 가져오고
실패하면 `base_image_name`으로 폴백했는데, 그 가격표가 이 시스템에는 없으므로
`base_image_name`만으로 `_detect_os_db.detect_os_db()`를 돌린다(legacy의
폴백 경로와 동일 입력).
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import ResourcePayload, _to_kst
from ism_adapter.transformers.compute._detect_os_db import detect_os_db

_RESOURCE_TYPE = "os_image"
_MID_PREFIX = "os_image-instance_id::"

_WINDOWS_OS_TYPES = frozenset({"windows", "windosw", "winddows", "window"})
# 자체 라이선스 보유로 무과금 대상(legacy OSIMAGE_FREE_TENANTS,
# ixcloud_service/common/ixcdaemon/base.py:630 — 증권통/stocktong_R1_Zone).
_FREE_TENANTS = frozenset({"d836600491664000b23268ed0fb85655"})


def _derive_windows_attributes(base_image_name: str | None) -> dict:
    """legacy `run_os_image`의 windows_type/server_type/sql_type 파생을 재현.

    `base_image_name`이 없을 때의 legacy 기본값(`windows_type="server"`,
    `server_type="standard"`)과, 있지만 윈도우 패턴이 안 잡힐 때
    `server_type`이 None으로 남는 것(의도적으로 다르게 처리됨) 둘 다
    그대로 따른다.
    """
    if not base_image_name:
        return {
            "windows_type": "server",
            "server_type": "standard",
            "server_version": None,
            "sql_type": None,
            "sql_version": None,
        }

    windows_type = "desktop" if base_image_name.lower() == "windows10" else "server"
    server_type = None
    server_version = None
    sql_type = None
    sql_version = None

    detected = detect_os_db(base_image_name)
    if detected.windows is not None:
        server_type = detected.windows.edition
        server_version = detected.windows.version
    if detected.sql is not None:
        sql_type = detected.sql.edition
        sql_version = detected.sql.version

    return {
        "windows_type": windows_type,
        "server_type": server_type,
        "server_version": server_version,
        "sql_type": sql_type,
        "sql_version": sql_version,
    }


class OsImageTransformer:
    resource_type = _RESOURCE_TYPE

    def is_excluded(self, usage: dict) -> bool:
        os_type = (usage.get("os_type") or "").lower()
        if os_type not in _WINDOWS_OS_TYPES:
            return True

        base_image_name = usage.get("base_image_name")
        if base_image_name and base_image_name.startswith("custom"):
            return True

        return usage.get("tenant_id") in _FREE_TENANTS

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        instance_id = usage["resource_id"]
        mid = f"{_MID_PREFIX}{instance_id}"
        windows_attributes = _derive_windows_attributes(usage.get("base_image_name"))

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
                        "resource_id": instance_id,
                        "display_name": usage.get("display_name"),
                        "resource_type": _RESOURCE_TYPE,
                        "base_image_ref": usage.get("base_image_ref"),
                        "base_image_name": usage.get("base_image_name"),
                        "os_type": usage.get("os_type"),
                        **windows_attributes,
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
                        "resource_id": instance_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage["durations"]["total"]["seconds"],
                        "resource_type": _RESOURCE_TYPE,
                        "charge_type": "Reserved",
                        "base_image_ref": usage.get("base_image_ref"),
                        "base_image_name": usage.get("base_image_name"),
                        "os_type": usage.get("os_type"),
                        **windows_attributes,
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid, resource_item=resource_item, metering_item=metering_item
        )

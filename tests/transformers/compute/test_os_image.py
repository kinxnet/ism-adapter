"""os_image mID 조립 규칙 고정 — legacy `ism/resource.py::run_os_image` /
`ism/metering.py::run_os_image`가 쓰던 `"os_image-instance_id::{instance_id}"`
포맷과 정확히 일치해야 한다(issue #8 acceptance criteria)."""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.compute.os_image import OsImageTransformer

_INSTANCE_ID = "b6b6b3e2-1c1a-4e9a-9c1a-1234567890ab"

_PROJECT = ProjectInfo(
    project_id="project-uuid-1",
    tenant_id="tenant-1",
    provider_id="provider-1",
)

_USAGE = {
    "resource_id": _INSTANCE_ID,
    "tenant_id": "tenant-1",
    "display_name": "web-server-01",
    "created_at": "2026-08-01T00:00:00+00:00",
    "deleted_at": None,
    "min_started_at": "2026-08-01T00:00:00+00:00",
    "max_ended_at": "2026-08-31T00:00:00+00:00",
    "durations": {"total": {"seconds": 2592000}},
    "base_image_ref": "image-ref-uuid",
    "base_image_name": "windows2019std",
    "os_type": "windows",
}


def test_mid_matches_legacy_format():
    payload = OsImageTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.mid == f"os_image-instance_id::{_INSTANCE_ID}"


def test_mid_does_not_encode_image_reference():
    """이미지 참조(base_image_ref)는 mID에 인코딩하지 않는다 — legacy 그대로
    instance_id만 쓴다(리빌드로 이미지가 바뀌어도 mID는 불변)."""
    payload = OsImageTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert "image-ref-uuid" not in payload.mid


def test_resource_item_uses_composed_mid():
    payload = OsImageTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.resource_item["resource"]["mID"] == payload.mid
    assert (
        payload.resource_item["resource"]["arDetailInfo"]["detail"]["resource_type"]
        == "os_image"
    )
    assert (
        payload.resource_item["resource"]["arDetailInfo"]["detail"]["resource_id"]
        == _INSTANCE_ID
    )


def test_metering_item_sresourceid_matches_mid():
    """metering.sResourceId는 resource의 mID와 동일값이어야 THAAD 쪽에서
    매칭된다(legacy `ism/metering.py::run_os_image`와 동일)."""
    payload = OsImageTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.metering_item["metering"]["sResourceId"] == payload.mid
    assert payload.metering_item["metering"]["nActiveSec"] == 2592000
    assert payload.metering_item["metering"]["nSuspendSec"] == 0


def test_rebuild_with_different_image_reuses_same_mid():
    """리빌드로 base_image_ref가 바뀌어도 instance_id가 같으면 동일 mID —
    legacy와 동일하게 이전 기간이 새 push로 덮어써지는 의도된 동작."""
    rebuilt_usage = {**_USAGE, "base_image_ref": "another-image-ref-uuid"}

    original = OsImageTransformer().to_resource_payload(_USAGE, _PROJECT)
    rebuilt = OsImageTransformer().to_resource_payload(rebuilt_usage, _PROJECT)

    assert original.mid == rebuilt.mid

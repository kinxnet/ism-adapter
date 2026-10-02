"""VolumeTransformer: mID 조립(0 치환 포함) + payload 구성 검증.

legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_volume`의
`max_IOPS or 0` / `burst_IOPS or 0` 치환을 그대로 재현하는지가 핵심이다 —
치환 없이 `None`이 mID 문자열에 그대로 들어가면 같은 볼륨이라도 IOPS 제한이
없는 시점과 있는 시점의 mID가 달라져 자원이 갈라진다.
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.storage.volume import VolumeTransformer


class TestVolumeTransformerToResourcePayload:
    def _usage(self, **overrides) -> dict:
        usage = {
            "resource_id": "volume-uuid-1",
            "tenant_id": "tenant-1",
            "display_name": "vol-01",
            "created_at": "2025-01-01T00:00:00+00:00",
            "deleted_at": None,
            "min_started_at": "2025-01-01T00:00:00+00:00",
            "max_ended_at": "2025-01-31T00:00:00+00:00",
            "volume_type_id": "type-ssd",
            "volume_type_name": "SSD",
            "size_gib": 100,
            "max_iops": 3000,
            "burst_iops": 6000,
            "durations": {"total": {"seconds": 2592000}},
        }
        usage.update(overrides)
        return usage

    def _project(self) -> ProjectInfo:
        return ProjectInfo(
            project_id="project-1", tenant_id="tenant-1", provider_id="provider-1"
        )

    def test_mid_follows_legacy_format(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(), self._project()
        )

        assert payload.mid == "volume-uuid-1-size::100-mIOPS::3000-bIOPS::6000"
        assert payload.resource_item["resource"]["mID"] == payload.mid

    def test_mid_substitutes_zero_when_iops_fields_are_none(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(max_iops=None, burst_iops=None), self._project()
        )

        assert payload.mid == "volume-uuid-1-size::100-mIOPS::0-bIOPS::0"

    def test_metering_sresourceid_matches_resource_mid(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(), self._project()
        )

        assert payload.metering_item["metering"]["sResourceId"] == payload.mid

    def test_active_seconds_come_from_total_duration(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(durations={"total": {"seconds": 123}}), self._project()
        )

        metering = payload.metering_item["metering"]
        assert metering["nActiveSec"] == 123
        assert metering["nSuspendSec"] == 0

    def test_detail_carries_raw_iops_values_not_zero_substituted(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(max_iops=None, burst_iops=None), self._project()
        )

        resource_detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        metering_detail = payload.metering_item["metering"]["arDetailInfo"]["detail"]
        assert resource_detail["max_iops"] is None
        assert resource_detail["burst_iops"] is None
        assert metering_detail["max_iops"] is None
        assert metering_detail["burst_iops"] is None

    def test_detail_carries_volume_type_and_size_fields(self):
        payload = VolumeTransformer().to_resource_payload(
            self._usage(), self._project()
        )

        resource_detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        assert resource_detail["volume_type_id"] == "type-ssd"
        assert resource_detail["volume_type_name"] == "SSD"
        assert resource_detail["size_gib"] == 100

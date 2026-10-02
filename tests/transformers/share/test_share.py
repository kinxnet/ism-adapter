"""ShareTransformer: size 절삭 + mID/payload 조립 + resource_type 이중 표기 검증.

legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_share`의
`int(float(meter.size))` 절삭을 재현하는지, 그리고 THAAD로 나가는
`arDetailInfo.detail.resource_type`이 metering-api 쪽 키("share")가 아니라
legacy 실측값("nas")으로 고정되는지가 핵심이다.
"""

import logging

import pytest
from loguru import logger

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.share.share import ShareTransformer, _normalize_size


class _PropagateHandler(logging.Handler):
    """loguru -> 표준 logging 브릿지. caplog은 표준 logging 핸들러만 보므로
    loguru가 남긴 경고를 caplog으로 넘기려면 이 핸들러를 통해 전파해야 한다."""

    def emit(self, record):
        logging.getLogger(record.name).handle(record)


@pytest.fixture(autouse=True)
def _propagate_loguru_to_caplog():
    handler_id = logger.add(_PropagateHandler(), format="{message}")
    yield
    logger.remove(handler_id)


class TestNormalizeSize:
    @pytest.mark.parametrize(
        ("size_gib", "expected"),
        [
            (100, 100),
            (100.0, 100),
            (100.9, 100),
            (0, 0),
        ],
    )
    def test_truncates_to_int(self, size_gib, expected):
        assert _normalize_size(size_gib) == expected

    def test_none_falls_back_to_zero_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _normalize_size(None)

        assert result == 0
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"


class TestShareTransformerToResourcePayload:
    def _usage(self, **overrides) -> dict:
        usage = {
            "resource_id": "share-uuid-1",
            "tenant_id": "tenant-1",
            "display_name": "nas-01",
            "created_at": "2025-01-01T00:00:00+00:00",
            "deleted_at": None,
            "min_started_at": "2025-01-01T00:00:00+00:00",
            "max_ended_at": "2025-01-31T00:00:00+00:00",
            "size_gib": 100,
            "durations": {"total": {"seconds": 2592000}},
        }
        usage.update(overrides)
        return usage

    def _project(self) -> ProjectInfo:
        return ProjectInfo(
            project_id="project-1", tenant_id="tenant-1", provider_id="provider-1"
        )

    def test_mid_follows_legacy_format_with_truncated_size(self):
        payload = ShareTransformer().to_resource_payload(
            self._usage(size_gib=100.9), self._project()
        )

        assert payload.mid == "share-uuid-1-size::100"
        assert payload.resource_item["resource"]["mID"] == payload.mid

    def test_metering_sresourceid_matches_resource_mid(self):
        payload = ShareTransformer().to_resource_payload(self._usage(), self._project())

        assert payload.metering_item["metering"]["sResourceId"] == payload.mid

    def test_active_seconds_come_from_total_duration(self):
        payload = ShareTransformer().to_resource_payload(
            self._usage(durations={"total": {"seconds": 42}}), self._project()
        )

        metering = payload.metering_item["metering"]
        assert metering["nActiveSec"] == 42
        assert metering["nSuspendSec"] == 0

    def test_none_size_gib_falls_back_to_zero_in_mid(self):
        payload = ShareTransformer().to_resource_payload(
            self._usage(size_gib=None), self._project()
        )

        assert payload.mid == "share-uuid-1-size::0"

    def test_detail_resource_type_is_hardcoded_to_nas_not_the_class_attribute(self):
        payload = ShareTransformer().to_resource_payload(self._usage(), self._project())

        resource_detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        metering_detail = payload.metering_item["metering"]["arDetailInfo"]["detail"]

        assert ShareTransformer.resource_type == "share"
        assert resource_detail["resource_type"] == "nas"
        assert metering_detail["resource_type"] == "nas"

    def test_detail_carries_truncated_size_not_raw_size_gib(self):
        payload = ShareTransformer().to_resource_payload(
            self._usage(size_gib=100.9), self._project()
        )

        resource_detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        metering_detail = payload.metering_item["metering"]["arDetailInfo"]["detail"]
        assert resource_detail["size"] == 100
        assert metering_detail["size"] == 100

    def test_metering_charge_type_is_reserved(self):
        payload = ShareTransformer().to_resource_payload(self._usage(), self._project())

        metering_detail = payload.metering_item["metering"]["arDetailInfo"]["detail"]
        assert metering_detail["charge_type"] == "Reserved"

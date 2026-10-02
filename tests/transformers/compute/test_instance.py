"""InstanceTransformer: charge_type 정규화 + mID/payload 조립 검증.

legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_instance`의
`meter.charge_type.title()` 실측 포맷(`Reserved`/`On_Demand`, 대문자 D)을
그대로 재현하는지가 핵심이다 — `On_demand`(소문자 d)로 통일하면 기존 THAAD
데이터와 다른 mID가 생겨 같은 인스턴스가 두 자원으로 갈라진다.
"""

import logging

import pytest
from loguru import logger

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.compute.instance import (
    InstanceTransformer,
    _normalize_charge_type,
)


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


class TestNormalizeChargeType:
    @pytest.mark.parametrize(
        "price_type",
        ["Reserved", "reserved", "RESERVED", "  reserved  "],
    )
    def test_matches_reserved_case_insensitively(self, price_type, caplog):
        with caplog.at_level(logging.WARNING):
            assert _normalize_charge_type(price_type) == "Reserved"
        assert caplog.records == []

    @pytest.mark.parametrize(
        "price_type",
        ["On_Demand", "on_demand", "ON_DEMAND", "  On_demand  "],
    )
    def test_matches_on_demand_case_insensitively(self, price_type, caplog):
        with caplog.at_level(logging.WARNING):
            assert _normalize_charge_type(price_type) == "On_Demand"
        assert caplog.records == []

    def test_none_falls_back_to_reserved_without_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert _normalize_charge_type(None) == "Reserved"
        assert caplog.records == []

    def test_unrecognized_value_falls_back_to_reserved_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _normalize_charge_type("flat_rate")

        assert result == "Reserved"
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert "flat_rate" in caplog.text


class TestInstanceTransformerToResourcePayload:
    def _usage(self, **overrides) -> dict:
        usage = {
            "resource_id": "instance-uuid-1",
            "tenant_id": "tenant-1",
            "display_name": "vm-01",
            "created_at": "2025-01-01T00:00:00+00:00",
            "deleted_at": None,
            "min_started_at": "2025-01-01T00:00:00+00:00",
            "max_ended_at": "2025-01-31T00:00:00+00:00",
            "instance_flavor_id": "m1.large",
            "price_type": "On_demand",
            "active_duration_sec": 2592000,
            "suspend_duration_sec": 120,
            "pause_duration_sec": 0,
            "power_off_duration_sec": 0,
        }
        usage.update(overrides)
        return usage

    def _project(self) -> ProjectInfo:
        return ProjectInfo(
            project_id="project-1", tenant_id="tenant-1", provider_id="provider-1"
        )

    def test_mid_follows_legacy_format_with_normalized_charge_type(self):
        payload = InstanceTransformer().to_resource_payload(
            self._usage(), self._project()
        )

        assert payload.mid == "instance-uuid-1-flavor::m1.large-charge_type::On_Demand"
        assert payload.resource_item["resource"]["mID"] == payload.mid

    def test_metering_sresourceid_matches_resource_mid(self):
        payload = InstanceTransformer().to_resource_payload(
            self._usage(), self._project()
        )

        assert payload.metering_item["metering"]["sResourceId"] == payload.mid

    def test_active_and_suspend_seconds_come_from_dedicated_duration_fields(self):
        payload = InstanceTransformer().to_resource_payload(
            self._usage(active_duration_sec=100, suspend_duration_sec=5),
            self._project(),
        )

        metering = payload.metering_item["metering"]
        assert metering["nActiveSec"] == 100
        assert metering["nSuspendSec"] == 5

    def test_null_price_type_falls_back_to_reserved_in_mid(self):
        payload = InstanceTransformer().to_resource_payload(
            self._usage(price_type=None), self._project()
        )

        assert payload.mid == "instance-uuid-1-flavor::m1.large-charge_type::Reserved"

    def test_detail_carries_normalized_charge_type_not_raw_price_type(self):
        payload = InstanceTransformer().to_resource_payload(
            self._usage(price_type="on_demand"), self._project()
        )

        resource_detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        metering_detail = payload.metering_item["metering"]["arDetailInfo"]["detail"]
        assert resource_detail["charge_type"] == "On_Demand"
        assert metering_detail["charge_type"] == "On_Demand"

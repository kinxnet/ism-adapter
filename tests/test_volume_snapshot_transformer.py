"""Tests for VolumeSnapshotTransformer."""

import pytest

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.storage.volume_snapshot import VolumeSnapshotTransformer


@pytest.fixture
def transformer():
    """Create a VolumeSnapshotTransformer instance."""
    return VolumeSnapshotTransformer()


@pytest.fixture
def project_info():
    """Create a sample ProjectInfo instance."""
    return ProjectInfo(
        project_id="proj-123",
        tenant_id="tenant-456",
        provider_id="provider-789",
    )


@pytest.fixture
def usage_data():
    """Create a sample usage data dictionary."""
    return {
        "resource_id": "vs-12345",
        "tenant_id": "tenant-456",
        "display_name": "snapshot-001",
        "created_at": "2026-09-15T10:30:00",
        "deleted_at": None,
        "min_started_at": "2026-09-15T10:30:00",
        "max_ended_at": "2026-09-29T10:30:00",
        "durations": {
            "total": {"seconds": 1209600},
        },
    }


class TestVolumeSnapshotTransformer:
    """Test suite for VolumeSnapshotTransformer."""

    def test_resource_type(self, transformer):
        """Test that resource_type is set correctly."""
        assert transformer.resource_type == "volume_snapshot"

    def test_to_resource_payload_returns_correct_mid(
        self, transformer, usage_data, project_info
    ):
        """Test that to_resource_payload returns correct mID."""
        payload = transformer.to_resource_payload(usage_data, project_info)
        assert payload.mid == "vs-12345"

    def test_to_resource_payload_structure(self, transformer, usage_data, project_info):
        """Test that payload has correct top-level structure."""
        payload = transformer.to_resource_payload(usage_data, project_info)

        # Check that payload is a ResourcePayload with expected attributes
        assert hasattr(payload, "mid")
        assert hasattr(payload, "resource_item")
        assert hasattr(payload, "metering_item")

    def test_resource_item_structure(self, transformer, usage_data, project_info):
        """Test that resource_item has correct THAAD push format."""
        payload = transformer.to_resource_payload(usage_data, project_info)
        resource_item = payload.resource_item

        # Check service_type
        assert resource_item["service_type"] == "cloud"

        # Check contract_service_map
        assert resource_item["contract_service_map"]["sService"] == "cloud"
        assert resource_item["contract_service_map"]["sType"] == "Contract"
        assert (
            resource_item["contract_service_map"]["sServiceKey"]
            == project_info.project_id
        )

        # Check resource field
        assert "resource" in resource_item
        resource = resource_item["resource"]
        assert resource["mID"] == "vs-12345"
        assert resource["sServiceType"] == "I"
        # dtStart/dtEnd are converted to KST (UTC+9)
        assert resource["dtStart"] == "2026-09-15 19:30:00"
        assert resource["dtEnd"] is None

        # Check arDetailInfo
        detail = resource["arDetailInfo"]["detail"]
        assert detail["resource_id"] == "vs-12345"
        assert detail["tenant_id"] == "tenant-456"
        assert detail["display_name"] == "snapshot-001"
        assert detail["resource_type"] == "volume_snapshot"
        assert detail["created_at"] == "2026-09-15T10:30:00"
        assert detail["deleted_at"] is None

    def test_metering_item_structure(self, transformer, usage_data, project_info):
        """Test that metering_item has correct THAAD push format."""
        payload = transformer.to_resource_payload(usage_data, project_info)
        metering_item = payload.metering_item

        # Check service_type
        assert metering_item["service_type"] == "cloud"

        # Check metering field
        metering = metering_item["metering"]
        assert metering["sResourceId"] == "vs-12345"
        assert metering["sProviderId"] == "provider-789"
        assert metering["sTenantId"] == "tenant-456"
        # dtPeriodStart/dtPeriodEnd are converted to KST (UTC+9)
        assert metering["dtPeriodStart"] == "2026-09-15 19:30:00"
        assert metering["dtPeriodEnd"] == "2026-09-29 19:30:00"
        assert metering["nActiveSec"] == 1209600
        assert metering["nSuspendSec"] == 0

        # Check arDetailInfo
        detail = metering["arDetailInfo"]["detail"]
        assert detail["resource_id"] == "vs-12345"
        assert detail["tenant_id"] == "tenant-456"
        assert detail["display_name"] == "snapshot-001"
        assert detail["resource_type"] == "volume_snapshot"
        assert detail["charge_type"] == "Reserved"
        assert detail["duration_sec"] == 1209600

    def test_deleted_snapshot_with_deleted_at(self, transformer, project_info):
        """Test payload generation for deleted snapshot."""
        usage_data = {
            "resource_id": "vs-67890",
            "tenant_id": "tenant-456",
            "display_name": "snapshot-deleted",
            "created_at": "2026-09-15T10:30:00",
            "deleted_at": "2026-09-28T15:45:00",
            "min_started_at": "2026-09-15T10:30:00",
            "max_ended_at": "2026-09-28T15:45:00",
            "durations": {
                "total": {"seconds": 1123500},
            },
        }

        payload = transformer.to_resource_payload(usage_data, project_info)
        resource = payload.resource_item["resource"]

        # Check that dtEnd is populated (converted to KST, UTC+9)
        assert resource["dtEnd"] == "2026-09-29 00:45:00"
        assert resource["arDetailInfo"]["detail"]["deleted_at"] == "2026-09-28T15:45:00"

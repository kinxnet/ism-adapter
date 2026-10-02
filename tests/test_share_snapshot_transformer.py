"""Unit tests for ShareSnapshotTransformer."""

import pytest

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.share.share_snapshot import ShareSnapshotTransformer


class TestShareSnapshotTransformer:
    """Tests for ShareSnapshotTransformer."""

    @pytest.fixture
    def transformer(self) -> ShareSnapshotTransformer:
        """Create a transformer instance."""
        return ShareSnapshotTransformer()

    def test_resource_type(self, transformer: ShareSnapshotTransformer) -> None:
        """Test that resource_type is set correctly."""
        assert transformer.resource_type == "share_snapshot"

    def test_to_resource_payload_structure(
        self,
        transformer: ShareSnapshotTransformer,
        sample_project: ProjectInfo,
        sample_share_snapshot_usage: dict,
    ) -> None:
        """Test that to_resource_payload returns correct structure."""
        payload = transformer.to_resource_payload(
            sample_share_snapshot_usage, sample_project
        )

        # Check ResourcePayload structure
        assert payload.mid == "share-snapshot-789"
        assert isinstance(payload.resource_item, dict)
        assert isinstance(payload.metering_item, dict)

    def test_resource_item_structure(
        self,
        transformer: ShareSnapshotTransformer,
        sample_project: ProjectInfo,
        sample_share_snapshot_usage: dict,
    ) -> None:
        """Test resource_item has correct fields and values."""
        payload = transformer.to_resource_payload(
            sample_share_snapshot_usage, sample_project
        )
        resource_item = payload.resource_item

        # Top-level fields
        assert resource_item["service_type"] == "cloud"
        assert "contract_service_map" in resource_item
        assert "resource" in resource_item

        # contract_service_map
        csm = resource_item["contract_service_map"]
        assert csm["sService"] == "cloud"
        assert csm["sType"] == "Contract"
        assert csm["sServiceKey"] == "project-123"

        # resource
        resource = resource_item["resource"]
        assert resource["mID"] == "share-snapshot-789"
        assert resource["sServiceType"] == "I"
        # dtStart is converted to KST (UTC+9), so 00:00:00 UTC becomes 09:00:00 KST
        assert resource["dtStart"] == "2026-01-01 09:00:00"
        assert resource["dtEnd"] is None  # Not deleted
        assert "arDetailInfo" in resource

        # arDetailInfo.detail
        detail = resource["arDetailInfo"]["detail"]
        assert detail["created_at"] == "2026-01-01T00:00:00+00:00"
        assert detail["deleted_at"] is None
        assert detail["tenant_id"] == "tenant-001"
        assert detail["resource_id"] == "share-snapshot-789"
        assert detail["display_name"] == "snapshot-1"
        # THAAD에 등록된 상품(nProductSeq=352)의 attribute.resource_type과
        # 일치해야 하는 값 — 내부 키 이름(share_snapshot)과 다르다.
        assert detail["resource_type"] == "nas_snapshot"

    def test_metering_item_structure(
        self,
        transformer: ShareSnapshotTransformer,
        sample_project: ProjectInfo,
        sample_share_snapshot_usage: dict,
    ) -> None:
        """Test metering_item has correct fields and values."""
        payload = transformer.to_resource_payload(
            sample_share_snapshot_usage, sample_project
        )
        metering_item = payload.metering_item

        # Top-level fields
        assert metering_item["service_type"] == "cloud"
        assert "metering" in metering_item

        # metering
        metering = metering_item["metering"]
        assert metering["sResourceId"] == "share-snapshot-789"
        assert metering["sProviderId"] == "provider-456"
        assert metering["sTenantId"] == "tenant-001"
        # dtPeriodStart and dtPeriodEnd are converted to KST (UTC+9)
        assert metering["dtPeriodStart"] == "2026-01-01 09:00:00"
        assert metering["dtPeriodEnd"] == "2026-01-02 09:00:00"
        assert metering["nActiveSec"] == 86400
        assert metering["nSuspendSec"] == 0
        assert "arDetailInfo" in metering

        # arDetailInfo.detail
        detail = metering["arDetailInfo"]["detail"]
        assert detail["period_start"] == "2026-01-01T00:00:00+00:00"
        assert detail["period_end"] == "2026-01-02T00:00:00+00:00"
        assert detail["created_at"] == "2026-01-01T00:00:00+00:00"
        assert detail["tenant_id"] == "tenant-001"
        assert detail["resource_id"] == "share-snapshot-789"
        assert detail["display_name"] == "snapshot-1"
        assert detail["duration_sec"] == 86400
        assert detail["resource_type"] == "nas_snapshot"
        assert detail["charge_type"] == "Reserved"

    def test_deleted_resource(
        self,
        transformer: ShareSnapshotTransformer,
        sample_project: ProjectInfo,
        sample_share_snapshot_usage_deleted: dict,
    ) -> None:
        """Test payload for a deleted resource."""
        payload = transformer.to_resource_payload(
            sample_share_snapshot_usage_deleted, sample_project
        )

        # Check dtEnd is set for deleted resource (converted to KST)
        resource = payload.resource_item["resource"]
        # 12:30:00 UTC becomes 21:30:00 KST (UTC+9)
        assert resource["dtEnd"] == "2026-01-15 21:30:00"

        # Check metering detail includes deleted_at
        detail = payload.resource_item["resource"]["arDetailInfo"]["detail"]
        assert detail["deleted_at"] == "2026-01-15T12:30:00+00:00"

    def test_mid_equals_resource_id(
        self,
        transformer: ShareSnapshotTransformer,
        sample_project: ProjectInfo,
        sample_share_snapshot_usage: dict,
    ) -> None:
        """Test that mID (mid) equals resource_id unchanged (Simple pattern)."""
        payload = transformer.to_resource_payload(
            sample_share_snapshot_usage, sample_project
        )

        # For SimpleResourceTransformer, mID should be resource_id as-is
        assert payload.mid == sample_share_snapshot_usage["resource_id"]
        assert (
            payload.resource_item["resource"]["mID"]
            == sample_share_snapshot_usage["resource_id"]
        )
        assert (
            payload.metering_item["metering"]["sResourceId"]
            == sample_share_snapshot_usage["resource_id"]
        )

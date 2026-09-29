"""Shared test fixtures."""

import pytest

from ism_adapter.repositories import ProjectInfo


@pytest.fixture
def sample_project() -> ProjectInfo:
    """Sample project for testing."""
    return ProjectInfo(
        project_id="project-123",
        provider_id="provider-456",
    )


@pytest.fixture
def sample_share_snapshot_usage() -> dict:
    """Sample share_snapshot usage data from metering-api."""
    return {
        "resource_id": "share-snapshot-789",
        "tenant_id": "tenant-001",
        "display_name": "snapshot-1",
        "created_at": "2026-01-01T00:00:00+00:00",
        "deleted_at": None,
        "min_started_at": "2026-01-01T00:00:00+00:00",
        "max_ended_at": "2026-01-02T00:00:00+00:00",
        "durations": {
            "total": {
                "seconds": 86400,
            }
        },
    }


@pytest.fixture
def sample_share_snapshot_usage_deleted() -> dict:
    """Sample deleted share_snapshot usage data."""
    return {
        "resource_id": "share-snapshot-deleted",
        "tenant_id": "tenant-001",
        "display_name": "snapshot-deleted",
        "created_at": "2026-01-01T00:00:00+00:00",
        "deleted_at": "2026-01-15T12:30:00+00:00",
        "min_started_at": "2026-01-01T00:00:00+00:00",
        "max_ended_at": "2026-01-15T12:30:00+00:00",
        "durations": {
            "total": {
                "seconds": 1209600,  # 14 days
            }
        },
    }

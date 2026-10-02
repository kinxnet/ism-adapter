"""push_service.py의 is_excluded 훅 동작을 고정하는 테스트.

전체 파이프라인(metering_client/project_repo/ism_client)은 이 테스트의
관심사가 아니라 더미로 대체한다 — 여기서 보는 건 "transformer가
is_excluded를 선언하면 push_service가 실제로 그걸 호출해서 걸러내는가"뿐이다.
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.services.push_service import push_resource_type
from ism_adapter.transformers import TRANSFORMERS
from ism_adapter.transformers.base import ResourcePayload


class _StubMeteringClient:
    def __init__(self, usages):
        self._usages = usages

    def list_metering(self, resource_type, period_start, period_end):
        return self._usages


class _StubProjectRepo:
    def __init__(self, project):
        self._project = project

    def get_by_tenant_ids(self, tenant_ids):
        return dict.fromkeys(tenant_ids, self._project)


class _StubIsmClient:
    def put_resources(self, items):
        return [{} for _ in items]

    def put_meterings(self, items):
        return [{} for _ in items]


class _AlwaysExcludedTransformer:
    """is_excluded가 항상 True인 가짜 transformer — to_resource_payload가
    호출되면 안 된다는 것까지 같이 검증한다."""

    resource_type = "fake_excluded"

    def is_excluded(self, usage):
        return True

    def to_resource_payload(self, usage, project):
        raise AssertionError(
            "excluded된 usage는 to_resource_payload가 호출되면 안 된다"
        )


def test_is_excluded_hook_skips_usage_and_counts_it(monkeypatch):
    monkeypatch.setitem(TRANSFORMERS, "fake_excluded", _AlwaysExcludedTransformer())

    usages = [{"resource_id": "r1", "tenant_id": "t1"}]
    project = ProjectInfo(project_id="p1", tenant_id="t1", provider_id="prov1")

    result = push_resource_type(
        "fake_excluded",
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
        _StubMeteringClient(usages),
        _StubProjectRepo(project),
        _StubIsmClient(),
    )

    assert result.skipped_excluded == 1
    assert result.pushed == 0
    assert result.skipped_no_project == 0


class _NeverExcludedTransformer:
    """is_excluded를 선언하지 않은 transformer(예: SimpleResourceTransformer
    계열)는 훅이 아예 없어도 정상 동작해야 한다 — hasattr 분기 확인."""

    resource_type = "fake_plain"

    def to_resource_payload(self, usage, project):
        return ResourcePayload(
            mid=usage["resource_id"], resource_item={}, metering_item={}
        )


def test_transformer_without_is_excluded_pushes_normally(monkeypatch):
    monkeypatch.setitem(TRANSFORMERS, "fake_plain", _NeverExcludedTransformer())

    usages = [{"resource_id": "r1", "tenant_id": "t1"}]
    project = ProjectInfo(project_id="p1", tenant_id="t1", provider_id="prov1")

    result = push_resource_type(
        "fake_plain",
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
        _StubMeteringClient(usages),
        _StubProjectRepo(project),
        _StubIsmClient(),
    )

    assert result.skipped_excluded == 0
    assert result.pushed == 1

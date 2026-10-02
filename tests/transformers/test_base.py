"""`EncodedMidResourceTransformer`의 mID 조립 규칙 고정.

volume/instance/share 실제 transformer는 각 후속 티켓에서 구현되므로, 여기서는
legacy mID 포맷을 재현하는 가짜(fake) 서브클래스로 `build_mid()` 규칙만 검증한다.
"""

import pytest

from ism_adapter.transformers.base import EncodedMidResourceTransformer, ResourcePayload


class _FakeVolumeTransformer(EncodedMidResourceTransformer):
    """legacy volume mID 포맷 재현: `{resource_id}-size::{size}-mIOPS::{max_iops}-bIOPS::{burst_iops}`"""

    resource_type = "volume"
    mid_fields = (
        ("size", "size"),
        ("mIOPS", "max_iops"),
        ("bIOPS", "burst_iops"),
    )

    def to_resource_payload(self, usage, project):
        return ResourcePayload(
            mid=self.build_mid(usage), resource_item={}, metering_item={}
        )


class _FakeInstanceTransformer(EncodedMidResourceTransformer):
    """legacy instance mID 포맷 재현: `{resource_id}-flavor::{flavor_id}-charge_type::{charge_type}`"""

    resource_type = "instance"
    mid_fields = (
        ("flavor", "flavor_id"),
        ("charge_type", "charge_type"),
    )

    def to_resource_payload(self, usage, project):
        return ResourcePayload(
            mid=self.build_mid(usage), resource_item={}, metering_item={}
        )


class _FakeShareTransformer(EncodedMidResourceTransformer):
    """legacy share(NAS) mID 포맷 재현: `{resource_id}-size::{size}`"""

    resource_type = "share"
    mid_fields = (("size", "size"),)

    def to_resource_payload(self, usage, project):
        return ResourcePayload(
            mid=self.build_mid(usage), resource_item={}, metering_item={}
        )


def test_build_mid_encodes_single_field_in_order():
    usage = {"resource_id": "share-uuid-1", "size": 100}

    mid = _FakeShareTransformer().build_mid(usage)

    assert mid == "share-uuid-1-size::100"


def test_build_mid_encodes_multiple_fields_in_declared_order():
    usage = {
        "resource_id": "volume-uuid-1",
        "size": 50,
        "max_iops": 3000,
        "burst_iops": 6000,
    }

    mid = _FakeVolumeTransformer().build_mid(usage)

    assert mid == "volume-uuid-1-size::50-mIOPS::3000-bIOPS::6000"


def test_build_mid_uses_each_subclass_own_field_declaration():
    usage = {
        "resource_id": "instance-uuid-1",
        "flavor_id": "m1.large",
        "charge_type": "Reserved",
    }

    mid = _FakeInstanceTransformer().build_mid(usage)

    assert mid == "instance-uuid-1-flavor::m1.large-charge_type::Reserved"


def test_to_resource_payload_signature_matches_simple_transformer():
    usage = {"resource_id": "share-uuid-2", "size": 10}

    payload = _FakeShareTransformer().to_resource_payload(usage, project=None)

    assert isinstance(payload, ResourcePayload)
    assert payload.mid == "share-uuid-2-size::10"


def test_encoded_mid_transformer_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        EncodedMidResourceTransformer()

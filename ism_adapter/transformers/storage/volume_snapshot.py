from ism_adapter.transformers.base import SimpleResourceTransformer


class VolumeSnapshotTransformer(SimpleResourceTransformer):
    resource_type = "volume_snapshot"

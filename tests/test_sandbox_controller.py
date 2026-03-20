"""Unit tests for the sandbox controller component."""

import pulumi

from components.cluster import create_cluster
from components.sandbox_controller import create_sandbox_controller

# We need a real node_pool output to pass as dependency.
cluster_result = create_cluster(
    project_id="test-project",
    region="us-central1",
    min_gke_cluster_version="1.35.0-gke.100",
    cluster_name="test-cluster",
    machine_type="e2-standard-4",
    node_pool_name="test-node-pool",
)

result = create_sandbox_controller(
    project_id="test-project",
    region="us-central1",
    snapshots_bucket_name="test-snapshots-bucket",
    snapshot_folder="snapshots/v1",
    snapshot_namespace="snapshot-ns",
    snapshot_ksa_name="snapshot-ksa",
    agent_sandbox_version="v0.1.0",
    node_pool=cluster_result.node_pool,
)


# ── GCS bucket ────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_snapshots_bucket_name():
    """Snapshots bucket should use the provided name."""
    return result.snapshots_bucket.name.apply(
        lambda v: assert_eq(v, "test-snapshots-bucket")
    )


@pulumi.runtime.test
def test_snapshots_bucket_location():
    """Snapshots bucket should be in the specified region."""
    return result.snapshots_bucket.location.apply(
        lambda v: assert_eq(v, "us-central1")
    )


@pulumi.runtime.test
def test_snapshots_bucket_uniform_access():
    """Snapshots bucket should have uniform bucket-level access."""
    return result.snapshots_bucket.uniform_bucket_level_access.apply(
        lambda v: assert_eq(v, True)
    )


@pulumi.runtime.test
def test_snapshots_bucket_hierarchical_namespace():
    """Snapshots bucket should have hierarchical namespace enabled."""
    return result.snapshots_bucket.hierarchical_namespace.apply(
        lambda v: assert_eq(v["enabled"], True)
    )


@pulumi.runtime.test
def test_snapshots_bucket_no_soft_delete():
    """Snapshots bucket should have soft delete disabled (0s retention)."""
    return result.snapshots_bucket.soft_delete_policy.apply(
        lambda v: assert_eq(v["retention_duration_seconds"], 0)
    )


# ── Kubernetes namespace ──────────────────────────────────────────────────────

@pulumi.runtime.test
def test_snapshot_namespace_name():
    """Snapshot namespace should use the provided name."""
    return result.snapshot_ns.metadata.apply(
        lambda v: assert_eq(v["name"], "snapshot-ns")
    )


# ── Kubernetes service account ────────────────────────────────────────────────

@pulumi.runtime.test
def test_snapshot_ksa_name():
    """Snapshot KSA should use the provided name."""
    return result.snapshot_ksa.metadata.apply(
        lambda v: assert_eq(v["name"], "snapshot-ksa")
    )


@pulumi.runtime.test
def test_snapshot_ksa_namespace():
    """Snapshot KSA should be in the snapshot namespace."""
    return result.snapshot_ksa.metadata.apply(
        lambda v: assert_eq(v["namespace"], "snapshot-ns")
    )


# ── Pod snapshot storage config ───────────────────────────────────────────────

@pulumi.runtime.test
def test_pssc_kind():
    """PodSnapshotStorageConfig should have correct kind."""
    return result.pod_snapshot_storage_config.kind.apply(
        lambda v: assert_eq(v, "PodSnapshotStorageConfig")
    )


@pulumi.runtime.test
def test_pssc_metadata_name():
    """PodSnapshotStorageConfig should be named cpu-pssc-gcs."""
    return result.pod_snapshot_storage_config.metadata.apply(
        lambda v: assert_eq(v["name"], "cpu-pssc-gcs")
    )


@pulumi.runtime.test
def test_pssc_gcs_path():
    """PodSnapshotStorageConfig should point to the correct snapshot folder."""
    return result.pod_snapshot_storage_config.spec.apply(
        lambda v: assert_eq(
            v["snapshotStorageConfig"]["gcs"]["path"], "snapshots/v1"
        )
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"

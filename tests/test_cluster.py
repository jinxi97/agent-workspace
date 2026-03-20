"""Unit tests for the GKE cluster component."""

import asyncio

import pulumi

# Pulumi needs a running event loop before set_mocks.
asyncio.set_event_loop(asyncio.new_event_loop())


class MockGcp(pulumi.runtime.Mocks):
    """Mock GCP provider – returns inputs as outputs with a fake ID."""

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        return [f"{args.name}-id", args.inputs]

    def call(self, args: pulumi.runtime.MockCallArgs):
        return {}


# Set mocks BEFORE importing the component under test.
pulumi.runtime.set_mocks(MockGcp(), preview=False)

from components.cluster import create_cluster  # noqa: E402


CLUSTER_ARGS = dict(
    project_id="test-project",
    region="us-central1",
    min_gke_cluster_version="1.35.0-gke.100",
    cluster_name="test-cluster",
    machine_type="e2-standard-4",
    node_pool_name="test-node-pool",
)

result = create_cluster(**CLUSTER_ARGS)


# ── Cluster ───────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_cluster_name():
    """Cluster should use the provided name."""
    return result.cluster.name.apply(lambda v: assert_eq(v, "test-cluster"))


@pulumi.runtime.test
def test_cluster_location():
    """Cluster should be in the specified region."""
    return result.cluster.location.apply(lambda v: assert_eq(v, "us-central1"))


@pulumi.runtime.test
def test_cluster_min_master_version():
    """Cluster should set min_master_version from input."""
    return result.cluster.min_master_version.apply(
        lambda v: assert_eq(v, "1.35.0-gke.100")
    )


@pulumi.runtime.test
def test_cluster_deletion_protection_disabled():
    """Cluster should have deletion protection disabled."""
    return result.cluster.deletion_protection.apply(lambda v: assert_eq(v, False))


@pulumi.runtime.test
def test_cluster_workload_identity():
    """Cluster should configure workload identity pool."""
    return result.cluster.workload_identity_config.apply(
        lambda v: assert_eq(v["workload_pool"], "test-project.svc.id.goog")
    )


@pulumi.runtime.test
def test_cluster_pod_snapshot_enabled():
    """Cluster should have pod snapshot addon enabled."""
    return result.cluster.addons_config.apply(
        lambda v: assert_eq(v["pod_snapshot_config"]["enabled"], True)
    )


@pulumi.runtime.test
def test_cluster_removes_default_node_pool():
    """Cluster should remove the default node pool."""
    return result.cluster.remove_default_node_pool.apply(lambda v: assert_eq(v, True))


# ── System node pool ──────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_system_node_pool_name():
    """System node pool should be named 'system-node-pool'."""
    return result.system_node_pool.name.apply(lambda v: assert_eq(v, "system-node-pool"))


@pulumi.runtime.test
def test_system_node_pool_machine_type():
    """System node pool should use the specified machine type."""
    return result.system_node_pool.node_config.apply(
        lambda v: assert_eq(v["machine_type"], "e2-standard-4")
    )


@pulumi.runtime.test
def test_system_node_pool_autoscaling():
    """System node pool should autoscale 1–5."""
    def check(v):
        assert v["min_node_count"] == 1
        assert v["max_node_count"] == 5
    return result.system_node_pool.autoscaling.apply(check)


@pulumi.runtime.test
def test_system_node_pool_workload_metadata():
    """System node pool should have GKE_METADATA workload metadata."""
    return result.system_node_pool.node_config.apply(
        lambda v: assert_eq(v["workload_metadata_config"]["mode"], "GKE_METADATA")
    )


# ── Agent workspace node pool ────────────────────────────────────────────────

@pulumi.runtime.test
def test_agent_node_pool_name():
    """Agent node pool should use the provided name."""
    return result.node_pool.name.apply(lambda v: assert_eq(v, "test-node-pool"))


@pulumi.runtime.test
def test_agent_node_pool_gvisor():
    """Agent node pool should use gvisor sandbox."""
    return result.node_pool.node_config.apply(
        lambda v: assert_eq(v["sandbox_config"]["sandbox_type"], "gvisor")
    )


@pulumi.runtime.test
def test_agent_node_pool_cos_containerd():
    """Agent node pool should use COS_CONTAINERD image type."""
    return result.node_pool.node_config.apply(
        lambda v: assert_eq(v["image_type"], "COS_CONTAINERD")
    )


@pulumi.runtime.test
def test_agent_node_pool_autoscaling():
    """Agent node pool should autoscale 1-5."""
    def check(v):
        assert v["min_node_count"] == 1
        assert v["max_node_count"] == 5
    return result.node_pool.autoscaling.apply(check)


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"

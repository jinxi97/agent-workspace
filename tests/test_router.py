"""Unit tests for the sandbox router component."""

import pulumi

from components.cluster import create_cluster
from components.sandbox_controller import create_sandbox_controller
from components.workspace_api import create_workspace_api
from components.router import create_router

# Build prerequisite components to get real Output values.
cluster_result = create_cluster(
    project_id="test-project",
    region="us-central1",
    min_gke_cluster_version="1.35.0-gke.100",
    cluster_name="test-cluster",
    machine_type="e2-standard-4",
    node_pool_name="test-node-pool",
)

controller = create_sandbox_controller(
    project_id="test-project",
    region="us-central1",
    snapshots_bucket_name="test-snapshots-bucket",
    snapshot_folder="snapshots/v1",
    snapshot_namespace="snapshot-ns",
    snapshot_ksa_name="snapshot-ksa",
    agent_sandbox_version="v0.1.0",
    node_pool=cluster_result.node_pool,
)

api = create_workspace_api(
    project_id="test-project",
    region="us-central1",
    snapshot_ns=controller.snapshot_ns,
    system_node_pool=cluster_result.system_node_pool,
    workloads_namespace="workloads-ns",
    fastapi_app_name="test-api",
    fastapi_replicas=1,
    fastapi_container_port=8080,
    fastapi_service_port=80,
    cloudbuild_file="cloudbuild.yaml",
    cloudbuild_branch_name="^main$",
    cloudbuild_location="us-central1",
    cloudbuild_repository="projects/test/locations/us-central1/connections/gh/repositories/test",
)

result = create_router(
    workloads_ns=api.workloads_ns,
    snapshot_ns=controller.snapshot_ns,
    system_node_pool=cluster_result.system_node_pool,
    sandbox_router_image="gcr.io/test-project/sandbox-router:v1",
)


# ── Service ───────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_service_name():
    """Router service should be named sandbox-router-svc."""
    return result.service.metadata.apply(
        lambda v: assert_eq(v["name"], "sandbox-router-svc")
    )


@pulumi.runtime.test
def test_service_namespace():
    """Router service should be in the workloads namespace."""
    return result.service.metadata.apply(
        lambda v: assert_eq(v["namespace"], "workloads-ns")
    )


@pulumi.runtime.test
def test_service_type():
    """Router service should be ClusterIP."""
    return result.service.spec.apply(
        lambda v: assert_eq(v["type"], "ClusterIP")
    )


@pulumi.runtime.test
def test_service_port():
    """Router service should expose port 8080."""
    return result.service.spec.apply(
        lambda v: assert_eq(v["ports"][0]["port"], 8080)
    )


@pulumi.runtime.test
def test_service_selector():
    """Router service should select app=sandbox-router."""
    return result.service.spec.apply(
        lambda v: assert_eq(v["selector"], {"app": "sandbox-router"})
    )


# ── Deployment ────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_deployment_name():
    """Router deployment should be named sandbox-router-deployment."""
    return result.deployment.metadata.apply(
        lambda v: assert_eq(v["name"], "sandbox-router-deployment")
    )


@pulumi.runtime.test
def test_deployment_namespace():
    """Router deployment should be in the workloads namespace."""
    return result.deployment.metadata.apply(
        lambda v: assert_eq(v["namespace"], "workloads-ns")
    )


@pulumi.runtime.test
def test_deployment_replicas():
    """Router deployment should have 2 replicas."""
    return result.deployment.spec.apply(
        lambda v: assert_eq(v["replicas"], 2)
    )


@pulumi.runtime.test
def test_deployment_image():
    """Router deployment should use the provided image."""
    return result.deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["containers"][0]["image"],
            "gcr.io/test-project/sandbox-router:v1",
        )
    )


@pulumi.runtime.test
def test_deployment_node_selector():
    """Router deployment should be pinned to system-node-pool."""
    return result.deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["node_selector"],
            {"cloud.google.com/gke-nodepool": "system-node-pool"},
        )
    )


@pulumi.runtime.test
def test_deployment_security_context():
    """Router deployment should run as non-root (uid/gid 1000)."""
    def check(v):
        sc = v["template"]["spec"]["security_context"]
        assert int(sc["run_as_user"]) == 1000
        assert int(sc["run_as_group"]) == 1000
    return result.deployment.spec.apply(check)


@pulumi.runtime.test
def test_deployment_readiness_probe():
    """Router container should have a readiness probe on /healthz."""
    def check(v):
        probe = v["template"]["spec"]["containers"][0]["readiness_probe"]["http_get"]
        assert probe["path"] == "/healthz"
        assert int(probe["port"]) == 8080
    return result.deployment.spec.apply(check)


@pulumi.runtime.test
def test_deployment_liveness_probe():
    """Router container should have a liveness probe on /healthz."""
    def check(v):
        probe = v["template"]["spec"]["containers"][0]["liveness_probe"]["http_get"]
        assert probe["path"] == "/healthz"
        assert int(probe["port"]) == 8080
    return result.deployment.spec.apply(check)


@pulumi.runtime.test
def test_deployment_topology_spread():
    """Router deployment should spread across zones."""
    return result.deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["topology_spread_constraints"][0]["topology_key"],
            "topology.kubernetes.io/zone",
        )
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"

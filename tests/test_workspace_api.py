"""Unit tests for the workspace API component."""

import pulumi

from components.cluster import create_cluster
from components.sandbox_controller import create_sandbox_controller
from components.workspace_api import create_workspace_api

# ── Setup: create upstream dependencies ───────────────────────────────────────
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

result = create_workspace_api(
    project_id="test-project",
    region="us-central1",
    snapshot_ns=controller.snapshot_ns,
    system_node_pool=cluster_result.system_node_pool,
    workloads_namespace="test-workloads",
    fastapi_app_name="test-api",
    fastapi_replicas=2,
    fastapi_container_port=8080,
    fastapi_service_port=80,
    cloudbuild_file="cloudbuild.yaml",
    cloudbuild_branch_name="^main$",
    cloudbuild_location="us-central1",
    cloudbuild_repository="projects/test-project/locations/us-central1/connections/github/repositories/test-repo",
)


# ── Namespace ─────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_workloads_namespace_name():
    """Workloads namespace should use the provided name."""
    return result.workloads_ns.metadata.apply(
        lambda v: assert_eq(v["name"], "test-workloads")
    )


# ── Deployment ────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_deployment_name():
    """Deployment should be named after the app."""
    return result.fastapi_deployment.metadata.apply(
        lambda v: assert_eq(v["name"], "test-api")
    )


@pulumi.runtime.test
def test_deployment_namespace():
    """Deployment should be in the workloads namespace."""
    return result.fastapi_deployment.metadata.apply(
        lambda v: assert_eq(v["namespace"], "test-workloads")
    )


@pulumi.runtime.test
def test_deployment_replicas():
    """Deployment should use the specified replica count."""
    return result.fastapi_deployment.spec.apply(
        lambda v: assert_eq(v["replicas"], 2)
    )


@pulumi.runtime.test
def test_deployment_labels():
    """Deployment should have the app label."""
    return result.fastapi_deployment.metadata.apply(
        lambda v: assert_eq(v["labels"]["app"], "test-api")
    )


@pulumi.runtime.test
def test_deployment_node_selector():
    """Deployment should target the system node pool."""
    return result.fastapi_deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["node_selector"]["cloud.google.com/gke-nodepool"],
            "system-node-pool",
        )
    )


@pulumi.runtime.test
def test_deployment_container_port():
    """Deployment container should expose the correct port."""
    return result.fastapi_deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["containers"][0]["ports"][0]["container_port"],
            8080,
        )
    )


@pulumi.runtime.test
def test_deployment_image():
    """Deployment should use the correct container image."""
    return result.fastapi_deployment.spec.apply(
        lambda v: assert_eq(
            v["template"]["spec"]["containers"][0]["image"],
            "gcr.io/test-project/test-api:latest",
        )
    )


@pulumi.runtime.test
def test_deployment_secret_refs():
    """Deployment should reference secrets for DB_PASS and JWT_SECRET."""
    def check(v):
        envs = v["template"]["spec"]["containers"][0]["env"]
        secret_envs = {e["name"]: e["value_from"]["secret_key_ref"]["key"]
                       for e in envs if "value_from" in e}
        assert secret_envs["DB_PASS"] == "db-pass"
        assert secret_envs["JWT_SECRET"] == "jwt-secret"
    return result.fastapi_deployment.spec.apply(check)


# ── Service ───────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_service_name():
    """Service should be named after the app."""
    return result.fastapi_service.metadata.apply(
        lambda v: assert_eq(v["name"], "test-api")
    )


@pulumi.runtime.test
def test_service_type():
    """Service should be NodePort for GCE ingress."""
    return result.fastapi_service.spec.apply(
        lambda v: assert_eq(v["type"], "NodePort")
    )


@pulumi.runtime.test
def test_service_ports():
    """Service should map the correct ports."""
    def check(v):
        port = v["ports"][0]
        assert port["port"] == 80
        assert port["target_port"] == 8080
    return result.fastapi_service.spec.apply(check)


@pulumi.runtime.test
def test_service_backend_config_annotation():
    """Service should reference the backend config."""
    return result.fastapi_service.metadata.apply(
        lambda v: assert_eq(
            v["annotations"]["cloud.google.com/backend-config"],
            '{"default": "test-api-backend-config"}',
        )
    )


# ── Static IP ─────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_static_ip_name():
    """Static IP should be named agent-workspace-api-ip."""
    return result.fastapi_static_ip.name.apply(
        lambda v: assert_eq(v, "agent-workspace-api-ip")
    )


# ── Ingress ───────────────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_ingress_name():
    """Ingress should be named after the app."""
    return result.fastapi_ingress.metadata.apply(
        lambda v: assert_eq(v["name"], "test-api")
    )


@pulumi.runtime.test
def test_ingress_static_ip_annotation():
    """Ingress should reference the static IP."""
    return result.fastapi_ingress.metadata.apply(
        lambda v: assert_eq(
            v["annotations"]["kubernetes.io/ingress.global-static-ip-name"],
            "agent-workspace-api-ip",
        )
    )


@pulumi.runtime.test
def test_ingress_managed_cert_annotation():
    """Ingress should reference the managed certificate."""
    return result.fastapi_ingress.metadata.apply(
        lambda v: assert_eq(
            v["annotations"]["networking.gke.io/managed-certificates"],
            "agent-workspace-api-cert",
        )
    )


@pulumi.runtime.test
def test_ingress_class():
    """Ingress should use the GCE ingress class."""
    return result.fastapi_ingress.metadata.apply(
        lambda v: assert_eq(
            v["annotations"]["kubernetes.io/ingress.class"],
            "gce",
        )
    )


@pulumi.runtime.test
def test_ingress_default_backend():
    """Ingress should route to the FastAPI service on port 80."""
    def check(v):
        backend = v["default_backend"]["service"]
        assert backend["name"] == "test-api"
        assert backend["port"]["number"] == 80
    return result.fastapi_ingress.spec.apply(check)


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"

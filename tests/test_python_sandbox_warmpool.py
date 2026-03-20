"""Unit tests for the Python sandbox warm pool component."""

import pulumi

from components.cluster import create_cluster
from components.sandbox_controller import create_sandbox_controller
from components.python_sandbox_warmpool import create_python_sandbox_warmpool

# Build prerequisites.
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

result = create_python_sandbox_warmpool(
    snapshot_ns=controller.snapshot_ns,
    snapshot_ksa=controller.snapshot_ksa,
    agent_sandbox_extensions=controller.agent_sandbox_extensions,
    pod_snapshot_storage_config=controller.pod_snapshot_storage_config,
    sandbox_template_revision="42",
    sandbox_warm_pool_replicas=3,
)


# ── SandboxTemplate ──────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_template_kind():
    """Template should be a SandboxTemplate."""
    return result.sandbox_template.kind.apply(
        lambda v: assert_eq(v, "SandboxTemplate")
    )


@pulumi.runtime.test
def test_template_name():
    """Template should be named python-runtime-template."""
    return result.sandbox_template.metadata.apply(
        lambda v: assert_eq(v["name"], "python-runtime-template")
    )


@pulumi.runtime.test
def test_template_namespace():
    """Template should be in the snapshot namespace."""
    return result.sandbox_template.metadata.apply(
        lambda v: assert_eq(v["namespace"], "snapshot-ns")
    )


@pulumi.runtime.test
def test_template_revision_annotation():
    """Template should carry the revision annotation."""
    return result.sandbox_template.metadata.apply(
        lambda v: assert_eq(v["annotations"]["funky.dev/template-revision"], "42")
    )


@pulumi.runtime.test
def test_template_container_name():
    """Template container should be named python-runtime."""
    return result.sandbox_template.spec.apply(
        lambda v: assert_eq(
            v["podTemplate"]["spec"]["containers"][0]["name"], "python-runtime"
        )
    )


@pulumi.runtime.test
def test_template_image():
    """Template should use the python-runtime-sandbox-custom image."""
    return result.sandbox_template.spec.apply(
        lambda v: assert_in(
            "python-runtime-sandbox-custom",
            v["podTemplate"]["spec"]["containers"][0]["image"],
        )
    )


@pulumi.runtime.test
def test_template_runtime_class():
    """Template should use gvisor runtime."""
    return result.sandbox_template.spec.apply(
        lambda v: assert_eq(v["podTemplate"]["spec"]["runtimeClassName"], "gvisor")
    )


@pulumi.runtime.test
def test_template_automount_disabled():
    """Template should disable service account token automount."""
    return result.sandbox_template.spec.apply(
        lambda v: assert_eq(
            v["podTemplate"]["spec"]["automountServiceAccountToken"], False
        )
    )


@pulumi.runtime.test
def test_template_command():
    """Template should run uvicorn."""
    return result.sandbox_template.spec.apply(
        lambda v: assert_eq(
            v["podTemplate"]["spec"]["containers"][0]["command"],
            ["/usr/local/bin/uvicorn"],
        )
    )


# ── SandboxWarmPool ──────────────────────────────────────────────────────────

@pulumi.runtime.test
def test_warmpool_kind():
    """Warm pool should be a SandboxWarmPool."""
    return result.sandbox_warm_pool.kind.apply(
        lambda v: assert_eq(v, "SandboxWarmPool")
    )


@pulumi.runtime.test
def test_warmpool_name():
    """Warm pool should be named python-sandbox-warmpool."""
    return result.sandbox_warm_pool.metadata.apply(
        lambda v: assert_eq(v["name"], "python-sandbox-warmpool")
    )


@pulumi.runtime.test
def test_warmpool_namespace():
    """Warm pool should be in the snapshot namespace."""
    return result.sandbox_warm_pool.metadata.apply(
        lambda v: assert_eq(v["namespace"], "snapshot-ns")
    )


@pulumi.runtime.test
def test_warmpool_replicas():
    """Warm pool should use the provided replica count."""
    return result.sandbox_warm_pool.spec.apply(
        lambda v: assert_eq(int(v["replicas"]), 3)
    )


@pulumi.runtime.test
def test_warmpool_template_ref():
    """Warm pool should reference python-runtime-template."""
    return result.sandbox_warm_pool.spec.apply(
        lambda v: assert_eq(
            v["sandboxTemplateRef"]["name"], "python-runtime-template"
        )
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"


def assert_in(substring, value):
    assert substring in value, f"Expected {substring!r} in {value!r}"

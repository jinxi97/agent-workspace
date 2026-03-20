"""Agent-sandbox controller: CRDs, snapshot infrastructure, GCS bucket, and IAM."""

from dataclasses import dataclass

import pulumi
from pulumi_gcp import container, organizations, projects, storage
import pulumi_kubernetes as kubernetes


@dataclass
class SandboxControllerResult:
    snapshot_ns: kubernetes.core.v1.Namespace
    snapshot_ksa: kubernetes.core.v1.ServiceAccount
    agent_sandbox_extensions: kubernetes.yaml.ConfigFile
    pod_snapshot_storage_config: kubernetes.apiextensions.CustomResource
    snapshots_bucket: storage.Bucket


def create_sandbox_controller(
    *,
    project_id: str,
    region: str,
    snapshots_bucket_name: str,
    snapshot_folder: str,
    snapshot_namespace: str,
    snapshot_ksa_name: str,
    agent_sandbox_version: str,
    node_pool: container.NodePool,
) -> SandboxControllerResult:
    # ── GCS bucket for snapshots ──────────────────────────────────────────
    snapshots_bucket = storage.Bucket(
        "snapshots-bucket",
        name=snapshots_bucket_name,
        location=region,
        uniform_bucket_level_access=True,
        hierarchical_namespace=storage.BucketHierarchicalNamespaceArgs(
            enabled=True,
        ),
        soft_delete_policy=storage.BucketSoftDeletePolicyArgs(
            retention_duration_seconds=0,
        ),
    )

    snapshots_managed_folder = storage.ManagedFolder(
        "snapshots-managed-folder",
        bucket=snapshots_bucket.name,
        name=f"{snapshot_folder.rstrip('/')}/",
    )

    pod_snapshot_gcs_read_writer_role = projects.IAMCustomRole(
        "pod-snapshot-gcs-read-writer-role",
        project=project_id,
        role_id="podSnapshotGcsReadWriter",
        title="podSnapshotGcsReadWriter",
        permissions=[
            "storage.objects.get",
            "storage.objects.create",
            "storage.objects.delete",
            "storage.folders.create",
        ],
    )

    # ── Kubernetes namespace & service account ────────────────────────────
    snapshot_ns = kubernetes.core.v1.Namespace(
        "snapshot-namespace",
        metadata={"name": snapshot_namespace},
    )

    snapshot_ksa = kubernetes.core.v1.ServiceAccount(
        "snapshot-ksa",
        metadata={
            "name": snapshot_ksa_name,
            "namespace": snapshot_ns.metadata["name"],
        },
        opts=pulumi.ResourceOptions(depends_on=[snapshot_ns]),
    )

    # ── IAM bindings ──────────────────────────────────────────────────────
    project = organizations.get_project_output(project_id=project_id)
    namespace_principal_set = pulumi.Output.format(
        "principalSet://iam.googleapis.com/projects/{0}/locations/global/workloadIdentityPools/{1}.svc.id.goog/namespace/{2}",
        project.number,
        project_id,
        snapshot_ns.metadata["name"],
    )

    bucket_viewer_for_namespace = storage.BucketIAMMember(
        "snapshot-namespace-bucket-viewer",
        bucket=snapshots_bucket.name,
        member=namespace_principal_set,
        role="roles/storage.bucketViewer",
    )

    snapshot_ksa_principal = pulumi.Output.format(
        "principal://iam.googleapis.com/projects/{0}/locations/global/workloadIdentityPools/{1}.svc.id.goog/subject/ns/{2}/sa/{3}",
        project.number,
        project_id,
        snapshot_ns.metadata["name"],
        snapshot_ksa.metadata["name"],
    )

    bucket_writer_for_snapshot_ksa = storage.BucketIAMMember(
        "snapshot-ksa-folder-writer",
        bucket=snapshots_bucket.name,
        member=snapshot_ksa_principal,
        role=pod_snapshot_gcs_read_writer_role.name,
    )

    bucket_object_user_for_snapshot_ksa = storage.BucketIAMMember(
        "snapshot-ksa-object-user",
        bucket=snapshots_bucket.name,
        member=snapshot_ksa_principal,
        role="roles/storage.objectUser",
    )

    vertex_ai_user_for_snapshot_ksa = projects.IAMMember(
        "snapshot-ksa-vertex-ai-user",
        project=project_id,
        role="roles/aiplatform.user",
        member=snapshot_ksa_principal,
    )

    gke_snapshot_controller_service_agent = pulumi.Output.format(
        "serviceAccount:service-{0}@container-engine-robot.iam.gserviceaccount.com",
        project.number,
    )

    bucket_object_user_for_gke_snapshot_controller = storage.BucketIAMMember(
        "gke-snapshot-controller-object-user",
        bucket=snapshots_bucket.name,
        member=gke_snapshot_controller_service_agent,
        role="roles/storage.objectUser",
    )

    # ── Agent-sandbox CRDs ────────────────────────────────────────────────
    agent_sandbox_system_ns = kubernetes.core.v1.Namespace(
        "agent-sandbox-system-namespace",
        metadata={"name": "agent-sandbox-system"},
        opts=pulumi.ResourceOptions(depends_on=[node_pool]),
    )

    agent_sandbox_manifest = kubernetes.yaml.ConfigFile(
        "agent-sandbox-manifest",
        file=f"https://github.com/kubernetes-sigs/agent-sandbox/releases/download/{agent_sandbox_version}/manifest.yaml",
        resource_prefix="agent-sandbox-manifest",
        opts=pulumi.ResourceOptions(depends_on=[agent_sandbox_system_ns]),
    )

    agent_sandbox_extensions = kubernetes.yaml.ConfigFile(
        "agent-sandbox-extensions",
        file=f"https://github.com/kubernetes-sigs/agent-sandbox/releases/download/{agent_sandbox_version}/extensions.yaml",
        resource_prefix="agent-sandbox-extensions",
        opts=pulumi.ResourceOptions(
            depends_on=[agent_sandbox_system_ns, agent_sandbox_manifest]
        ),
    )

    # ── Pod snapshot storage config ───────────────────────────────────────
    pod_snapshot_storage_config = kubernetes.apiextensions.CustomResource(
        "cpu-pssc-gcs",
        api_version="podsnapshot.gke.io/v1alpha1",
        kind="PodSnapshotStorageConfig",
        metadata={"name": "cpu-pssc-gcs"},
        spec={
            "snapshotStorageConfig": {
                "gcs": {
                    "bucket": snapshots_bucket.name,
                    "path": snapshot_folder,
                },
            },
        },
        opts=pulumi.ResourceOptions(
            depends_on=[
                agent_sandbox_extensions,
                snapshots_managed_folder,
                bucket_viewer_for_namespace,
                bucket_writer_for_snapshot_ksa,
                bucket_object_user_for_snapshot_ksa,
                bucket_object_user_for_gke_snapshot_controller,
            ]
        ),
    )

    return SandboxControllerResult(
        snapshot_ns=snapshot_ns,
        snapshot_ksa=snapshot_ksa,
        agent_sandbox_extensions=agent_sandbox_extensions,
        pod_snapshot_storage_config=pod_snapshot_storage_config,
        snapshots_bucket=snapshots_bucket,
    )

"""Pulumi program for a Standard GKE cluster with Pod Snapshot enabled."""

import os

import pulumi
from dotenv import load_dotenv
from pulumi_gcp import container, storage
import pulumi_kubernetes as kubernetes

load_dotenv()

def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


gcp_config = pulumi.Config("gcp")
project_id = gcp_config.require("project")
region = _required_env("GKE_LOCATION")
gke_version = _required_env("GKE_VERSION")
cluster_name = _required_env("CLUSTER_NAME")
machine_type = _required_env("MACHINE_TYPE")
node_pool_name = _required_env("NODE_POOL_NAME")
agent_sandbox_version = _required_env("AGENT_SANDBOX_VERSION")
snapshots_bucket_name_prefix = _required_env("SNAPSHOTS_BUCKET_NAME_PREFIX")
snapshots_bucket_name = f"{snapshots_bucket_name_prefix}{project_id}"
snapshot_folder = _required_env("SNAPSHOT_FOLDER")

cluster = container.Cluster(
    "standard-cluster",
    name=cluster_name,
    location=region,
    initial_node_count=1,
    min_master_version=gke_version,
    deletion_protection=False,
    addons_config=container.ClusterAddonsConfigArgs(
        pod_snapshot_config=container.ClusterAddonsConfigPodSnapshotConfigArgs(
            enabled=True,
        ),
    ),
    workload_identity_config=container.ClusterWorkloadIdentityConfigArgs(
        workload_pool=f"{project_id}.svc.id.goog",
    ),
    node_config=container.ClusterNodeConfigArgs(
        machine_type=machine_type,
        workload_metadata_config=container.ClusterNodeConfigWorkloadMetadataConfigArgs(
            mode="GKE_METADATA",
        ),
    ),
)

node_pool = container.NodePool(
    "agent-workspace-node-pool",
    name=node_pool_name,
    cluster=cluster.name,
    location=region,
    node_count=1,
    version=gke_version,
    node_config=container.NodePoolNodeConfigArgs(
        machine_type=machine_type,
        image_type="COS_CONTAINERD",
        sandbox_config=container.NodePoolNodeConfigSandboxConfigArgs(
            sandbox_type="gvisor",
        ),
    ),
)

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

# These resources use the default Pulumi Kubernetes provider, which reads kubeconfig
# from ~/.kube/config. Run gcloud get-credentials before pulumi up.
agent_sandbox_manifest = kubernetes.yaml.ConfigFile(
    "agent-sandbox-manifest",
    file=f"https://github.com/kubernetes-sigs/agent-sandbox/releases/download/{agent_sandbox_version}/manifest.yaml",
    resource_prefix="agent-sandbox-manifest",
    opts=pulumi.ResourceOptions(depends_on=[node_pool]),
)

agent_sandbox_extensions = kubernetes.yaml.ConfigFile(
    "agent-sandbox-extensions",
    file=f"https://github.com/kubernetes-sigs/agent-sandbox/releases/download/{agent_sandbox_version}/extensions.yaml",
    resource_prefix="agent-sandbox-extensions",
    opts=pulumi.ResourceOptions(depends_on=[agent_sandbox_manifest]),
)

pulumi.export("project_id", project_id)
pulumi.export("region", region)
pulumi.export("cluster_name", cluster.name)
pulumi.export("node_pool_name", node_pool.name)
pulumi.export("agent_sandbox_version", agent_sandbox_version)
pulumi.export("snapshots_bucket_name", snapshots_bucket.name)
pulumi.export("snapshot_folder", snapshots_managed_folder.name)

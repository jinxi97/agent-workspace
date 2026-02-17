"""Pulumi program for a Standard GKE cluster with Pod Snapshot enabled."""

import os

import pulumi
from dotenv import load_dotenv
from pulumi_gcp import container

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
gke_version = os.getenv("GKE_VERSION")

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

pulumi.export("project_id", project_id)
pulumi.export("region", region)
pulumi.export("cluster_name", cluster.name)

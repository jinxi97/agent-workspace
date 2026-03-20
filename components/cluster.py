"""GKE cluster and node pools."""

from dataclasses import dataclass

from pulumi_gcp import container


@dataclass
class ClusterResult:
    cluster: container.Cluster
    system_node_pool: container.NodePool
    node_pool: container.NodePool


def create_cluster(
    *,
    project_id: str,
    region: str,
    min_gke_cluster_version: str,
    cluster_name: str,
    machine_type: str,
    node_pool_name: str,
) -> ClusterResult:
    cluster = container.Cluster(
        "standard-cluster",
        name=cluster_name,
        location=region,
        initial_node_count=1,
        remove_default_node_pool=True,
        min_master_version=min_gke_cluster_version,
        deletion_protection=False,
        node_locations=["us-central1-a"],
        addons_config=container.ClusterAddonsConfigArgs(
            pod_snapshot_config=container.ClusterAddonsConfigPodSnapshotConfigArgs(
                enabled=True,
            ),
        ),
        workload_identity_config=container.ClusterWorkloadIdentityConfigArgs(
            workload_pool=f"{project_id}.svc.id.goog",
        ),
        maintenance_policy=container.ClusterMaintenancePolicyArgs(
            recurring_window=container.ClusterMaintenancePolicyRecurringWindowArgs(
                start_time="2026-01-01T02:00:00Z",
                end_time="2026-01-01T06:00:00Z",
                recurrence="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
            ),
        ),
    )

    system_node_pool = container.NodePool(
        "system-node-pool",
        name="system-node-pool",
        cluster=cluster.name,
        location=region,
        initial_node_count=1,
        autoscaling=container.NodePoolAutoscalingArgs(
            min_node_count=1,
            max_node_count=5,
        ),
        node_config=container.NodePoolNodeConfigArgs(
            machine_type=machine_type,
            workload_metadata_config=container.NodePoolNodeConfigWorkloadMetadataConfigArgs(
                mode="GKE_METADATA",
            ),
        ),
    )

    node_pool = container.NodePool(
        "agent-workspace-node-pool",
        name=node_pool_name,
        cluster=cluster.name,
        location=region,
        initial_node_count=1,
        autoscaling=container.NodePoolAutoscalingArgs(
            min_node_count=1,
            max_node_count=5,
        ),
        node_config=container.NodePoolNodeConfigArgs(
            machine_type=machine_type,
            image_type="COS_CONTAINERD",
            sandbox_config=container.NodePoolNodeConfigSandboxConfigArgs(
                sandbox_type="gvisor",
            ),
        ),
    )

    return ClusterResult(
        cluster=cluster,
        system_node_pool=system_node_pool,
        node_pool=node_pool,
    )

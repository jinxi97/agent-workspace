"""Pulumi program for a Standard GKE cluster with Pod Snapshot enabled."""

import pulumi
from dotenv import load_dotenv

from components.helpers import required_env, int_env, service_external_ip
from components.cluster import create_cluster
from components.sandbox_controller import create_sandbox_controller
from components.workspace_api import create_workspace_api
from components.router import create_router
from components.python_sandbox_warmpool import create_python_sandbox_warmpool
from components.claude_agent_warmpool import create_claude_agent_warmpool

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
gcp_config = pulumi.Config("gcp")
project_id = gcp_config.require("project")
region = required_env("GKE_LOCATION")
min_gke_cluster_version = required_env("GKE_VERSION")
cluster_name = required_env("CLUSTER_NAME")
machine_type = required_env("MACHINE_TYPE")
node_pool_name = required_env("NODE_POOL_NAME")
agent_sandbox_version = required_env("AGENT_SANDBOX_VERSION")
snapshots_bucket_name_prefix = required_env("SNAPSHOTS_BUCKET_NAME_PREFIX")
snapshots_bucket_name = f"{snapshots_bucket_name_prefix}{project_id}"
snapshot_folder = required_env("SNAPSHOT_FOLDER")
snapshot_namespace = required_env("SNAPSHOT_NAMESPACE")
snapshot_ksa_name = required_env("SNAPSHOT_KSA_NAME")
sandbox_template_revision = required_env("SANDBOX_TEMPLATE_REVISION")
sandbox_warm_pool_replicas = int_env("SANDBOX_WARM_POOL_REPLICAS", 2)
claude_agent_sandbox_template_revision = required_env("CLAUDE_AGENT_SANDBOX_TEMPLATE_REVISION")
claude_agent_sandbox_warm_pool_replicas = int_env("CLAUDE_AGENT_SANDBOX_WARM_POOL_REPLICAS", 2)
sandbox_router_image = required_env("SANDBOX_ROUTER_IMAGE")
workloads_namespace = required_env("WORKLOADS_NAMESPACE")
fastapi_app_name = required_env("FASTAPI_APP_NAME")
fastapi_replicas = int_env("FASTAPI_REPLICAS", 1)
fastapi_container_port = int_env("FASTAPI_CONTAINER_PORT", 8080)
fastapi_service_port = int_env("FASTAPI_SERVICE_PORT", 80)
cloudbuild_file = required_env("CLOUDBUILD_FILE")
cloudbuild_branch_name = required_env("CLOUDBUILD_BRANCH_NAME")
cloudbuild_location = required_env("CLOUDBUILD_LOCATION")
cloudbuild_repository = required_env("CLOUDBUILD_REPOSITORY")

# ── Components ────────────────────────────────────────────────────────────────
cluster_result = create_cluster(
    project_id=project_id,
    region=region,
    min_gke_cluster_version=min_gke_cluster_version,
    cluster_name=cluster_name,
    machine_type=machine_type,
    node_pool_name=node_pool_name,
)

controller = create_sandbox_controller(
    project_id=project_id,
    region=region,
    snapshots_bucket_name=snapshots_bucket_name,
    snapshot_folder=snapshot_folder,
    snapshot_namespace=snapshot_namespace,
    snapshot_ksa_name=snapshot_ksa_name,
    agent_sandbox_version=agent_sandbox_version,
    node_pool=cluster_result.node_pool,
)

api = create_workspace_api(
    project_id=project_id,
    region=region,
    snapshot_ns=controller.snapshot_ns,
    system_node_pool=cluster_result.system_node_pool,
    workloads_namespace=workloads_namespace,
    fastapi_app_name=fastapi_app_name,
    fastapi_replicas=fastapi_replicas,
    fastapi_container_port=fastapi_container_port,
    fastapi_service_port=fastapi_service_port,
    cloudbuild_file=cloudbuild_file,
    cloudbuild_branch_name=cloudbuild_branch_name,
    cloudbuild_location=cloudbuild_location,
    cloudbuild_repository=cloudbuild_repository,
)

router = create_router(
    workloads_ns=api.workloads_ns,
    snapshot_ns=controller.snapshot_ns,
    system_node_pool=cluster_result.system_node_pool,
    sandbox_router_image=sandbox_router_image,
)

python_pool = create_python_sandbox_warmpool(
    snapshot_ns=controller.snapshot_ns,
    snapshot_ksa=controller.snapshot_ksa,
    agent_sandbox_extensions=controller.agent_sandbox_extensions,
    pod_snapshot_storage_config=controller.pod_snapshot_storage_config,
    sandbox_template_revision=sandbox_template_revision,
    sandbox_warm_pool_replicas=sandbox_warm_pool_replicas,
)

claude_pool = create_claude_agent_warmpool(
    project_id=project_id,
    snapshot_ns=controller.snapshot_ns,
    snapshot_ksa=controller.snapshot_ksa,
    agent_sandbox_extensions=controller.agent_sandbox_extensions,
    pod_snapshot_storage_config=controller.pod_snapshot_storage_config,
    claude_agent_sandbox_template_revision=claude_agent_sandbox_template_revision,
    claude_agent_sandbox_warm_pool_replicas=claude_agent_sandbox_warm_pool_replicas,
)

# ── Exports ───────────────────────────────────────────────────────────────────
pulumi.export("project_id", project_id)
pulumi.export("region", region)
pulumi.export("cluster_name", cluster_result.cluster.name)
pulumi.export("system_node_pool_name", cluster_result.system_node_pool.name)
pulumi.export("sandbox_node_pool_name", cluster_result.node_pool.name)
pulumi.export("agent_sandbox_version", agent_sandbox_version)
pulumi.export("snapshots_bucket_name", controller.snapshots_bucket.name)
pulumi.export("snapshot_folder", snapshot_folder)
pulumi.export("snapshot_namespace", controller.snapshot_ns.metadata["name"])
pulumi.export("snapshot_ksa_name", controller.snapshot_ksa.metadata["name"])
pulumi.export("sandbox_template", python_pool.sandbox_template.metadata["name"])
pulumi.export("sandbox_template_revision", sandbox_template_revision)
pulumi.export("sandbox_warm_pool", python_pool.sandbox_warm_pool.metadata["name"])
pulumi.export("sandbox_warm_pool_replicas", sandbox_warm_pool_replicas)
pulumi.export("fastapi_deployment", api.fastapi_deployment.metadata["name"])
pulumi.export("fastapi_service", api.fastapi_service.metadata["name"])
pulumi.export("fastapi_static_ip", api.fastapi_static_ip.address)
pulumi.export("fastapi_ingress", api.fastapi_ingress.metadata["name"])
pulumi.export("sandbox_router_deployment", router.deployment.metadata["name"])
pulumi.export("sandbox_router_service", router.service.metadata["name"])

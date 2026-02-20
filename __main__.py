"""Pulumi program for a Standard GKE cluster with Pod Snapshot enabled."""

import os
from typing import Any

import pulumi
from dotenv import load_dotenv
from pulumi_gcp import cloudbuild, container, organizations, projects, serviceaccount, storage
import pulumi_kubernetes as kubernetes

load_dotenv()

def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {value}") from exc


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
snapshot_namespace = _required_env("SNAPSHOT_NAMESPACE")
snapshot_ksa_name = _required_env("SNAPSHOT_KSA_NAME")
sandbox_template_revision = _required_env("SANDBOX_TEMPLATE_REVISION")
sandbox_warm_pool_replicas = _int_env("SANDBOX_WARM_POOL_REPLICAS", 2)
fastapi_app_name = _required_env("FASTAPI_APP_NAME")
fastapi_container_port = _int_env("FASTAPI_CONTAINER_PORT", 8080)
fastapi_service_port = _int_env("FASTAPI_SERVICE_PORT", 80)
cloudbuild_file = _required_env("CLOUDBUILD_FILE")
cloudbuild_branch_name = _required_env("CLOUDBUILD_BRANCH_NAME")
cloudbuild_location = _required_env("CLOUDBUILD_LOCATION")
cloudbuild_repository = _required_env("CLOUDBUILD_REPOSITORY")

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

pod_snapshot_policy = kubernetes.apiextensions.CustomResource(
    "cpu-psp",
    api_version="podsnapshot.gke.io/v1alpha1",
    kind="PodSnapshotPolicy",
    metadata={
        "name": "cpu-psp",
        "namespace": snapshot_ns.metadata["name"],
    },
    spec={
        "storageConfigName": "cpu-pssc-gcs",
        "selector": {
            "matchLabels": {
                "app": "agent-sandbox-workload",
            },
        },
        "triggerConfig": {
            "type": "manual",
            "postCheckpoint": "resume",
        },
    },
    opts=pulumi.ResourceOptions(depends_on=[pod_snapshot_storage_config]),
)

sandbox_template = kubernetes.apiextensions.CustomResource(
    "python-runtime-template",
    api_version="extensions.agents.x-k8s.io/v1alpha1",
    kind="SandboxTemplate",
    metadata={
        "name": "python-runtime-template",
        "namespace": snapshot_ns.metadata["name"],
        "annotations": {
            "funky.dev/template-revision": sandbox_template_revision,
        },
    },
    spec={
        "podTemplate": {
            "metadata": {
                "labels": {
                    "app": "agent-sandbox-workload",
                },
            },
            "spec": {
                "serviceAccountName": snapshot_ksa.metadata["name"],
                "runtimeClassName": "gvisor",
                "containers": [
                    {
                        "name": "python-runtime",
                        "image": "us-central1-docker.pkg.dev/funky-485504/agent-sandbox/python-runtime-sandbox-custom:v3",
                        "command": ["/usr/local/bin/uvicorn"],
                        "args": [
                            "main:app",
                            "--host",
                            "0.0.0.0",
                            "--port",
                            "8888",
                            "--log-level",
                            "trace",
                        ],
                        "ports": [{"containerPort": 8888}],
                        "readinessProbe": {
                            "httpGet": {"path": "/", "port": 8888},
                            "initialDelaySeconds": 0,
                            "periodSeconds": 1,
                        },
                        "resources": {
                            "requests": {
                                "cpu": "250m",
                                "memory": "512Mi",
                                "ephemeral-storage": "512Mi",
                            },
                            "limits": {
                                "cpu": "1",
                                "memory": "1Gi",
                                "ephemeral-storage": "1Gi",
                            },
                        },
                    }
                ],
                "restartPolicy": "OnFailure",
            },
        },
    },
    opts=pulumi.ResourceOptions(
        depends_on=[
            agent_sandbox_extensions,
            snapshot_ksa,
            pod_snapshot_policy,
        ]
    ),
)

sandbox_warm_pool = kubernetes.apiextensions.CustomResource(
    "python-sandbox-warmpool",
    api_version="extensions.agents.x-k8s.io/v1alpha1",
    kind="SandboxWarmPool",
    metadata={
        "name": "python-sandbox-warmpool",
        "namespace": snapshot_ns.metadata["name"],
    },
    spec={
        "replicas": sandbox_warm_pool_replicas,
        "sandboxTemplateRef": {
            "name": "python-runtime-template",
        },
    },
    opts=pulumi.ResourceOptions(depends_on=[sandbox_template]),
)

fastapi_labels = {"app": fastapi_app_name}

fastapi_ksa = kubernetes.core.v1.ServiceAccount(
    "fastapi-ksa",
    metadata={
        "name": f"{fastapi_app_name}-sa",
        "namespace": "default",
    },
)

fastapi_sandboxclaims_role = kubernetes.rbac.v1.Role(
    "fastapi-sandboxclaims-role",
    metadata={
        "name": f"{fastapi_app_name}-sandboxclaims-role",
        "namespace": snapshot_ns.metadata["name"],
    },
    rules=[
        {
            "apiGroups": ["extensions.agents.x-k8s.io"],
            "resources": ["sandboxclaims"],
            "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"],
        },
        {
            "apiGroups": ["agents.x-k8s.io"],
            "resources": ["sandboxclaims", "sandboxes", "sandboxtemplates"],
            "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"],
        },
    ],
    opts=pulumi.ResourceOptions(depends_on=[snapshot_ns]),
)

fastapi_sandboxclaims_rolebinding = kubernetes.rbac.v1.RoleBinding(
    "fastapi-sandboxclaims-rolebinding",
    metadata={
        "name": f"{fastapi_app_name}-sandboxclaims-rb",
        "namespace": snapshot_ns.metadata["name"],
    },
    role_ref={
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": fastapi_sandboxclaims_role.metadata["name"],
    },
    subjects=[
        {
            "kind": "ServiceAccount",
            "name": fastapi_ksa.metadata["name"],
            "namespace": "default",
        }
    ],
    opts=pulumi.ResourceOptions(depends_on=[fastapi_ksa, fastapi_sandboxclaims_role]),
)

fastapi_deployment = kubernetes.apps.v1.Deployment(
    "fastapi-deployment",
    metadata={"name": fastapi_app_name, "labels": fastapi_labels},
    spec={
        "replicas": 1,
        "selector": {"matchLabels": fastapi_labels},
        "template": {
            "metadata": {"labels": fastapi_labels},
            "spec": {
                "serviceAccountName": fastapi_ksa.metadata["name"],
                "containers": [
                    {
                        "name": fastapi_app_name,
                        "image": f"gcr.io/{project_id}/{fastapi_app_name}:latest",
                        "ports": [{"containerPort": fastapi_container_port}],
                    }
                ]
            },
        },
    },
    opts=pulumi.ResourceOptions(
        depends_on=[node_pool, fastapi_sandboxclaims_rolebinding],
    ),
)

fastapi_service = kubernetes.core.v1.Service(
    "fastapi-service",
    metadata={"name": fastapi_app_name, "labels": fastapi_labels},
    spec={
        "type": "LoadBalancer",
        "selector": fastapi_labels,
        "ports": [{"port": fastapi_service_port, "targetPort": fastapi_container_port}],
    },
    opts=pulumi.ResourceOptions(depends_on=[fastapi_deployment]),
)

sandbox_router_labels = {"app": "sandbox-router"}

sandbox_router_ksa = kubernetes.core.v1.ServiceAccount(
    "sandbox-router-ksa",
    metadata={"name": "sandbox-router-sa", "namespace": "default"},
)

sandbox_router_role = kubernetes.rbac.v1.Role(
    "sandbox-router-role",
    metadata={
        "name": "sandbox-router-role",
        "namespace": snapshot_ns.metadata["name"],
    },
    rules=[
        {
            "apiGroups": ["extensions.agents.x-k8s.io", "agents.x-k8s.io"],
            "resources": ["sandboxclaims", "sandboxtemplates", "sandboxes"],
            "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
        }
    ],
    opts=pulumi.ResourceOptions(depends_on=[snapshot_ns]),
)

sandbox_router_rolebinding = kubernetes.rbac.v1.RoleBinding(
    "sandbox-router-rolebinding",
    metadata={
        "name": "sandbox-router-binding",
        "namespace": snapshot_ns.metadata["name"],
    },
    role_ref={
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": sandbox_router_role.metadata["name"],
    },
    subjects=[
        {
            "kind": "ServiceAccount",
            "name": sandbox_router_ksa.metadata["name"],
            "namespace": "default",
        }
    ],
    opts=pulumi.ResourceOptions(depends_on=[sandbox_router_ksa, sandbox_router_role]),
)

sandbox_router_service = kubernetes.core.v1.Service(
    "sandbox-router-service",
    metadata={"name": "sandbox-router-svc", "namespace": "default"},
    spec={
        "type": "ClusterIP",
        "selector": sandbox_router_labels,
        "ports": [
            {
                "name": "http",
                "protocol": "TCP",
                "port": 8080,
                "targetPort": 8080,
            }
        ],
    },
    opts=pulumi.ResourceOptions(depends_on=[node_pool]),
)

sandbox_router_deployment = kubernetes.apps.v1.Deployment(
    "sandbox-router-deployment",
    metadata={"name": "sandbox-router-deployment", "namespace": "default"},
    spec={
        "replicas": 2,
        "selector": {"matchLabels": sandbox_router_labels},
        "template": {
            "metadata": {"labels": sandbox_router_labels},
            "spec": {
                "serviceAccountName": sandbox_router_ksa.metadata["name"],
                "topologySpreadConstraints": [
                    {
                        "maxSkew": 1,
                        "topologyKey": "topology.kubernetes.io/zone",
                        "whenUnsatisfiable": "ScheduleAnyway",
                        "labelSelector": {"matchLabels": sandbox_router_labels},
                    }
                ],
                "securityContext": {"runAsUser": 1000, "runAsGroup": 1000},
                "containers": [
                    {
                        "name": "router",
                        "image": "us-central1-docker.pkg.dev/k8s-staging-images/agent-sandbox/sandbox-router:v20251124-v0.1.0-10-ge26ddb2",
                        "ports": [{"containerPort": 8080}],
                        "readinessProbe": {
                            "httpGet": {"path": "/healthz", "port": 8080},
                            "initialDelaySeconds": 5,
                            "periodSeconds": 5,
                        },
                        "livenessProbe": {
                            "httpGet": {"path": "/healthz", "port": 8080},
                            "initialDelaySeconds": 10,
                            "periodSeconds": 10,
                        },
                        "resources": {
                            "requests": {"cpu": "250m", "memory": "512Mi"},
                            "limits": {"cpu": "1000m", "memory": "1Gi"},
                        },
                    }
                ],
            },
        },
    },
    opts=pulumi.ResourceOptions(
        depends_on=[sandbox_router_service, sandbox_router_rolebinding]
    ),
)

cloud_build_sa = serviceaccount.Account(
    "agent-workspace-cloudbuild-sa",
    account_id="agentworkspacebuild",
    display_name="Agent Workspace Cloud Build",
    project=project_id,
)
cloud_build_member = cloud_build_sa.email.apply(
    lambda email: f"serviceAccount:{email}"
)
cloud_build_service_account = (
    cloud_build_sa.email.apply(
        lambda email: f"projects/{project_id}/serviceAccounts/{email}"
    )
)
cloud_build_service_agent_member = project.number.apply(
    lambda num: f"serviceAccount:service-{num}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
)

cloudbuild_gke_developer = projects.IAMMember(
    "cloudbuild-gke-developer",
    project=project_id,
    role="roles/container.developer",
    member=cloud_build_member,
)

cloudbuild_gke_viewer = projects.IAMMember(
    "cloudbuild-gke-viewer",
    project=project_id,
    role="roles/container.clusterViewer",
    member=cloud_build_member,
)

cloudbuild_storage_admin = projects.IAMMember(
    "cloudbuild-storage-admin",
    project=project_id,
    role="roles/storage.admin",
    member=cloud_build_member,
)

cloudbuild_artifact_registry_writer = projects.IAMMember(
    "cloudbuild-artifact-registry-writer",
    project=project_id,
    role="roles/artifactregistry.writer",
    member=cloud_build_member,
)

cloudbuild_logging_writer = projects.IAMMember(
    "cloudbuild-logging-writer",
    project=project_id,
    role="roles/logging.logWriter",
    member=cloud_build_member,
)

cloudbuild_sa_user = serviceaccount.IAMMember(
    "cloudbuild-sa-user",
    service_account_id=cloud_build_sa.name,
    role="roles/iam.serviceAccountUser",
    member=cloud_build_service_agent_member,
)

cloudbuild_sa_token_creator = serviceaccount.IAMMember(
    "cloudbuild-sa-token-creator",
    service_account_id=cloud_build_sa.name,
    role="roles/iam.serviceAccountTokenCreator",
    member=cloud_build_service_agent_member,
)

fastapi_cloudbuild_trigger = cloudbuild.Trigger(
    "fastapi-cloudbuild-trigger",
    name=f"{fastapi_app_name}-main-trigger",
    description=f"Build and deploy {fastapi_app_name} on push to main",
    location=cloudbuild_location,
    filename=cloudbuild_file,
    repository_event_config=cloudbuild.TriggerRepositoryEventConfigArgs(
        repository=cloudbuild_repository,
        push=cloudbuild.TriggerRepositoryEventConfigPushArgs(
            branch=cloudbuild_branch_name,
        ),
    ),
    service_account=cloud_build_service_account,
    opts=pulumi.ResourceOptions(
        depends_on=[
            cloudbuild_gke_developer,
            cloudbuild_gke_viewer,
            cloudbuild_storage_admin,
            cloudbuild_artifact_registry_writer,
            cloudbuild_logging_writer,
            cloudbuild_sa_user,
            cloudbuild_sa_token_creator,
        ],
    ),
)

def _service_external_ip(status: Any) -> str | None:
    if status is None:
        return None

    if isinstance(status, dict):
        ingress = status.get("load_balancer", {}).get("ingress", [])
        if ingress:
            first = ingress[0]
            if isinstance(first, dict):
                return first.get("ip")
        return None

    load_balancer = getattr(status, "load_balancer", None)
    if not load_balancer:
        return None
    ingress = getattr(load_balancer, "ingress", None) or []
    if not ingress:
        return None
    return getattr(ingress[0], "ip", None)


fastapi_external_ip = fastapi_service.status.apply(_service_external_ip)

pulumi.export("project_id", project_id)
pulumi.export("region", region)
pulumi.export("cluster_name", cluster.name)
pulumi.export("node_pool_name", node_pool.name)
pulumi.export("agent_sandbox_version", agent_sandbox_version)
pulumi.export("snapshots_bucket_name", snapshots_bucket.name)
pulumi.export("snapshot_folder", snapshots_managed_folder.name)
pulumi.export("pod_snapshot_gcs_read_writer_role", pod_snapshot_gcs_read_writer_role.name)
pulumi.export("snapshot_namespace", snapshot_ns.metadata["name"])
pulumi.export("snapshot_ksa_name", snapshot_ksa.metadata["name"])
pulumi.export("project_number", project.number)
pulumi.export("pod_snapshot_storage_config", pod_snapshot_storage_config.metadata["name"])
pulumi.export("pod_snapshot_policy", pod_snapshot_policy.metadata["name"])
pulumi.export("sandbox_template", sandbox_template.metadata["name"])
pulumi.export("sandbox_template_revision", sandbox_template_revision)
pulumi.export("sandbox_warm_pool", sandbox_warm_pool.metadata["name"])
pulumi.export("sandbox_warm_pool_replicas", sandbox_warm_pool_replicas)
pulumi.export("fastapi_deployment", fastapi_deployment.metadata["name"])
pulumi.export("fastapi_service", fastapi_service.metadata["name"])
pulumi.export("fastapi_external_ip", fastapi_external_ip)
pulumi.export("sandbox_router_deployment", sandbox_router_deployment.metadata["name"])
pulumi.export("sandbox_router_service", sandbox_router_service.metadata["name"])
pulumi.export("sandbox_router_service_account", sandbox_router_ksa.metadata["name"])
pulumi.export("fastapi_cloudbuild_trigger_id", fastapi_cloudbuild_trigger.trigger_id)

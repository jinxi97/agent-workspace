"""Workspace API: FastAPI deployment, ingress, certs, and Cloud Build CI/CD."""

from dataclasses import dataclass

import pulumi
from pulumi_gcp import cloudbuild, compute, container, organizations, projects, serviceaccount
import pulumi_kubernetes as kubernetes


@dataclass
class WorkspaceApiResult:
    workloads_ns: kubernetes.core.v1.Namespace
    fastapi_deployment: kubernetes.apps.v1.Deployment
    fastapi_service: kubernetes.core.v1.Service
    fastapi_static_ip: compute.GlobalAddress
    fastapi_ingress: kubernetes.networking.v1.Ingress


def create_workspace_api(
    *,
    project_id: str,
    region: str,
    snapshot_ns: kubernetes.core.v1.Namespace,
    system_node_pool: container.NodePool,
    workloads_namespace: str,
    fastapi_app_name: str,
    fastapi_replicas: int,
    fastapi_container_port: int,
    fastapi_service_port: int,
    cloudbuild_file: str,
    cloudbuild_branch_name: str,
    cloudbuild_location: str,
    cloudbuild_repository: str,
) -> WorkspaceApiResult:
    fastapi_labels = {"app": fastapi_app_name}

    # ── Namespace ─────────────────────────────────────────────────────────
    workloads_ns = kubernetes.core.v1.Namespace(
        "workloads-namespace",
        metadata={"name": workloads_namespace},
    )

    # ── Secret (placeholder – actual values managed out-of-band) ──────────
    agent_workspace_secret = kubernetes.core.v1.Secret(
        "agent-workspace-secrets",
        metadata={
            "name": "agent-workspace-secrets",
            "namespace": workloads_ns.metadata["name"],
        },
        string_data={},
        opts=pulumi.ResourceOptions(
            depends_on=[workloads_ns],
            ignore_changes=["stringData", "data"],
        ),
    )

    # ── Service account + IAM ─────────────────────────────────────────────
    fastapi_ksa = kubernetes.core.v1.ServiceAccount(
        "fastapi-ksa",
        metadata={
            "name": f"{fastapi_app_name}-sa",
            "namespace": workloads_ns.metadata["name"],
        },
        opts=pulumi.ResourceOptions(depends_on=[workloads_ns]),
    )

    project = organizations.get_project_output(project_id=project_id)
    fastapi_ksa_principal = pulumi.Output.format(
        "principal://iam.googleapis.com/projects/{0}/locations/global/workloadIdentityPools/{1}.svc.id.goog/subject/ns/{2}/sa/{3}",
        project.number,
        project_id,
        workloads_ns.metadata["name"],
        fastapi_ksa.metadata["name"],
    )

    fastapi_cloudsql_client = projects.IAMMember(
        "fastapi-ksa-cloudsql-client",
        project=project_id,
        role="roles/cloudsql.client",
        member=fastapi_ksa_principal,
    )

    # ── RBAC for sandbox claims ───────────────────────────────────────────
    fastapi_sandboxclaims_role = kubernetes.rbac.v1.Role(
        "fastapi-sandboxclaims-role",
        metadata={
            "name": f"{fastapi_app_name}-sandboxclaims-role",
            "namespace": snapshot_ns.metadata["name"],
        },
        rules=[
            {
                "apiGroups": ["extensions.agents.x-k8s.io"],
                "resources": ["sandboxclaims", "sandboxtemplates"],
                "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"],
            },
            {
                "apiGroups": ["agents.x-k8s.io"],
                "resources": ["sandboxclaims", "sandboxes", "sandboxtemplates"],
                "verbs": ["create", "get", "list", "watch", "update", "patch", "delete"],
            },
            {
                "apiGroups": ["podsnapshot.gke.io"],
                "resources": ["podsnapshotmanualtriggers", "podsnapshots", "podsnapshotpolicies"],
                "verbs": ["create", "get", "list", "watch", "delete"],
            },
            {
                "apiGroups": [""],
                "resources": ["pods"],
                "verbs": ["get", "list", "patch"],
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
                "namespace": workloads_ns.metadata["name"],
            }
        ],
        opts=pulumi.ResourceOptions(depends_on=[fastapi_ksa, fastapi_sandboxclaims_role]),
    )

    # ── Deployment ────────────────────────────────────────────────────────
    fastapi_deployment = kubernetes.apps.v1.Deployment(
        "fastapi-deployment",
        metadata={
            "name": fastapi_app_name,
            "namespace": workloads_ns.metadata["name"],
            "labels": fastapi_labels,
            "annotations": {
                "pulumi.com/skipAwait": "true",
            },
        },
        spec={
            "replicas": fastapi_replicas,
            "selector": {"matchLabels": fastapi_labels},
            "template": {
                "metadata": {"labels": fastapi_labels},
                "spec": {
                    "serviceAccountName": fastapi_ksa.metadata["name"],
                    "nodeSelector": {"cloud.google.com/gke-nodepool": "system-node-pool"},
                    "containers": [
                        {
                            "name": fastapi_app_name,
                            "image": f"gcr.io/{project_id}/{fastapi_app_name}:latest",
                            "ports": [{"containerPort": fastapi_container_port}],
                            "env": [
                                {"name": "PORT", "value": str(fastapi_container_port)},
                                {"name": "CLOUD_SQL_CONNECTION_NAME", "value": "funky-485504:us-central1:funky-landing"},
                                {"name": "DB_USER", "value": "postgres"},
                                {"name": "DB_NAME", "value": "workspace_api"},
                                {"name": "GOOGLE_CLIENT_ID", "value": "819221826816-5v3r7pgtj96l56cs3770vesaa79r9rk5.apps.googleusercontent.com"},
                                {
                                    "name": "DB_PASS",
                                    "valueFrom": {"secretKeyRef": {"name": "agent-workspace-secrets", "key": "db-pass"}},
                                },
                                {
                                    "name": "JWT_SECRET",
                                    "valueFrom": {"secretKeyRef": {"name": "agent-workspace-secrets", "key": "jwt-secret"}},
                                },
                            ],
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
            depends_on=[system_node_pool, fastapi_ksa, fastapi_sandboxclaims_rolebinding, agent_workspace_secret],
            ignore_changes=["spec.template.spec.containers[*].image"],
        ),
    )

    # ── Networking: BackendConfig, Service, IP, Cert, FrontendConfig, Ingress
    fastapi_backend_config = kubernetes.apiextensions.CustomResource(
        "fastapi-backend-config",
        api_version="cloud.google.com/v1",
        kind="BackendConfig",
        metadata={
            "name": f"{fastapi_app_name}-backend-config",
            "namespace": workloads_ns.metadata["name"],
        },
        spec={
            "timeoutSec": 3600,
        },
        opts=pulumi.ResourceOptions(depends_on=[workloads_ns]),
    )

    fastapi_service = kubernetes.core.v1.Service(
        "fastapi-service",
        metadata={
            "name": fastapi_app_name,
            "namespace": workloads_ns.metadata["name"],
            "labels": fastapi_labels,
            "annotations": {
                "cloud.google.com/backend-config": f'{{"default": "{fastapi_app_name}-backend-config"}}',
            },
        },
        spec={
            "type": "NodePort",
            "selector": fastapi_labels,
            "ports": [{"port": fastapi_service_port, "targetPort": fastapi_container_port}],
        },
        opts=pulumi.ResourceOptions(depends_on=[fastapi_deployment, fastapi_backend_config]),
    )

    fastapi_static_ip = compute.GlobalAddress(
        "fastapi-static-ip",
        name="agent-workspace-api-ip",
        project=project_id,
    )

    fastapi_managed_cert = kubernetes.apiextensions.CustomResource(
        "fastapi-managed-cert",
        api_version="networking.gke.io/v1",
        kind="ManagedCertificate",
        metadata={
            "name": "agent-workspace-api-cert",
            "namespace": workloads_ns.metadata["name"],
        },
        spec={"domains": ["api.funky.dev"]},
    )

    fastapi_frontend_config = kubernetes.apiextensions.CustomResource(
        "fastapi-frontend-config",
        api_version="networking.gke.io/v1beta1",
        kind="FrontendConfig",
        metadata={
            "name": f"{fastapi_app_name}-frontend-config",
            "namespace": workloads_ns.metadata["name"],
        },
        spec={
            "redirectToHttps": {"enabled": True},
        },
        opts=pulumi.ResourceOptions(depends_on=[workloads_ns]),
    )

    fastapi_ingress = kubernetes.networking.v1.Ingress(
        "fastapi-ingress",
        metadata={
            "name": fastapi_app_name,
            "namespace": workloads_ns.metadata["name"],
            "annotations": {
                "kubernetes.io/ingress.global-static-ip-name": "agent-workspace-api-ip",
                "networking.gke.io/managed-certificates": "agent-workspace-api-cert",
                "kubernetes.io/ingress.class": "gce",
                "networking.gke.io/v1beta1.FrontendConfig": f"{fastapi_app_name}-frontend-config",
            },
        },
        spec={
            "defaultBackend": {
                "service": {
                    "name": fastapi_app_name,
                    "port": {"number": fastapi_service_port},
                }
            }
        },
        opts=pulumi.ResourceOptions(depends_on=[fastapi_service, fastapi_managed_cert, fastapi_static_ip, fastapi_frontend_config]),
    )

    fastapi_pdb = kubernetes.policy.v1.PodDisruptionBudget(
        "fastapi-pdb",
        metadata={
            "name": f"{fastapi_app_name}-pdb",
            "namespace": workloads_ns.metadata["name"],
        },
        spec={
            "minAvailable": 1,
            "selector": {"matchLabels": fastapi_labels},
        },
        opts=pulumi.ResourceOptions(depends_on=[fastapi_deployment]),
    )

    # ── Cloud Build ───────────────────────────────────────────────────────
    cloud_build_sa = serviceaccount.Account(
        "agent-workspace-cloudbuild-sa",
        account_id="agentworkspacebuild",
        display_name="Agent Workspace Cloud Build",
        project=project_id,
    )
    cloud_build_member = cloud_build_sa.email.apply(
        lambda email: f"serviceAccount:{email}"
    )
    cloud_build_service_account = cloud_build_sa.email.apply(
        lambda email: f"projects/{project_id}/serviceAccounts/{email}"
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

    return WorkspaceApiResult(
        workloads_ns=workloads_ns,
        fastapi_deployment=fastapi_deployment,
        fastapi_service=fastapi_service,
        fastapi_static_ip=fastapi_static_ip,
        fastapi_ingress=fastapi_ingress,
    )

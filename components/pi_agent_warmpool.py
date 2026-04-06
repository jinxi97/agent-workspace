"""pi-agent sandbox template and warm pool."""

from dataclasses import dataclass

import pulumi
import pulumi_kubernetes as kubernetes


@dataclass
class PiAgentWarmpoolResult:
    sandbox_template: kubernetes.apiextensions.CustomResource
    sandbox_warm_pool: kubernetes.apiextensions.CustomResource


def create_pi_agent_warmpool(
    *,
    snapshot_ns: kubernetes.core.v1.Namespace,
    snapshot_ksa: kubernetes.core.v1.ServiceAccount,
    agent_sandbox_extensions: kubernetes.yaml.ConfigFile,
    pod_snapshot_storage_config: kubernetes.apiextensions.CustomResource,
    pi_agent_sandbox_template_revision: str,
    pi_agent_sandbox_warm_pool_replicas: int,
    pi_agent_image_version: str,
    gemini_api_key_secret_name: str,
    gemini_api_key_secret_key: str = "GEMINI_API_KEY",
) -> PiAgentWarmpoolResult:
    pi_agent_sandbox_template = kubernetes.apiextensions.CustomResource(
        "pi-agent-sandbox-template",
        api_version="extensions.agents.x-k8s.io/v1alpha1",
        kind="SandboxTemplate",
        metadata={
            "name": "pi-agent-sandbox-template",
            "namespace": snapshot_ns.metadata["name"],
            "annotations": {
                "funky.dev/template-revision": pi_agent_sandbox_template_revision,
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
                    "automountServiceAccountToken": False,
                    "runtimeClassName": "gvisor",
                    "volumes": [
                        # Shared workspace: the agent reads/writes here,
                        # syncthing watches and syncs it to the user's desktop.
                        {"name": "workspace", "emptyDir": {}},
                        # Ephemeral syncthing config (device ID is regenerated
                        # on every pod spawn — users must re-pair each time).
                        {"name": "syncthing-config", "emptyDir": {}},
                    ],
                    "containers": [
                        {
                            "name": "pi-agent-sandbox",
                            "image": f"us-central1-docker.pkg.dev/funky-485504/agent-sandbox/pi-agent-sandbox:{pi_agent_image_version}",
                            "env": [
                                {"name": "WORKSPACE_DIR", "value": "/workspace"},
                                {"name": "PORT", "value": "3000"},
                                {
                                    "name": "GEMINI_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": gemini_api_key_secret_name,
                                            "key": gemini_api_key_secret_key,
                                        },
                                    },
                                },
                            ],
                            "ports": [{"containerPort": 3000}],
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                            ],
                            "readinessProbe": {
                                "httpGet": {"path": "/", "port": 3000},
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
                        },
                        {
                            "name": "syncthing",
                            "image": "syncthing/syncthing:1.27",
                            "env": [
                                # Bind the admin UI to all interfaces so it's
                                # reachable in-cluster via port-forward / a
                                # per-pod Service.
                                {"name": "STGUIADDRESS", "value": "0.0.0.0:8384"},
                                {"name": "PUID", "value": "1000"},
                                {"name": "PGID", "value": "1000"},
                            ],
                            "ports": [
                                {"containerPort": 22000, "protocol": "TCP", "name": "sync-tcp"},
                                {"containerPort": 22000, "protocol": "UDP", "name": "sync-quic"},
                                {"containerPort": 21027, "protocol": "UDP", "name": "discovery"},
                                {"containerPort": 8384, "protocol": "TCP", "name": "admin-ui"},
                            ],
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/var/syncthing/Sync/workspace"},
                                {"name": "syncthing-config", "mountPath": "/var/syncthing/config"},
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": "50m",
                                    "memory": "128Mi",
                                    "ephemeral-storage": "128Mi",
                                },
                                "limits": {
                                    "cpu": "500m",
                                    "memory": "512Mi",
                                    "ephemeral-storage": "512Mi",
                                },
                            },
                        },
                    ],
                    "restartPolicy": "OnFailure",
                },
            },
        },
        opts=pulumi.ResourceOptions(
            depends_on=[
                agent_sandbox_extensions,
                snapshot_ksa,
                pod_snapshot_storage_config,
            ]
        ),
    )

    pi_agent_sandbox_warm_pool = kubernetes.apiextensions.CustomResource(
        "pi-agent-sandbox-warmpool",
        api_version="extensions.agents.x-k8s.io/v1alpha1",
        kind="SandboxWarmPool",
        metadata={
            "name": "pi-agent-sandbox-warmpool",
            "namespace": snapshot_ns.metadata["name"],
        },
        spec={
            "replicas": pi_agent_sandbox_warm_pool_replicas,
            "sandboxTemplateRef": {
                "name": "pi-agent-sandbox-template",
            },
        },
        opts=pulumi.ResourceOptions(depends_on=[pi_agent_sandbox_template]),
    )

    return PiAgentWarmpoolResult(
        sandbox_template=pi_agent_sandbox_template,
        sandbox_warm_pool=pi_agent_sandbox_warm_pool,
    )

"""Python runtime sandbox template and warm pool."""

from dataclasses import dataclass

import pulumi
import pulumi_kubernetes as kubernetes


@dataclass
class PythonSandboxWarmpoolResult:
    sandbox_template: kubernetes.apiextensions.CustomResource
    sandbox_warm_pool: kubernetes.apiextensions.CustomResource


def create_python_sandbox_warmpool(
    *,
    snapshot_ns: kubernetes.core.v1.Namespace,
    snapshot_ksa: kubernetes.core.v1.ServiceAccount,
    agent_sandbox_extensions: kubernetes.yaml.ConfigFile,
    pod_snapshot_storage_config: kubernetes.apiextensions.CustomResource,
    sandbox_template_revision: str,
    sandbox_warm_pool_replicas: int,
) -> PythonSandboxWarmpoolResult:
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
                    "automountServiceAccountToken": False,
                    "runtimeClassName": "gvisor",
                    "containers": [
                        {
                            "name": "python-runtime",
                            "image": "us-central1-docker.pkg.dev/funky-485504/agent-sandbox/python-runtime-sandbox-custom:v13",
                            "command": ["/usr/local/bin/uvicorn"],
                            "args": [
                                "main:app",
                                "--host",
                                "0.0.0.0",
                                "--port",
                                "8888",
                                "--log-level",
                                "info",
                            ],
                            "ports": [{"containerPort": 8888}],
                            "readinessProbe": {
                                "httpGet": {"path": "/", "port": 8888},
                                "initialDelaySeconds": 0,
                                "periodSeconds": 1,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/", "port": 8888},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5,
                                "failureThreshold": 6,
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
                pod_snapshot_storage_config,
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

    return PythonSandboxWarmpoolResult(
        sandbox_template=sandbox_template,
        sandbox_warm_pool=sandbox_warm_pool,
    )

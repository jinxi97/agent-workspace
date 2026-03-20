"""Claude agent sandbox template and warm pool."""

from dataclasses import dataclass

import pulumi
import pulumi_kubernetes as kubernetes


@dataclass
class ClaudeAgentWarmpoolResult:
    sandbox_template: kubernetes.apiextensions.CustomResource
    sandbox_warm_pool: kubernetes.apiextensions.CustomResource


def create_claude_agent_warmpool(
    *,
    project_id: str,
    snapshot_ns: kubernetes.core.v1.Namespace,
    snapshot_ksa: kubernetes.core.v1.ServiceAccount,
    agent_sandbox_extensions: kubernetes.yaml.ConfigFile,
    pod_snapshot_storage_config: kubernetes.apiextensions.CustomResource,
    claude_agent_sandbox_template_revision: str,
    claude_agent_sandbox_warm_pool_replicas: int,
) -> ClaudeAgentWarmpoolResult:
    claude_agent_sandbox_template = kubernetes.apiextensions.CustomResource(
        "claude-agent-sandbox-template",
        api_version="extensions.agents.x-k8s.io/v1alpha1",
        kind="SandboxTemplate",
        metadata={
            "name": "claude-agent-sandbox-template",
            "namespace": snapshot_ns.metadata["name"],
            "annotations": {
                "funky.dev/template-revision": claude_agent_sandbox_template_revision,
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
                            "name": "claude-agent-sandbox",
                            "image": "us-central1-docker.pkg.dev/funky-485504/agent-sandbox/claude-agent-sandbox:v11",
                            "env": [
                                {"name": "CLAUDE_CODE_USE_VERTEX", "value": "1"},
                                {"name": "ANTHROPIC_VERTEX_PROJECT_ID", "value": project_id},
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
                pod_snapshot_storage_config,
            ]
        ),
    )

    claude_agent_sandbox_warm_pool = kubernetes.apiextensions.CustomResource(
        "claude-agent-sandbox-warmpool",
        api_version="extensions.agents.x-k8s.io/v1alpha1",
        kind="SandboxWarmPool",
        metadata={
            "name": "claude-agent-sandbox-warmpool",
            "namespace": snapshot_ns.metadata["name"],
        },
        spec={
            "replicas": claude_agent_sandbox_warm_pool_replicas,
            "sandboxTemplateRef": {
                "name": "claude-agent-sandbox-template",
            },
        },
        opts=pulumi.ResourceOptions(depends_on=[claude_agent_sandbox_template]),
    )

    return ClaudeAgentWarmpoolResult(
        sandbox_template=claude_agent_sandbox_template,
        sandbox_warm_pool=claude_agent_sandbox_warm_pool,
    )

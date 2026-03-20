"""Sandbox router: deployment, service, and RBAC."""

from dataclasses import dataclass

import pulumi
from pulumi_gcp import container
import pulumi_kubernetes as kubernetes


@dataclass
class RouterResult:
    deployment: kubernetes.apps.v1.Deployment
    service: kubernetes.core.v1.Service


def create_router(
    *,
    workloads_ns: kubernetes.core.v1.Namespace,
    snapshot_ns: kubernetes.core.v1.Namespace,
    system_node_pool: container.NodePool,
    sandbox_router_image: str,
) -> RouterResult:
    sandbox_router_labels = {"app": "sandbox-router"}

    sandbox_router_ksa = kubernetes.core.v1.ServiceAccount(
        "sandbox-router-ksa",
        metadata={"name": "sandbox-router-sa", "namespace": workloads_ns.metadata["name"]},
        opts=pulumi.ResourceOptions(depends_on=[workloads_ns]),
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
                "namespace": workloads_ns.metadata["name"],
            }
        ],
        opts=pulumi.ResourceOptions(depends_on=[sandbox_router_ksa, sandbox_router_role]),
    )

    sandbox_router_service = kubernetes.core.v1.Service(
        "sandbox-router-service",
        metadata={
            "name": "sandbox-router-svc",
            "namespace": workloads_ns.metadata["name"],
            "annotations": {"pulumi.com/skipAwait": "true"},
        },
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
        opts=pulumi.ResourceOptions(
            depends_on=[system_node_pool],
            custom_timeouts=pulumi.CustomTimeouts(create="30s", update="30s"),
        ),
    )

    sandbox_router_deployment = kubernetes.apps.v1.Deployment(
        "sandbox-router-deployment",
        metadata={
            "name": "sandbox-router-deployment",
            "namespace": workloads_ns.metadata["name"],
            "annotations": {"pulumi.com/skipAwait": "true"},
        },
        spec={
            "replicas": 2,
            "selector": {"matchLabels": sandbox_router_labels},
            "template": {
                "metadata": {"labels": sandbox_router_labels},
                "spec": {
                    "serviceAccountName": sandbox_router_ksa.metadata["name"],
                    "nodeSelector": {"cloud.google.com/gke-nodepool": "system-node-pool"},
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
                            "image": sandbox_router_image,
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
            depends_on=[system_node_pool, sandbox_router_service, sandbox_router_ksa, sandbox_router_rolebinding],
            custom_timeouts=pulumi.CustomTimeouts(create="30s", update="30s"),
        ),
    )

    sandbox_router_pdb = kubernetes.policy.v1.PodDisruptionBudget(
        "sandbox-router-pdb",
        metadata={
            "name": "sandbox-router-pdb",
            "namespace": workloads_ns.metadata["name"],
        },
        spec={
            "minAvailable": 1,
            "selector": {"matchLabels": sandbox_router_labels},
        },
        opts=pulumi.ResourceOptions(depends_on=[sandbox_router_deployment]),
    )

    return RouterResult(
        deployment=sandbox_router_deployment,
        service=sandbox_router_service,
    )

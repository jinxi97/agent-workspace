# Agent Workspace on GKE with Pulumi

Infrastructure-as-code for provisioning agent workspace environments on GKE, including sandbox controllers, warm pools, and a FastAPI workspace API.

## Project structure

```
├── __main__.py                        # Orchestrator — wires components together
├── components/
│   ├── helpers.py                     # Shared utilities (required_env, int_env)
│   ├── cluster.py                     # GKE cluster + node pools
│   ├── sandbox_controller.py          # Agent-sandbox CRDs, snapshot infra, GCS, IAM
│   ├── workspace_api.py               # FastAPI deployment, ingress, certs, Cloud Build
│   ├── router.py                      # Sandbox router deployment, service, RBAC
│   ├── python_sandbox_warmpool.py     # Python runtime sandbox template + warm pool
│   └── claude_agent_warmpool.py       # Claude agent sandbox template + warm pool
├── tests/
│   ├── conftest.py                    # Shared Pulumi mock setup
│   ├── test_cluster.py                # Cluster component tests
│   └── test_sandbox_controller.py     # Sandbox controller component tests
├── image_source/                      # Container image build contexts
├── Pulumi.yaml                        # Pulumi project definition
├── Pulumi.dev.yaml                    # Dev stack configuration
└── cloudbuild.yaml                    # Cloud Build pipeline
```

## What this stack creates

| Component | Resources |
|---|---|
| **Cluster** | Standard GKE cluster, system node pool, gVisor-enabled agent node pool |
| **Sandbox controller** | Agent-sandbox CRDs (manifest + extensions), GCS snapshot bucket, PodSnapshotStorageConfig, snapshot namespace/KSA, IAM bindings |
| **Workspace API** | FastAPI Deployment, Service, Ingress with managed cert, static IP, Cloud Build trigger + SA |
| **Router** | Sandbox router Deployment, ClusterIP Service, RBAC |
| **Python sandbox warm pool** | SandboxTemplate + SandboxWarmPool for Python runtime |
| **Claude agent warm pool** | SandboxTemplate + SandboxWarmPool for Claude agent |

## Prerequisites

- Pulumi CLI installed and logged in
- `gcloud` CLI installed and authenticated
- Python 3.13+
- `uv` installed

## Configuration

Set `gcp:project` in Pulumi stack config (already present in `Pulumi.dev.yaml`), and use `.env` for runtime variables.

1. Create `.env`:

```bash
cp .env.example .env
```

2. Ensure `.env` contains at least:

```bash
CLUSTER_NAME="agent-workspace-cluster"
GKE_LOCATION="us-central1"
GKE_VERSION="1.35.0-gke.1795000"
MACHINE_TYPE="n2-standard-2"
NODE_POOL_NAME="agent-sandbox-node-pool"
AGENT_SANDBOX_VERSION="v0.1.0"
SNAPSHOTS_BUCKET_NAME_PREFIX="snapshots-"
SNAPSHOT_FOLDER="snapshots/v1"
SNAPSHOT_NAMESPACE="snapshot-ns"
SNAPSHOT_KSA_NAME="snapshot-ksa"
SANDBOX_TEMPLATE_REVISION="1"
CLAUDE_AGENT_SANDBOX_TEMPLATE_REVISION="1"
SANDBOX_ROUTER_IMAGE="us-central1-docker.pkg.dev/..."
WORKLOADS_NAMESPACE="agent-sandbox-application"
FASTAPI_APP_NAME="agent-workspace-api"
CLOUDBUILD_FILE="cloudbuild.yaml"
CLOUDBUILD_BRANCH_NAME="^main$"
CLOUDBUILD_LOCATION="us-central1"
CLOUDBUILD_REPOSITORY="..."
```

Notes:
- `__main__.py` calls `load_dotenv()`, so Pulumi reads `.env` when evaluating the Python program.
- `GKE_VERSION` sets the **minimum** cluster control plane version (`min_master_version`). Node pool versions are managed by GKE auto-upgrade.

## Deploy

1. Retrieve cluster credentials (required because Kubernetes resources are applied via the default kubeconfig-based provider):

```bash
gcloud container clusters get-credentials "${CLUSTER_NAME}" --location="${GKE_LOCATION}"
```

2. Deploy:

```bash
pulumi up
```

## Tests

Unit tests use Pulumi's mock framework to verify resource configuration without calling any cloud APIs.

```bash
# Install dev dependencies
uv sync --group dev

# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_cluster.py -v
```

## Destroy

To remove managed resources:

```bash
pulumi destroy
```

If desired, remove stack metadata too:

```bash
pulumi stack rm dev
```

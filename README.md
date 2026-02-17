# Agent Sandbox on GKE with Pulumi

This project provisions a Standard GKE cluster for Agent Sandbox and deploys the Agent Sandbox controller manifests.

## What this stack creates

- A Standard GKE cluster (`pulumi_gcp.container.Cluster`)
- A dedicated node pool with gVisor enabled (`pulumi_gcp.container.NodePool`)
- Agent Sandbox controller manifests from GitHub release URLs (`pulumi_kubernetes.yaml.ConfigFile`)
  - `manifest.yaml`
  - `extensions.yaml`

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
```

Notes:
- `__main__.py` calls `load_dotenv()`, so Pulumi reads `.env` when evaluating the Python program.
- `PROJECT_ID` can be set in `.env`, but this program currently uses `gcp:project` from Pulumi config for the workload pool.

## Deploy

1. Load `.env` into shell:

```bash
set -a; source .env; set +a
```

2. Retrieve cluster credentials (required because Kubernetes manifests are applied via the default kubeconfig-based provider):

```bash
gcloud container clusters get-credentials "${CLUSTER_NAME}" --location="${GKE_LOCATION}"
```

3. Deploy:

```bash
pulumi up
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

## Outputs

- `project_id`
- `region`
- `cluster_name`
- `node_pool_name`
- `agent_sandbox_version`

# Helm Export + Ansible for Demo Deployment

Helm export and Ansible-based deployment for **ephemeral demo environments** (e.g., conference demos) — easily stood up and torn down, namespace-scoped. For production with real ServiceNow/Slack credentials, use `helm-install-test` or `helm-install-prod` directly.

**Alternative:** If you prefer Helm-only (no Ansible), use `make helm-install-demo NAMESPACE=ssa-demo` or `make install NAMESPACE=ssa-demo INSTALL_MODE=demo` — applies Greenmail, installs with demo values, waits for all workloads. Use `make uninstall` to remove.

## When to Use Ansible vs Helm

Both `helm-install-demo` and `ansible-apply-demo` deploy the same demo stack. Choose based on your workflow:

| Use **ansible-apply-demo** when… | Use **helm-install-demo** when… |
|---------------------------------|--------------------------------|
| Export and apply are separate steps (e.g. CI exports manifests, another system applies them) | You want a single-command install with Helm managing the release |
| The target cluster has no Helm or Helm is restricted | You use Helm for day-to-day management and want `helm upgrade`, `helm rollback`, `helm history` |
| You prefer GitOps with plain YAML (no Helm release in cluster) | You're doing local dev, CI, or ad-hoc demos with standard tooling |
| Ansible is already your automation standard and you can extend the playbook (multi-cluster, pre/post steps) | You want fewer dependencies (no Ansible) |
| You need to apply from a bastion or different host than where manifests are generated | You're fine running everything from the repo with direct cluster access |

**Technical difference:** `helm-install-demo` uses `helm upgrade --install` (Helm release, lifecycle managed by Helm). `ansible-apply-demo` uses `helm template` to render YAML, then `kubectl apply` — no Helm release, just raw manifests.

## Quick Start

Set LLM config (same as regular installs). For a remote LLM: `LLM`, `LLM_ID`, `LLM_URL`, and `LLM_API_TOKEN` if required. For local/huggingface models: `HF_TOKEN`.

```bash
export NAMESPACE=ssa-demo
export LLM=llama-3-3-70b-instruct-w8a8
export LLM_ID=llama-3-3-70b-instruct-w8a8
export LLM_URL=https://your-llm-endpoint
export LLM_API_TOKEN=your-api-token   # if required by your endpoint
# Or for local models: export HF_TOKEN=...

# Deploy demo (export + apply)
make ansible-apply-demo NAMESPACE=$NAMESPACE

# Teardown
make ansible-teardown-demo NAMESPACE=$NAMESPACE
```

## Export Then Run Ansible Directly

To export first and run Ansible separately (e.g., to inspect manifests or run from another host). Ensure LLM env vars are set (see Quick Start) before exporting.

```bash
# 1. Export manifests (LLM env vars must be set)
make helm-export-demo NAMESPACE=ssa-demo

# 2. Run Ansible from repo root
ansible-playbook -i localhost, ansible/playbooks/apply-demo-manifests.yml \
  -e "target_namespace=ssa-demo" \
  -e "helm_export_dir=ansible/helm-export"
```

**Important:** Run `ansible-playbook` from the **repo root** so file paths resolve correctly.

## Targets

| Target | Description |
|--------|-------------|
| **install** | Deploy to cluster (alias for `helm-install-$(INSTALL_MODE)`, default: test). Use `INSTALL_MODE=demo|prod` to change. |
| **uninstall** | `helm-uninstall` + delete namespace (full teardown). |
| **helm-install-demo** | Helm-only: deploy Greenmail + install with demo values (no Ansible). Use `uninstall` to remove (includes test-email-server). |
| **helm-install-ticketing** | One-shot: deploy Zammad + install with ticketing channel (zammad.enabled, zammad-mcp). Requires manual API token creation after Zammad is ready. See [TICKETING_CHANNEL_GAMEPLAN.md](TICKETING_CHANNEL_GAMEPLAN.md). |
| **helm-export-demo** | Export demo manifests to `ansible/helm-export/` from passed-in vars (NAMESPACE, VERSION, REGISTRY, SERVICENOW_*, etc.) |
| **ansible-apply-demo** | Export then apply demo via Ansible |
| **ansible-teardown-demo** | Delete demo namespace |
| **helm-export-validate-demo** | Export then validate with kubeconform (no cluster required; used in CI) |

## Export variables

The export is generated from Makefile variables. Key vars that flow into the manifests:

| Variable | Purpose |
|----------|---------|
| `NAMESPACE` | Required. Used in metadata, email hostnames (e.g. `test-email-server-smtp.$(NAMESPACE).svc.cluster.local`), ServiceNow secret |
| `VERSION` | Image tags |
| `REGISTRY` | Image registry |
| `SERVICENOW_INSTANCE_URL` | Mock default: `http://self-service-agent-mock-servicenow:8080` |
| `SERVICENOW_API_KEY` | Mock default: `now_mock_api_key` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DBNAME` | pgvector config |
| `LLM`, `LLM_ID`, `LLM_URL`, `LLM_API_TOKEN` | Remote LLM config; or `HF_TOKEN` for local/huggingface models (same as `helm-install-test`) |

Override any at export time, e.g. `make helm-export-demo NAMESPACE=my-demo VERSION=0.0.12`.

## Demo Configuration

- Temp email server (Greenmail) for email-based demos
- Defaults: mock eventing, mock ServiceNow, no Slack. Override with `ENABLE_SLACK`, `SERVICENOW_INSTANCE_URL`, or `EXTRA_HELM_ARGS` if needed.
- Mock/default credentials (e.g. `now_mock_api_key`, `rag_password`) baked into export
- Exported YAML is self-contained — Ansible applies manifests only, no separate secret creation

## Prerequisites

- `kubectl` configured for your cluster (for apply)
- `ansible` (core) for apply/teardown playbooks
- `helm` for export
- `kubeconform` for helm-export-validate-demo (e.g. `brew install kubeconform`)
- LLM config: `LLM`, `LLM_ID`, `LLM_URL`, `LLM_API_TOKEN` (if needed) for remote LLM; or `HF_TOKEN` for local/huggingface models — same as `helm-install-test`

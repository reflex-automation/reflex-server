# Reflex Server

The API server for Reflex, a community-maintained fork of
Event-Driven Ansible (EDA) that targets open-source AWX-compatible
controllers, mainly [CIQ Ascender](https://ciq.com/products/ascender).

Red Hat actively develops
[ansible/eda-server](https://github.com/ansible/eda-server). Reflex tracks
it as a friendly fork: the patch set stays small, upstream merges happen
regularly, CVEs get patched, and fixes get offered upstream where they
fit.

## What Reflex adds

- Standalone deployments work out of the box. Upstream defaults
  `RESOURCE_SERVER__URL` to an AAP gateway mode that silently breaks
  session login; Reflex defaults it to empty.
- Releases are smoke-tested end to end against Ascender: a
  webhook-triggered rulebook activation launches a job template via
  `run_job_template`.
- Images are published at `ghcr.io/reflex-automation/reflex-server`.
- Image builds work behind firewalls and under emulation. GitHub host keys
  are baked in instead of running `ssh-keyscan` at build time.
- `suggest_only` activations. Rules still evaluate and show up in the rule
  audit, but `run_job_template`, `run_workflow_template`, `run_playbook` and
  `run_module` actions are swapped for a debug message before the rulebook
  reaches the worker. Use it to dry-run a new rulebook against live events
  without touching the controller. Set `suggest_only` while the activation
  is disabled; updates to an enabled or running activation are rejected.
- Prometheus metrics at `GET /api/eda/v1/metrics/`: activation status and
  restarts, event stream counters, audit rule and action counts by status,
  and activation request queue depth. Authenticate as a superuser, or send
  `Authorization: Bearer <token>` with the token set in `EDA_METRICS_TOKEN`.
  An upstream PR for this
  ([#1614](https://github.com/ansible/eda-server/pull/1614)) was closed
  without merging.
- Project push webhook. Set an event stream credential of type GitHub,
  GitLab, HMAC or Token as the project's webhook credential, then point the
  git host at `/api/eda/v1/external_project/<webhook_uuid>/post/`. A push to
  the project's branch syncs the project. Pushes to other branches, branch
  deletes and pings don't sync. Every pre-auth failure returns the same 403.

Internal identifiers (the `aap_eda` Python package, `/api/eda/v1` API
paths, `EDA_*` settings) keep their upstream names so merges stay clean.

## Deployment

Deploy on Kubernetes with
[reflex-operator](https://github.com/reflex-automation/reflex-operator).
The related projects:

| Repo | Role |
|---|---|
| [reflex-operator](https://github.com/reflex-automation/reflex-operator) | K8s operator deploying the stack |
| [reflex-ui](https://github.com/reflex-automation/reflex-ui) | Web UI |
| [reflex-decision-environment](https://github.com/reflex-automation/reflex-decision-environment) | Container image activations run in |

For development and non-k8s deployment, upstream's docs still apply:
[deployment guide](docs/deployment.md), [development guide](docs/development.md).

## OpenAPI

From a running instance: API docs at `/api/eda/v1/docs/`, schema at
`/api/eda/v1/openapi.json`.

## License and attribution

Apache-2.0, unchanged from upstream; see [LICENSE](LICENSE).
Based on [ansible/eda-server](https://github.com/ansible/eda-server),
© Red Hat, Inc. and contributors. Reflex is a community project and is not
affiliated with or endorsed by Red Hat. "Ansible" is a trademark of
Red Hat, Inc.

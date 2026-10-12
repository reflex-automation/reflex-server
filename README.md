# Reflex Server

The API server for Reflex, a close-tracking fork of Event-Driven Ansible
(EDA) for standalone use with open-source AWX-compatible controllers, mainly
[CIQ Ascender](https://ciq.com/products/ascender).

[ansible/eda-server](https://github.com/ansible/eda-server) is actively
developed in public by Red Hat. Reflex adds what upstream does
not carry by default, such as standalone login (see below), plus a
user-facing rebrand, published images and end-to-end smoke tests against
Ascender. It is a friendly fork: the patch set stays small, upstream merges
happen regularly, CVEs get patched, and fixes get offered upstream where
they fit.

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
- SSO login through OIDC, Keycloak, GitHub, Azure AD and Google:
  [docs/sso.md](docs/sso.md).
- Prometheus metrics at `/api/eda/v1/metrics/`: [docs/metrics.md](docs/metrics.md).
- Push webhook that syncs a project from GitHub or GitLab:
  [docs/project-webhook.md](docs/project-webhook.md).
- Suggest-only activations: set `suggest_only` on an activation and its
  `run_job_template`, `run_workflow_template`, `run_playbook` and `run_module`
  actions are replaced with a `debug` action that logs what would have run
  (`suggest_only: would run_job_template <name>`). Other actions still run.
  The flag can only be changed while the activation is disabled, and the
  activation still needs its controller credentials to start.

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

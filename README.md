# Reflex Server

The API server for **Reflex** — a community-maintained continuation of
Event-Driven Ansible (EDA), kept working against open-source AWX-compatible
controllers, primarily [CIQ Ascender](https://ciq.com/products/ascender).

Red Hat stopped developing EDA as a supported open-source product; the code
lives on as the internal upstream of Ansible Automation Platform. Reflex
tracks that upstream ([ansible/eda-server](https://github.com/ansible/eda-server))
as a friendly fork: small patch set, regular merges, fixes offered upstream
where they fit.

## What Reflex adds

- **Standalone deployments work out of the box** — `RESOURCE_SERVER__URL`
  defaults to empty, so session/UI login works without an AAP gateway
  (upstream's default silently switches auth to JWT-only).
- **Tested against Ascender** — releases are smoke-tested end-to-end: a
  webhook-triggered rulebook activation launching a job template on
  Ascender via `run_job_template`.
- **Published images** — `ghcr.io/reflex-automation/reflex-server`.
- **Firewall/emulation-proof image builds** — GitHub host keys are baked
  into the build instead of `ssh-keyscan` at build time.

Internal identifiers (the `aap_eda` Python package, `/api/eda/v1` API paths,
`EDA_*` settings) deliberately keep their upstream names so merges stay clean.

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

Apache-2.0, unchanged from upstream — see [LICENSE](LICENSE).
Based on [ansible/eda-server](https://github.com/ansible/eda-server),
© Red Hat, Inc. and contributors. Reflex is a community project and is not
affiliated with or endorsed by Red Hat. "Ansible" is a trademark of
Red Hat, Inc.

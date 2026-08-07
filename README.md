# Reflex Server

The API server for Reflex, a community-maintained continuation of
Event-Driven Ansible (EDA) that targets open-source AWX-compatible
controllers, mainly [CIQ Ascender](https://ciq.com/products/ascender).

Red Hat stopped developing EDA as a supported open-source product and now
uses the code as the internal upstream of Ansible Automation Platform.
Reflex tracks [ansible/eda-server](https://github.com/ansible/eda-server)
as a friendly fork: the patch set stays small, merges happen regularly,
and fixes get offered upstream where they fit.

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

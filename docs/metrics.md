# Metrics

`GET /api/eda/v1/metrics/` returns Prometheus text format (version 0.0.4).

## Auth

Either:

- a superuser (basic auth or session), or
- a static bearer token: set `EDA_METRICS_TOKEN` and send
  `Authorization: Bearer <token>`.

The token is off by default. Nothing else is accepted, including non-superuser
accounts.

On Kubernetes, reflex-operator has no secret reference for it. The only way in
is `extra_settings` on the EDA custom resource, which ends up in the
`<name>-eda-env-properties` ConfigMap in plain text:

```yaml
spec:
  extra_settings:
    - setting: EDA_METRICS_TOKEN
      value: change-me
```

Anyone who can read ConfigMaps in the namespace can read the token. If that
matters, use a superuser with basic auth instead. Outside the operator, set
`EDA_METRICS_TOKEN` as a normal environment variable on the API container.

## Metrics

| Name | Type | Labels |
|---|---|---|
| `eda_activation_status` | gauge, always 1 | `id`, `name`, `status`, `enabled` |
| `eda_activation_restarts` | gauge | `id`, `name` |
| `eda_activation_request_queue_depth` | gauge | none |
| `eda_event_stream_events_received_total` | counter | `name` |
| `eda_event_stream_last_event_timestamp_seconds` | gauge | `name` |
| `eda_audit_rules` | gauge | `status` |
| `eda_audit_actions` | gauge | `status` |

`enabled` is `"true"` or `"false"`. The last-event series is missing for a
stream that has never received an event.

## Scrape config

```yaml
scrape_configs:
  - job_name: reflex
    metrics_path: /api/eda/v1/metrics/
    scheme: https
    authorization:
      credentials: change-me
    static_configs:
      - targets: [reflex.example.com]
```

## Alert

Activations that are enabled but not running:

```yaml
- alert: ReflexActivationNotRunning
  expr: eda_activation_status{enabled="true", status!="running"} == 1
  for: 10m
  annotations:
    summary: "Activation {{ $labels.name }} is {{ $labels.status }}"
```

## Gotchas

- The audit counts come from a full scan of the audit tables on every scrape.
  Scrape every minute or so, not every few seconds, and watch it if the audit
  tables get large.
- Activation series are one per activation and carry `status` as a label, so a
  status change starts a new series.

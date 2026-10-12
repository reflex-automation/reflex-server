# Project push webhook

A git host can call Reflex on every push to sync the project, instead of
waiting for someone to click sync.

## Enable

1. Create a credential of type HMAC Event Stream, Token Event Stream,
   GitHub Event Stream or GitLab Event Stream. Other types are rejected.
2. Set it as `webhook_credential_id` on the project (create or update). Set it
   to null to turn the webhook off.
3. Read the project. `webhook_path` is
   `/api/eda/v1/external_project/<uuid>/post/`. The uuid is generated per
   project; the path is null while no credential is set.

The caller needs permission to use the credential.

## GitHub

Repo settings, Webhooks, Add webhook:

- Payload URL: `https://<eda-host>/api/eda/v1/external_project/<uuid>/post/`
- Content type: `application/json`
- Secret: the secret from the credential
- Events: just the push event

Use a GitHub Event Stream credential (SHA-256 HMAC in `X-Hub-Signature-256`).
GitHub's ping on creation gets `{"message": "pong"}`.

## GitLab

Settings, Webhooks:

- URL: same as above
- Secret token: the token from the credential
- Trigger: push events

Use a GitLab Event Stream credential (token in `X-Gitlab-Token`).

## Which pushes sync

- GitHub events other than `push`, and GitLab events other than `Push Hook`,
  are ignored (GitLab tag push hooks do nothing).
- Branch deletes are ignored.
- If the project has `scm_branch`, only pushes to that branch (or a tag of the
  same name) sync. With no
  `scm_branch`, the repository's default branch from the payload is used.
  If neither is known, any push syncs.

## Responses

| Code | Body | Meaning |
|---|---|---|
| 202 | `{"status": "queued"}` | sync queued |
| 202 | `{"status": "already_running"}` | project is already pending or syncing |
| 200 | `{"ignored": true}` | valid request, nothing to do |
| 200 | `{"message": "pong"}` | GitHub ping |
| 400 | | body is not a JSON object |
| 403 | `{"detail": "Authentication failed"}` | unknown uuid, no credential, or bad signature or token |
| 503 | | no default worker is healthy |

Every pre-auth failure returns the same 403 so uuids can't be probed.

## Restarting activations

A sync alone does not restart anything. Set `restart_on_project_update` on an
activation and, after a sync, it restarts if it is enabled and its rulebook
changed, or if it is in a failed or error state.

## Gotchas

- The body must be JSON. GitHub's form-encoded content type does not work.
- An empty secret or token in the credential always fails with 403.
- Use HTTPS; the secret protects the request, but a replayed signed body would
  just queue another sync.

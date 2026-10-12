import hashlib
import hmac
import json
import uuid
from unittest import mock

import pytest
from ansible_base.rbac import permission_registry
from ansible_base.rbac.models import DABPermission, RoleDefinition
from rest_framework import status
from rest_framework.test import APIClient

from aap_eda.core import enums, models
from aap_eda.core.utils.credentials import inputs_to_store
from tests.integration.constants import api_url_v1

SECRET = "s3cret"
JOB_ID = "46e289a7-9dcc-4baa-a49a-a6ca756d9b71"
FORBIDDEN = {"detail": "Authentication failed"}
SYNC = "aap_eda.api.views.external_project.tasks.sync_project"
HEALTH = "aap_eda.api.views.external_project.check_default_worker_health"


def _credential(org, type_name, inputs, name="wh-cred"):
    return models.EdaCredential.objects.create(
        name=name,
        credential_type=models.CredentialType.objects.get(name=type_name),
        inputs=inputs_to_store(inputs),
        organization=org,
    )


def _hmac_inputs(**kw):
    return {
        "auth_type": "hmac",
        "secret": SECRET,
        "hash_algorithm": "sha256",
        "http_header_key": "X-Hub-Signature-256",
        "signature_encoding": "hex",
        "signature_prefix": "sha256=",
        **kw,
    }


@pytest.fixture
def hmac_project(default_organization, preseed_credential_types):
    cred = _credential(
        default_organization,
        enums.EventStreamCredentialType.HMAC,
        _hmac_inputs(),
    )
    return models.Project.objects.create(
        name="wh-project",
        url="https://git.example.com/acme/p",
        organization=default_organization,
        webhook_credential=cred,
        scm_branch="main",
        import_state=models.Project.ImportState.COMPLETED,
    )


@pytest.fixture
def sync_mock():
    with mock.patch(SYNC, return_value=JOB_ID) as m, mock.patch(
        HEALTH, return_value=True
    ):
        yield m


def url_for(project_or_uuid):
    wid = getattr(project_or_uuid, "webhook_uuid", project_or_uuid)
    return f"{api_url_v1}/external_project/{wid}/post/"


def sign(body: bytes, secret=SECRET):
    return (
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    )


def post_push(
    project,
    payload=None,
    event="push",
    client=None,
    signature=None,
    raw=None,
    headers=None,
):
    body = raw if raw is not None else json.dumps(payload or {}).encode()
    hdrs = {"X-GitHub-Event": event} if event else {}
    hdrs["X-Hub-Signature-256"] = signature or sign(body)
    hdrs.update(headers or {})
    return (client or APIClient()).post(
        url_for(project),
        data=body,
        content_type="application/json",
        headers=hdrs,
    )


@pytest.mark.django_db
def test_github_hmac_push_queues_sync(hmac_project, sync_mock):
    response = post_push(hmac_project, {"ref": "refs/heads/main"})
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json() == {"status": "queued"}
    sync_mock.assert_called_once_with(hmac_project.id)
    hmac_project.refresh_from_db()
    assert hmac_project.import_state == models.Project.ImportState.PENDING
    assert hmac_project.import_task_id == uuid.UUID(JOB_ID)


@pytest.mark.django_db
def test_gitlab_token_push_hook(hmac_project, default_organization, sync_mock):
    hmac_project.webhook_credential = _credential(
        default_organization,
        enums.EventStreamCredentialType.TOKEN,
        {
            "auth_type": "token",
            "token": SECRET,
            "http_header_key": "X-Gitlab-Token",
        },
        name="tok",
    )
    hmac_project.save()
    response = APIClient().post(
        url_for(hmac_project),
        data={"ref": "refs/heads/main"},
        format="json",
        headers={"X-Gitlab-Token": SECRET, "X-Gitlab-Event": "Push Hook"},
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    sync_mock.assert_called_once()

    response = APIClient().post(
        url_for(hmac_project),
        data={"ref": "refs/tags/main"},
        format="json",
        headers={"X-Gitlab-Token": SECRET, "X-Gitlab-Event": "Tag Push Hook"},
    )
    assert response.json() == {"ignored": True}
    sync_mock.assert_called_once()


@pytest.mark.django_db
def test_pre_auth_failures_are_uniform_403(
    hmac_project, default_organization, sync_mock
):
    no_cred = models.Project.objects.create(
        name="no-cred",
        url="https://git.example.com/acme/q",
        organization=default_organization,
    )
    body = json.dumps({}).encode()
    cases = [
        post_push(hmac_project, signature="sha256=bad"),
        post_push(hmac_project, signature="sha256=" + "0" * 64),
        APIClient().post(
            url_for(hmac_project), data=body, content_type="application/json"
        ),
        post_push(uuid.uuid4()),
        APIClient().post(
            f"{api_url_v1}/external_project/not-a-uuid/post/",
            data=body,
            content_type="application/json",
        ),
        post_push(no_cred),
    ]
    for response in cases:
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == FORBIDDEN
    sync_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["Bearer", "Bearer ", ""])
def test_bearer_without_token_is_403(
    hmac_project, default_organization, sync_mock, value
):
    hmac_project.webhook_credential = _credential(
        default_organization,
        enums.EventStreamCredentialType.TOKEN,
        {"auth_type": "token", "token": SECRET, "http_header_key": "X-Tok"},
        name="tok",
    )
    hmac_project.save()
    response = APIClient().post(
        url_for(hmac_project),
        data=b"[]",
        content_type="application/json",
        headers={"X-Tok": value},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == FORBIDDEN


@pytest.mark.django_db
def test_empty_secret_is_403(hmac_project, default_organization, sync_mock):
    hmac_project.webhook_credential = _credential(
        default_organization,
        enums.EventStreamCredentialType.HMAC,
        _hmac_inputs(secret=""),
        name="empty",
    )
    hmac_project.save()
    body = json.dumps({}).encode()
    response = post_push(hmac_project, raw=body, signature=sign(body, ""))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == FORBIDDEN
    sync_mock.assert_not_called()


@pytest.mark.django_db
def test_ping_returns_pong(hmac_project, sync_mock):
    response = post_push(hmac_project, event="ping")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "pong"}
    sync_mock.assert_not_called()


@pytest.mark.django_db
def test_other_branch_ignored(hmac_project, sync_mock):
    response = post_push(hmac_project, {"ref": "refs/heads/dev"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"ignored": True}
    sync_mock.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"ref": "refs/heads/main", "deleted": True},
        {"ref": "refs/heads/main", "after": "0" * 40},
    ],
)
def test_branch_delete_ignored(hmac_project, sync_mock, payload):
    response = post_push(hmac_project, payload)
    assert response.json() == {"ignored": True}
    sync_mock.assert_not_called()


@pytest.mark.django_db
def test_tag_ref_matches_only_when_scm_branch_names_tag(
    hmac_project, sync_mock
):
    assert post_push(hmac_project, {"ref": "refs/tags/v1"}).json() == {
        "ignored": True
    }
    sync_mock.assert_not_called()

    hmac_project.scm_branch = "v1"
    hmac_project.save()
    response = post_push(hmac_project, {"ref": "refs/tags/v1"})
    assert response.status_code == status.HTTP_202_ACCEPTED
    sync_mock.assert_called_once()


@pytest.mark.django_db
def test_empty_scm_branch_uses_payload_default_branch(hmac_project, sync_mock):
    hmac_project.scm_branch = ""
    hmac_project.save()
    payload = {
        "ref": "refs/heads/trunk",
        "repository": {"default_branch": "trunk"},
    }
    assert post_push(hmac_project, payload).status_code == 202
    sync_mock.assert_called_once()

    payload = {"ref": "refs/heads/dev", "project": {"default_branch": "trunk"}}
    assert post_push(hmac_project, payload).json() == {"ignored": True}
    sync_mock.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    [
        models.Project.ImportState.RUNNING,
        models.Project.ImportState.PENDING,
    ],
)
def test_already_running(hmac_project, sync_mock, state):
    hmac_project.import_state = state
    hmac_project.save()
    response = post_push(hmac_project, {"ref": "refs/heads/main"})
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json() == {"status": "already_running"}
    sync_mock.assert_not_called()


@pytest.mark.django_db
def test_workers_unavailable(hmac_project):
    with mock.patch(HEALTH, return_value=False), mock.patch(SYNC) as sync:
        response = post_push(hmac_project, {"ref": "refs/heads/main"})
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    sync.assert_not_called()


@pytest.mark.django_db
def test_non_json_body_after_auth_is_400(hmac_project, sync_mock):
    response = post_push(hmac_project, raw=b"payload=%7B%7D")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    sync_mock.assert_not_called()


@pytest.mark.django_db
def test_no_csrf_token_needed(hmac_project, sync_mock):
    client = APIClient(enforce_csrf_checks=True)
    response = post_push(
        hmac_project, {"ref": "refs/heads/main"}, client=client
    )
    assert response.status_code == status.HTTP_202_ACCEPTED


@pytest.mark.django_db
def test_generic_hmac_bare_hex_signature(
    hmac_project, default_organization, sync_mock
):
    hmac_project.webhook_credential = _credential(
        default_organization,
        enums.EventStreamCredentialType.HMAC,
        _hmac_inputs(http_header_key="X-Gitea-Signature", signature_prefix=""),
        name="gitea",
    )
    hmac_project.save()
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    response = APIClient().post(
        url_for(hmac_project),
        data=body,
        content_type="application/json",
        headers={"X-Gitea-Signature": sign(body).removeprefix("sha256=")},
    )
    assert response.status_code == status.HTTP_202_ACCEPTED


# credential assignment through the projects API


@pytest.fixture
def webhook_cred(default_organization, preseed_credential_types):
    return _credential(
        default_organization,
        enums.EventStreamCredentialType.HMAC,
        _hmac_inputs(),
    )


@pytest.mark.django_db
def test_set_webhook_credential_exposes_path(
    new_project, webhook_cred, superuser_client
):
    response = superuser_client.patch(
        f"{api_url_v1}/projects/{new_project.id}/",
        data={"webhook_credential_id": webhook_cred.id},
    )
    assert response.status_code == status.HTTP_200_OK
    new_project.refresh_from_db()
    assert new_project.webhook_credential_id == webhook_cred.id

    data = superuser_client.get(
        f"{api_url_v1}/projects/{new_project.id}/"
    ).json()
    assert data["webhook_credential"]["id"] == webhook_cred.id
    assert data["webhook_path"] == url_for(new_project)
    assert "webhook_uuid" not in data


@pytest.mark.django_db
def test_no_webhook_path_without_credential(new_project, superuser_client):
    data = superuser_client.get(
        f"{api_url_v1}/projects/{new_project.id}/"
    ).json()
    assert data["webhook_credential"] is None
    assert data["webhook_path"] is None


@pytest.mark.django_db
def test_webhook_credential_type_validation(
    new_project, default_scm_credential, default_organization, superuser_client
):
    response = superuser_client.patch(
        f"{api_url_v1}/projects/{new_project.id}/",
        data={"webhook_credential_id": default_scm_credential.id},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    ecdsa = _credential(
        default_organization,
        enums.EventStreamCredentialType.ECDSA,
        {"auth_type": "ecdsa"},
        name="ecdsa",
    )
    response = superuser_client.patch(
        f"{api_url_v1}/projects/{new_project.id}/",
        data={"webhook_credential_id": ecdsa.id},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_webhook_credential_requires_credential_use_permission(
    new_project, webhook_cred, default_user, user_client
):
    ctype = permission_registry.content_type_model.objects.get_for_model(
        new_project
    )
    role = RoleDefinition.objects.create(
        name="project-editor", content_type=ctype
    )
    role.permissions.add(
        *DABPermission.objects.filter(
            codename__in=["view_project", "change_project"]
        )
    )
    role.give_permission(default_user, new_project)

    response = user_client.patch(
        f"{api_url_v1}/projects/{new_project.id}/",
        data={"webhook_credential_id": webhook_cred.id},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    new_project.refresh_from_db()
    assert new_project.webhook_credential_id is None


@pytest.mark.django_db
def test_oversized_body_is_uniform_403(hmac_project, sync_mock):
    raw = b" " * (2_621_440 + 1)
    response = post_push(hmac_project, raw=raw)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Authentication failed"}


@pytest.mark.django_db
def test_bad_hash_algorithm_is_403(hmac_project, sync_mock):
    cred = hmac_project.webhook_credential
    cred.inputs = inputs_to_store(_hmac_inputs(hash_algorithm="sha1024"))
    cred.save()
    response = post_push(hmac_project, {"ref": "refs/heads/main"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_hostile_payloads_do_not_500(hmac_project, sync_mock):
    response = post_push(hmac_project, {"after": 5, "ref": "refs/heads/main"})
    assert response.status_code == status.HTTP_202_ACCEPTED
    response = post_push(hmac_project, raw=b"[" * 200000)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

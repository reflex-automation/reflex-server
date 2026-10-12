import base64
import uuid

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from aap_eda.api import metrics
from aap_eda.core import models
from tests.integration.constants import api_url_v1

URL = f"{api_url_v1}/metrics/"
JWT_CLASSES = [
    "ansible_base.jwt_consumer.eda.auth.EDAJWTAuthentication",
    "aap_eda.api.authentication.WebsocketJWTAuthentication",
]


def bearer(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_unauthenticated(base_client):
    r = base_client.get(URL)
    assert r.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_normal_user_forbidden(user_client):
    assert user_client.get(URL).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_superuser_ok(superuser_client):
    r = superuser_client.get(URL)
    assert r.status_code == status.HTTP_200_OK
    assert r["Content-Type"] == metrics.CONTENT_TYPE


@pytest.mark.django_db
def test_superuser_basic_auth(super_user):
    super_user.set_password("pw")
    super_user.save()
    client = APIClient()
    creds = base64.b64encode(f"{super_user.username}:pw".encode()).decode()
    client.credentials(HTTP_AUTHORIZATION=f"Basic {creds}")
    assert client.get(URL).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("jwt", [False, True])
@pytest.mark.django_db
def test_token_auth(base_client, settings, jwt):
    settings.METRICS_TOKEN = "s3cret"
    if jwt:
        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_AUTHENTICATION_CLASSES": JWT_CLASSES,
        }
    ok = base_client.get(URL, **bearer("s3cret"))
    assert ok.status_code == status.HTTP_200_OK
    assert ok["Content-Type"] == metrics.CONTENT_TYPE
    bad = base_client.get(URL, **bearer("nope"))
    assert bad.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize("token", [None, ""])
@pytest.mark.django_db
def test_token_unset_bearer_rejected(base_client, settings, token):
    settings.METRICS_TOKEN = token
    r = base_client.get(URL, **bearer(token or "anything"))
    assert r.status_code == status.HTTP_401_UNAUTHORIZED
    assert base_client.get(URL, **bearer("")).status_code != 200


@pytest.mark.django_db
def test_body_series(
    superuser_client,
    default_activation,
    default_event_stream,
    default_audit_rule,
    default_activation_instance,
):
    models.EventStream.objects.filter(pk=default_event_stream.pk).update(
        events_received=7, last_event_received_at=timezone.now()
    )
    models.AuditAction.objects.create(
        id=uuid.uuid4(),
        name="debug",
        status="successful",
        fired_at=timezone.now(),
        audit_rule=default_audit_rule,
    )
    body = superuser_client.get(URL).content.decode()
    a = default_activation
    assert (
        f'eda_activation_status{{id="{a.id}",name="{a.name}",'
        f'status="{a.status}",enabled="{str(a.is_enabled).lower()}"}} 1'
    ) in body
    assert f'eda_activation_restarts{{id="{a.id}",name="{a.name}"}} 0' in body
    n = default_event_stream.name
    assert f'eda_event_stream_events_received_total{{name="{n}"}} 7' in body
    assert f'eda_event_stream_last_event_timestamp_seconds{{name="{n}"}}' in (
        body
    )
    assert 'eda_audit_rules{status=""} 1' in body
    assert 'eda_audit_actions{status="successful"} 1' in body
    assert "# TYPE eda_activation_request_queue_depth gauge" in body
    assert "eda_activation_request_queue_depth " in body


def test_label_escaping():
    out = metrics.render([("m", "gauge", "h", [({"a": 'x\\y"z\nw'}, 1)])])
    assert 'm{a="x\\\\y\\"z\\nw"} 1' in out

#  Copyright 2026 Reflex.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import pytest
from ansible_base.authentication.models import Authenticator
from rest_framework import status
from rest_framework.test import APIClient

from tests.integration.constants import api_url_v1

ui_auth_url = f"{api_url_v1}/ui_auth/"


@pytest.fixture
def local_authenticator(db):
    return Authenticator.objects.create(
        name="Local Database Authenticator",
        type="ansible_base.authentication.authenticator_plugins.local",
        enabled=True,
        create_objects=False,
        configuration={},
    )


@pytest.fixture
def oidc_authenticator(db):
    return Authenticator.objects.create(
        name="Test OIDC",
        type="ansible_base.authentication.authenticator_plugins.oidc",
        enabled=True,
        create_objects=True,
        configuration={
            "OIDC_ENDPOINT": "https://idp.example.com/realms/test",
            "KEY": "client-id",
            "SECRET": "client-secret",
        },
    )


@pytest.mark.django_db
def test_ui_auth_is_public(base_client: APIClient):
    response = base_client.get(ui_auth_url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_ui_auth_lists_authenticators(
    base_client: APIClient, local_authenticator, oidc_authenticator
):
    response = base_client.get(ui_auth_url)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["show_login_form"] is True
    assert [p["name"] for p in data["passwords"]] == [
        "Local Database Authenticator"
    ]
    assert len(data["ssos"]) == 1
    sso = data["ssos"][0]
    assert sso["name"] == "Test OIDC"
    assert sso["type"] == "oidc"
    assert sso["login_url"] == (
        f"/api/eda/social/login/{oidc_authenticator.slug}/"
    )


@pytest.mark.django_db
def test_ui_auth_excludes_disabled_authenticators(
    base_client: APIClient, oidc_authenticator
):
    oidc_authenticator.enabled = False
    oidc_authenticator.save()
    response = base_client.get(ui_auth_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["ssos"] == []


@pytest.mark.django_db
def test_authenticators_api_requires_auth(base_client: APIClient):
    response = base_client.get(f"{api_url_v1}/authenticators/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_authenticators_crud_as_superuser(
    superuser_client: APIClient, local_authenticator
):
    # local_authenticator present so delete succeeds: DAB refuses to
    # delete the last enabled authenticator
    response = superuser_client.post(
        f"{api_url_v1}/authenticators/",
        data={
            "name": "Corp OIDC",
            "type": "ansible_base.authentication.authenticator_plugins.oidc",
            "enabled": True,
            "create_objects": True,
            "configuration": {
                "OIDC_ENDPOINT": "https://idp.example.com/realms/corp",
                "KEY": "client-id",
                "SECRET": "client-secret",
            },
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    pk = response.data["id"]

    response = superuser_client.get(f"{api_url_v1}/authenticators/{pk}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Corp OIDC"

    response = superuser_client.delete(f"{api_url_v1}/authenticators/{pk}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT

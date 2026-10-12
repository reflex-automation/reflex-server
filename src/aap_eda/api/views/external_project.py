#  Copyright 2026 Red Hat, Inc.
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
"""Module providing the project push webhook."""

import json
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from aap_eda import tasks
from aap_eda.api.event_stream_authentication import (
    HMACAuthentication,
    TokenAuthentication,
)
from aap_eda.core.enums import Action, EventStreamAuthType, ResourceType
from aap_eda.core.exceptions import CredentialPluginError
from aap_eda.core.models import Project
from aap_eda.core.utils.credentials import get_resolved_secrets
from aap_eda.tasks.project import check_default_worker_health

logger = logging.getLogger(__name__)

# same body for every pre-auth failure so uuids can't be probed
AUTH_FAILED = {"detail": "Authentication failed"}


def _verify(request, inputs: dict) -> None:
    """Raise unless the request is signed with the credential's secret."""
    if inputs["auth_type"] == EventStreamAuthType.HMAC:
        if not inputs["secret"]:
            raise AuthenticationFailed()
        HMACAuthentication(
            signature_encoding=inputs["signature_encoding"],
            signature_prefix=inputs.get("signature_prefix", ""),
            signature=request.headers[inputs["http_header_key"]],
            hash_algorithm=inputs["hash_algorithm"],
            secret=inputs["secret"].encode("utf-8"),
        ).authenticate(request.body)
    elif inputs["auth_type"] == EventStreamAuthType.TOKEN:
        if not inputs["token"]:
            raise AuthenticationFailed()
        TokenAuthentication(
            token=inputs["token"],
            value=request.headers[inputs["http_header_key"]],
        ).authenticate()
    else:
        raise AuthenticationFailed()


def _nested(payload: dict, key: str, sub: str) -> str:
    value = payload.get(key)
    return value.get(sub) or "" if isinstance(value, dict) else ""


def _wants_sync(project: Project, request, payload: dict) -> bool:
    github_event = request.headers.get("X-GitHub-Event")
    gitlab_event = request.headers.get("X-Gitlab-Event")
    if github_event and github_event != "push":
        return False
    if gitlab_event and gitlab_event != "Push Hook":
        return False

    if payload.get("deleted") or (
        payload.get("after") and set(payload["after"]) == {"0"}
    ):
        return False

    want = (
        project.scm_branch
        or _nested(payload, "repository", "default_branch")
        or _nested(payload, "project", "default_branch")
    )
    ref = payload.get("ref")
    if not want or not ref:
        return True
    return ref in (f"refs/heads/{want}", f"refs/tags/{want}")


class ExternalProjectViewSet(viewsets.GenericViewSet):
    """Project push webhook."""

    rbac_action = None
    rbac_resource_type = ResourceType.PROJECT
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_rbac_permission(self):
        """RBAC Permissions."""
        return ResourceType.PROJECT, Action.READ

    @extend_schema(exclude=True)
    @action(detail=True, methods=["POST"], rbac_action=None)
    def post(self, request, *_args, **kwargs):
        """Handle push events from git hosts."""
        try:
            project = Project.objects.select_related("webhook_credential").get(
                webhook_uuid=kwargs["pk"]
            )
        except (Project.DoesNotExist, ValidationError):
            return Response(AUTH_FAILED, status=status.HTTP_403_FORBIDDEN)
        if project.webhook_credential is None:
            return Response(AUTH_FAILED, status=status.HTTP_403_FORBIDDEN)

        try:
            inputs = get_resolved_secrets(project.webhook_credential)
        except CredentialPluginError as err:
            logger.warning("Error fetching external secrets %s", str(err))
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            _verify(request, inputs)
        except (AuthenticationFailed, KeyError, IndexError):
            return Response(AUTH_FAILED, status=status.HTTP_403_FORBIDDEN)

        if request.headers.get("X-GitHub-Event") == "ping":
            return Response({"message": "pong"})

        try:
            payload = json.loads(request.body)
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            return Response(
                {"detail": "expected application/json"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _wants_sync(project, request, payload):
            return Response({"ignored": True})

        if not check_default_worker_health():
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        with transaction.atomic():
            project = Project.objects.select_for_update().get(pk=project.pk)
            if project.import_state in [
                Project.ImportState.PENDING,
                Project.ImportState.RUNNING,
            ]:
                return Response(
                    {"status": "already_running"},
                    status=status.HTTP_202_ACCEPTED,
                )
            job_id = tasks.sync_project(project.id)
            project.import_state = Project.ImportState.PENDING
            update_fields = ["import_state"]
            if job_id:
                project.import_task_id = job_id
                update_fields.append("import_task_id")
            project.save(update_fields=update_fields)

        logger.info(
            "Webhook sync of project %s (%s)", project.name, project.id
        )
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

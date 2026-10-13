import hmac

from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.authentication import (
    BaseAuthentication,
    BasicAuthentication,
)
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from aap_eda.api.authentication import SessionAuthentication
from aap_eda.core import models

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
TOKEN_OK = "metrics-token"


def _esc(v) -> str:
    return (
        str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )


def render(families) -> str:
    """Render (name, type, help, [(labels, value)]) families."""
    out = []
    for name, typ, help_, samples in families:
        out += [f"# HELP {name} {help_}", f"# TYPE {name} {typ}"]
        for labels, value in samples:
            lbl = ",".join(f'{k}="{_esc(v)}"' for k, v in labels.items())
            out.append(
                f"{name}{{{lbl}}} {value}" if lbl else f"{name} {value}"
            )
    return "\n".join(out) + "\n"


def collect():
    acts = list(
        models.Activation.objects.values_list(
            "id", "name", "status", "is_enabled", "restart_count"
        )
    )
    streams = list(
        models.EventStream.objects.values_list(
            "name", "events_received", "last_event_received_at"
        )
    )
    # ponytail: seq scan of audit tables per scrape; add a fired_at window
    # or a short cache if these grow large
    rules = models.AuditRule.objects.order_by().values("status")
    actions = models.AuditAction.objects.order_by().values("status")
    by_status = lambda qs: [  # noqa: E731
        ({"status": r["status"]}, r["n"]) for r in qs.annotate(n=Count("*"))
    ]
    return [
        (
            "eda_activation_status",
            "gauge",
            "Activation status, one series per activation.",
            [
                (
                    {
                        "id": i,
                        "name": n,
                        "status": s,
                        "enabled": str(e).lower(),
                    },
                    1,
                )
                for i, n, s, e, _ in acts
            ],
        ),
        (
            "eda_activation_restarts",
            "gauge",
            "Activation restart count.",
            [({"id": i, "name": n}, r) for i, n, _, _, r in acts],
        ),
        (
            "eda_event_stream_events_received_total",
            "counter",
            "Events received by an event stream.",
            [({"name": n}, c) for n, c, _ in streams],
        ),
        (
            "eda_event_stream_last_event_timestamp_seconds",
            "gauge",
            "Unix time of the last event received by an event stream.",
            [({"name": n}, t.timestamp()) for n, _, t in streams if t],
        ),
        (
            "eda_audit_rules",
            "gauge",
            "Audit rules by status.",
            by_status(rules),
        ),
        (
            "eda_audit_actions",
            "gauge",
            "Audit actions by status.",
            by_status(actions),
        ),
        (
            "eda_activation_request_queue_depth",
            "gauge",
            "Pending activation requests.",
            [({}, models.ActivationRequestQueue.objects.count())],
        ),
    ]


class MetricsTokenAuthentication(BaseAuthentication):
    """Static bearer token, checked before JWT auth can reject it."""

    def authenticate(self, request):
        token = getattr(settings, "METRICS_TOKEN", None)
        parts = request.META.get("HTTP_AUTHORIZATION", "").split()
        if (
            token
            and len(parts) == 2
            and parts[0].lower() == "bearer"
            and hmac.compare_digest(parts[1].encode(), token.encode())
        ):
            return None, TOKEN_OK
        return None

    def authenticate_header(self, request):
        return "Bearer"


class MetricsPermission(BasePermission):
    def has_permission(self, request, view):
        return request.auth == TOKEN_OK or bool(request.user.is_superuser)


class MetricsView(APIView):
    authentication_classes = [
        MetricsTokenAuthentication,
        SessionAuthentication,
        BasicAuthentication,
    ]
    permission_classes = [MetricsPermission]

    @extend_schema(exclude=True)
    def get(self, request):
        return HttpResponse(render(collect()), content_type=CONTENT_TYPE)

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.fixture
def rollback_migration():
    call_command("migrate", "core", "0077")
    yield
    call_command("migrate")


@pytest.mark.django_db(transaction=True)
def test_backfill_gives_unique_webhook_uuids(
    rollback_migration, default_organization
):
    state = MigrationExecutor(connection).loader.project_state(
        ("core", "0077_activation_suggest_only")
    )
    project_model = state.apps.get_model("core", "Project")
    ids = [
        project_model.objects.create(
            name=f"p{i}",
            url="https://git.example.com/a/b",
            organization_id=default_organization.id,
        ).pk
        for i in range(3)
    ]

    call_command("migrate", "core", "0078")

    from aap_eda.core import models

    uuids = set(
        models.Project.objects.filter(pk__in=ids).values_list(
            "webhook_uuid", flat=True
        )
    )
    assert len(uuids) == 3 and None not in uuids

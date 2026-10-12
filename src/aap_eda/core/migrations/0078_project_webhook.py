import uuid

import django.db.models.deletion
from django.db import migrations, models


def gen_uuids(apps, schema_editor):
    project_model = apps.get_model("core", "Project")
    for pk in project_model.objects.values_list("pk", flat=True):
        project_model.objects.filter(pk=pk).update(webhook_uuid=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0077_activation_suggest_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="webhook_credential",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)ss_webhook",
                to="core.edacredential",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="webhook_uuid",
            field=models.UUIDField(default=uuid.uuid4, null=True),
        ),
        migrations.RunPython(gen_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="webhook_uuid",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, unique=True
            ),
        ),
    ]

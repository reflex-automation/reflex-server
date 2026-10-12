from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0076_rulebookprocess_log_retention_checkpoint"),
    ]

    operations = [
        migrations.AddField(
            model_name="activation",
            name="suggest_only",
            field=models.BooleanField(
                default=False,
                help_text="Replace job template, workflow, playbook and module actions with a debug message instead of running them.",
            ),
        ),
    ]

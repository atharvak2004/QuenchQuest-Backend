"""Give Project.volunteers a through model (ProjectVolunteer) without rebuilding the table.

The existing many-to-many table (website_project_volunteers: id, project_id, user_id)
becomes ProjectVolunteer in Django's state only, so existing assignments are kept.
Then joined_by / joined_at columns are added; existing rows count as "added by staff".
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0018_admin_panel_auth"),
        ("website", "0005_programcards_to_services"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ProjectVolunteer",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("project", models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="memberships", to="website.project",
                        )),
                        ("volunteer", models.ForeignKey(
                            db_column="user_id", on_delete=django.db.models.deletion.CASCADE,
                            related_name="project_memberships", to="authentication.user",
                        )),
                    ],
                    options={
                        "db_table": "website_project_volunteers",
                        "unique_together": {("project", "volunteer")},
                    },
                ),
                migrations.AlterField(
                    model_name="project",
                    name="volunteers",
                    field=models.ManyToManyField(
                        blank=True, related_name="projects",
                        through="website.ProjectVolunteer", to="authentication.user",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="projectvolunteer",
            name="joined_by",
            field=models.CharField(
                choices=[("self", "Joined from the website"), ("staff", "Added by staff")],
                default="staff", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="projectvolunteer",
            name="joined_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="project",
            name="allow_volunteers",
            field=models.BooleanField(default=True),
        ),
    ]

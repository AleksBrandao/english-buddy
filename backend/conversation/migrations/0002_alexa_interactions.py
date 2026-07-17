# Generated manually for Alexa interaction logging

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversa",
            name="canal",
            field=models.CharField(
                choices=[("web", "Web"), ("alexa", "Alexa")],
                default="web",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="conversa",
            name="external_session_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="conversa",
            name="external_user_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="InteracaoAlexa",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("request_id", models.CharField(max_length=255, unique=True)),
                ("request_type", models.CharField(max_length=80)),
                ("intent_name", models.CharField(blank=True, default="", max_length=150)),
                ("slots", models.JSONField(blank=True, default=dict)),
                ("locale", models.CharField(blank=True, default="", max_length=20)),
                ("user_text", models.TextField(blank=True, default="")),
                ("assistant_text", models.TextField(blank=True, default="")),
                ("response_should_end_session", models.BooleanField(blank=True, null=True)),
                ("status_code", models.PositiveSmallIntegerField(default=200)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "conversa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interacoes_alexa",
                        to="conversation.conversa",
                    ),
                ),
            ],
            options={"ordering": ["-criado_em"]},
        ),
    ]

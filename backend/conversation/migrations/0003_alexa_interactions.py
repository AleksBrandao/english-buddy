# Generated manually for Alexa interaction persistence.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0002_sessaotreino_avaliacaosessao"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversa",
            name="origem",
            field=models.CharField(
                choices=[("web", "Web"), ("alexa", "Alexa")],
                db_index=True,
                default="web",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="conversa",
            name="alexa_session_id",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                unique=True,
            ),
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
                (
                    "request_type",
                    models.CharField(db_index=True, max_length=80),
                ),
                (
                    "intent_name",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                (
                    "locale",
                    models.CharField(blank=True, default="", max_length=20),
                ),
                (
                    "application_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "user_id_hash",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=64,
                    ),
                ),
                ("user_text", models.TextField(blank=True, default="")),
                ("assistant_text", models.TextField(blank=True, default="")),
                ("slots", models.JSONField(blank=True, default=dict)),
                ("request_data", models.JSONField(blank=True, default=dict)),
                (
                    "session_ended_reason",
                    models.CharField(blank=True, default="", max_length=80),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "conversa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="interacoes_alexa",
                        to="conversation.conversa",
                    ),
                ),
            ],
            options={
                "ordering": ["criado_em"],
            },
        ),
    ]

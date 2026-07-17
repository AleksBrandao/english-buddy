# Generated manually for the guided lesson MVP.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessaoTreino",
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
                ("scenario_id", models.CharField(db_index=True, max_length=100)),
                (
                    "etapa_atual",
                    models.CharField(
                        choices=[
                            ("introduction", "Introdução"),
                            ("phrase_preparation", "Preparação de expressões"),
                            ("first_attempt", "Primeira tentativa"),
                            ("first_feedback", "Feedback intermediário"),
                            ("second_attempt", "Segunda tentativa"),
                            ("final_result", "Resultado final"),
                            ("completed", "Concluída"),
                        ],
                        default="introduction",
                        max_length=50,
                    ),
                ),
                (
                    "primeira_tentativa",
                    models.JSONField(blank=True, default=list),
                ),
                (
                    "segunda_tentativa",
                    models.JSONField(blank=True, default=list),
                ),
                ("iniciada_em", models.DateTimeField(auto_now_add=True)),
                ("finalizada_em", models.DateTimeField(blank=True, null=True)),
                (
                    "conversa",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessao_treino",
                        to="conversation.conversa",
                    ),
                ),
                (
                    "perfil",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessoes_treino",
                        to="conversation.perfil",
                    ),
                ),
            ],
            options={
                "ordering": ["-iniciada_em"],
            },
        ),
        migrations.CreateModel(
            name="AvaliacaoSessao",
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
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("primeira_tentativa", "Primeira tentativa"),
                            ("resultado_final", "Resultado final"),
                        ],
                        max_length=30,
                    ),
                ),
                ("dados", models.JSONField(blank=True, default=dict)),
                ("criada_em", models.DateTimeField(auto_now_add=True)),
                (
                    "sessao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="avaliacoes",
                        to="conversation.sessaotreino",
                    ),
                ),
            ],
            options={
                "ordering": ["criada_em"],
            },
        ),
        migrations.AddConstraint(
            model_name="avaliacaosessao",
            constraint=models.UniqueConstraint(
                fields=("sessao", "tipo"),
                name="unique_evaluation_type_per_session",
            ),
        ),
    ]

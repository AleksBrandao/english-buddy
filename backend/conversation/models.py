from django.db import models


class Perfil(models.Model):
    """Perfil único do aprendiz (assume usuário único por enquanto,
    sem sistema de login ainda)."""

    nivel_atual = models.CharField(
        max_length=50,
        default="A2/B1 (intermediate-beginner)",
    )
    velocidade_preferida = models.FloatField(default=1.0)
    referencia_nivel = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Descrição de conteúdos que o usuário já entende bem, "
            "usada como âncora concreta de calibração (ex: 'entende bem "
            "podcasts de shadowing como Speak Up Sessions')."
        ),
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil (nível: {self.nivel_atual})"

    @classmethod
    def obter_ou_criar(cls):
        perfil, _ = cls.objects.get_or_create(id=1)
        return perfil


class Conversa(models.Model):
    perfil = models.ForeignKey(
        Perfil,
        on_delete=models.CASCADE,
        related_name="conversas",
    )
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Conversa #{self.id} ({self.iniciada_em:%d/%m/%Y %H:%M})"


class Mensagem(models.Model):
    AUTOR_CHOICES = [
        ("usuario", "Usuário"),
        ("assistente", "Assistente"),
    ]

    conversa = models.ForeignKey(
        Conversa,
        on_delete=models.CASCADE,
        related_name="mensagens",
    )
    autor = models.CharField(max_length=10, choices=AUTOR_CHOICES)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]

    def __str__(self):
        return f"[{self.autor}] {self.texto[:50]}"


class SessaoTreino(models.Model):
    """Execução de uma prática guiada associada a uma conversa."""

    class Etapa(models.TextChoices):
        INTRODUCTION = "introduction", "Introdução"
        PHRASE_PREPARATION = "phrase_preparation", "Preparação de expressões"
        FIRST_ATTEMPT = "first_attempt", "Primeira tentativa"
        FIRST_FEEDBACK = "first_feedback", "Feedback intermediário"
        SECOND_ATTEMPT = "second_attempt", "Segunda tentativa"
        FINAL_RESULT = "final_result", "Resultado final"
        COMPLETED = "completed", "Concluída"

    perfil = models.ForeignKey(
        Perfil,
        on_delete=models.CASCADE,
        related_name="sessoes_treino",
    )
    conversa = models.OneToOneField(
        Conversa,
        on_delete=models.CASCADE,
        related_name="sessao_treino",
    )
    scenario_id = models.CharField(max_length=100, db_index=True)
    etapa_atual = models.CharField(
        max_length=50,
        choices=Etapa.choices,
        default=Etapa.INTRODUCTION,
    )
    primeira_tentativa = models.JSONField(default=list, blank=True)
    segunda_tentativa = models.JSONField(default=list, blank=True)
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-iniciada_em"]

    def __str__(self):
        return f"Sessão #{self.id} — {self.scenario_id} ({self.etapa_atual})"


class AvaliacaoSessao(models.Model):
    """Resultado estruturado produzido pelo avaliador da prática guiada."""

    class Tipo(models.TextChoices):
        PRIMEIRA_TENTATIVA = "primeira_tentativa", "Primeira tentativa"
        RESULTADO_FINAL = "resultado_final", "Resultado final"

    sessao = models.ForeignKey(
        SessaoTreino,
        on_delete=models.CASCADE,
        related_name="avaliacoes",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    dados = models.JSONField(default=dict, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["sessao", "tipo"],
                name="unique_evaluation_type_per_session",
            )
        ]

    def __str__(self):
        return f"Avaliação {self.get_tipo_display()} — sessão #{self.sessao_id}"

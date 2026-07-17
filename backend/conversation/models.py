from django.db import models


class Perfil(models.Model):
    """Perfil único do aprendiz (assume usuário único por enquanto,
    sem sistema de login ainda)."""

    nivel_atual = models.CharField(max_length=50, default="A2/B1 (intermediate-beginner)")
    velocidade_preferida = models.FloatField(default=1.0)
    referencia_nivel = models.TextField(
        blank=True,
        default="",
        help_text="Descrição de conteúdos que o usuário já entende bem, "
        "usada como âncora concreta de calibração (ex: 'entende bem "
        "podcasts de shadowing como Speak Up Sessions').",
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
    CANAL_CHOICES = [
        ("web", "Web"),
        ("alexa", "Alexa"),
    ]

    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="conversas")
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES, default="web")
    external_session_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    external_user_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Conversa #{self.id} ({self.iniciada_em:%d/%m/%Y %H:%M})"


class Mensagem(models.Model):
    AUTOR_CHOICES = [("usuario", "Usuário"), ("assistente", "Assistente")]

    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="mensagens")
    autor = models.CharField(max_length=10, choices=AUTOR_CHOICES)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]

    def __str__(self):
        return f"[{self.autor}] {self.texto[:50]}"


class InteracaoAlexa(models.Model):
    """Registro técnico de uma requisição recebida pela Skill Alexa.

    O request_id é único para tornar o endpoint idempotente: se a Lambda
    repetir o envio, a mesma interação é atualizada em vez de duplicada.
    """

    conversa = models.ForeignKey(
        Conversa,
        on_delete=models.CASCADE,
        related_name="interacoes_alexa",
    )
    request_id = models.CharField(max_length=255, unique=True)
    request_type = models.CharField(max_length=80)
    intent_name = models.CharField(max_length=150, blank=True, default="")
    slots = models.JSONField(default=dict, blank=True)
    locale = models.CharField(max_length=20, blank=True, default="")
    user_text = models.TextField(blank=True, default="")
    assistant_text = models.TextField(blank=True, default="")
    response_should_end_session = models.BooleanField(null=True, blank=True)
    status_code = models.PositiveSmallIntegerField(default=200)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        destino = self.intent_name or self.request_type
        return f"Alexa {destino} ({self.request_id})"

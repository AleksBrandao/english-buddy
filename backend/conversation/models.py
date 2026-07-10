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
                  "podcasts de shadowing como Speak Up Sessions')."
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
    perfil = models.ForeignKey(Perfil, on_delete=models.CASCADE, related_name="conversas")
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
from django.contrib import admin

from .models import (
    AvaliacaoSessao,
    Conversa,
    InteracaoAlexa,
    Mensagem,
    Perfil,
    SessaoTreino,
)


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    readonly_fields = ("autor", "texto", "criado_em")
    can_delete = False


class InteracaoAlexaInline(admin.TabularInline):
    model = InteracaoAlexa
    extra = 0
    fields = (
        "request_type",
        "intent_name",
        "user_text",
        "assistant_text",
        "criado_em",
    )
    readonly_fields = fields
    can_delete = False


class AvaliacaoSessaoInline(admin.TabularInline):
    model = AvaliacaoSessao
    extra = 0
    readonly_fields = ("tipo", "dados", "criada_em")
    can_delete = False


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("id", "nivel_atual", "velocidade_preferida", "atualizado_em")
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "perfil",
        "origem",
        "alexa_session_id",
        "iniciada_em",
        "finalizada_em",
        "total_mensagens",
    )
    list_filter = ("origem",)
    search_fields = ("alexa_session_id",)
    inlines = [MensagemInline, InteracaoAlexaInline]
    readonly_fields = ("iniciada_em",)

    def total_mensagens(self, obj):
        return obj.mensagens.count()

    total_mensagens.short_description = "Mensagens"


@admin.register(Mensagem)
class MensagemAdmin(admin.ModelAdmin):
    list_display = ("id", "conversa", "autor", "texto_resumido", "criado_em")
    list_filter = ("autor",)
    readonly_fields = ("criado_em",)

    def texto_resumido(self, obj):
        return obj.texto[:80]

    texto_resumido.short_description = "Texto"


@admin.register(InteracaoAlexa)
class InteracaoAlexaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversa",
        "request_type",
        "intent_name",
        "texto_usuario_resumido",
        "criado_em",
    )
    list_filter = ("request_type", "intent_name", "locale")
    search_fields = (
        "request_id",
        "conversa__alexa_session_id",
        "user_text",
        "assistant_text",
    )
    readonly_fields = (
        "conversa",
        "request_id",
        "request_type",
        "intent_name",
        "locale",
        "application_id",
        "user_id_hash",
        "user_text",
        "assistant_text",
        "slots",
        "request_data",
        "session_ended_reason",
        "criado_em",
    )

    def texto_usuario_resumido(self, obj):
        return obj.user_text[:80]

    texto_usuario_resumido.short_description = "Usuário"


@admin.register(SessaoTreino)
class SessaoTreinoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "scenario_id",
        "perfil",
        "etapa_atual",
        "iniciada_em",
        "finalizada_em",
    )
    list_filter = ("scenario_id", "etapa_atual")
    readonly_fields = ("iniciada_em",)
    inlines = [AvaliacaoSessaoInline]


@admin.register(AvaliacaoSessao)
class AvaliacaoSessaoAdmin(admin.ModelAdmin):
    list_display = ("id", "sessao", "tipo", "criada_em")
    list_filter = ("tipo",)
    readonly_fields = ("criada_em",)

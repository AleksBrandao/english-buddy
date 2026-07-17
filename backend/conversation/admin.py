from django.contrib import admin

from .models import Conversa, InteracaoAlexa, Mensagem, Perfil


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    readonly_fields = ("autor", "texto", "criado_em")
    can_delete = False


class InteracaoAlexaInline(admin.TabularInline):
    model = InteracaoAlexa
    extra = 0
    readonly_fields = (
        "request_id",
        "request_type",
        "intent_name",
        "user_text",
        "assistant_text",
        "status_code",
        "latency_ms",
        "criado_em",
    )
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
        "canal",
        "external_session_id",
        "iniciada_em",
        "finalizada_em",
        "total_mensagens",
    )
    list_filter = ("canal",)
    search_fields = ("external_session_id", "external_user_hash")
    inlines = [MensagemInline, InteracaoAlexaInline]
    readonly_fields = ("iniciada_em",)

    def total_mensagens(self, obj):
        return obj.mensagens.count()

    total_mensagens.short_description = "Mensagens"


@admin.register(Mensagem)
class MensagemAdmin(admin.ModelAdmin):
    list_display = ("id", "conversa", "autor", "texto_resumido", "criado_em")
    list_filter = ("autor", "conversa__canal")
    search_fields = ("texto",)
    readonly_fields = ("criado_em",)

    def texto_resumido(self, obj):
        return obj.texto[:80]

    texto_resumido.short_description = "Texto"


@admin.register(InteracaoAlexa)
class InteracaoAlexaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "request_type",
        "intent_name",
        "user_text_resumido",
        "status_code",
        "latency_ms",
        "criado_em",
    )
    list_filter = ("request_type", "intent_name", "status_code", "locale")
    search_fields = (
        "request_id",
        "intent_name",
        "user_text",
        "assistant_text",
        "conversa__external_session_id",
    )
    readonly_fields = ("criado_em", "atualizado_em")

    def user_text_resumido(self, obj):
        return obj.user_text[:80]

    user_text_resumido.short_description = "Fala do usuário"

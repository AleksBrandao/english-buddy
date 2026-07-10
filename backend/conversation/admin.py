from django.contrib import admin
from .models import Perfil, Conversa, Mensagem


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    readonly_fields = ("autor", "texto", "criado_em")
    can_delete = False


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("id", "nivel_atual", "velocidade_preferida", "atualizado_em")
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ("id", "perfil", "iniciada_em", "finalizada_em", "total_mensagens")
    inlines = [MensagemInline]
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
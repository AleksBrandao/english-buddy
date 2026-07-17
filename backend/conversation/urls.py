from django.urls import path

from .views import registrar_interacao_alexa


urlpatterns = [
    path("alexa/interactions/", registrar_interacao_alexa, name="registrar-interacao-alexa"),
]

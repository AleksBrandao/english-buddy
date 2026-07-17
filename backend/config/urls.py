"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

import os

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from django.conf import settings


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("conversation.urls")),
    re_path(
        r"^(?!assets/|api/).*$/",
        TemplateView.as_view(template_name="index.html"),
    ),
]

TEMPLATES_DIR = os.path.join(settings.BASE_DIR.parent, "frontend", "dist")

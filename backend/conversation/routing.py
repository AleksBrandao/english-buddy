from django.urls import re_path

from .feedback_consumer import FeedbackTalkConsumer


websocket_urlpatterns = [
    re_path(r"ws/talk/$", FeedbackTalkConsumer.as_asgi()),
]

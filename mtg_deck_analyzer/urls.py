"""URL routing for the MTG Deck Analyzer web service."""

from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("decks", views.create_deck, name="create_deck"),
    path("decks/<int:deck_id>", views.deck_detail, name="deck_detail"),
    path("decks/<int:deck_id>/pdf", views.deck_pdf, name="deck_pdf"),
    path("media/<str:name>", views.media, name="media"),
]

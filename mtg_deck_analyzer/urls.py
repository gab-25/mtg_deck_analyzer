"""URL routing for the MTG Deck Analyzer web service."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login", auth_views.LoginView.as_view(), name="login"),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.index, name="index"),
    path("decks/new", views.new_deck, name="new_deck"),
    path("decks", views.create_deck, name="create_deck"),
    path("decks/<int:deck_id>", views.deck_detail, name="deck_detail"),
    path("decks/<int:deck_id>/delete", views.delete_deck, name="delete_deck"),
    path("decks/<int:deck_id>/pdf", views.deck_pdf, name="deck_pdf"),
    path("media/<str:name>", views.media, name="media"),
]

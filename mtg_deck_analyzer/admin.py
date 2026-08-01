"""Django admin registrations."""

from django.contrib import admin

from .models import Deck, ScryfallCard, ScryfallImage


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "total_cards", "total_value_eur", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "raw_decklist")
    readonly_fields = ("created_at",)


@admin.register(ScryfallCard)
class ScryfallCardAdmin(admin.ModelAdmin):
    list_display = ("key", "created_at")
    search_fields = ("key",)
    readonly_fields = ("created_at",)


@admin.register(ScryfallImage)
class ScryfallImageAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)

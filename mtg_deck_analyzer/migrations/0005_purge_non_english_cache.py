from django.db import migrations


def purge_non_english_cache(apps, schema_editor):
    """Removes Scryfall cache entries left over from non-English analyses.

    Now that the app is English-only, only ``card_en_*`` card JSON and
    ``img_*_en.jpg`` / ``img_*_en_face*.jpg`` images are ever read. Older
    localized entries (``card_it_*``, ``img_*_it.jpg``, …) are dead weight and
    are dropped here. Deck records themselves are left untouched.
    """
    ScryfallCard = apps.get_model("mtg_deck_analyzer", "ScryfallCard")
    ScryfallImage = apps.get_model("mtg_deck_analyzer", "ScryfallImage")

    # Cards are keyed ``card_<lang>_<slug>``: keep only the English ones.
    ScryfallCard.objects.filter(key__startswith="card_").exclude(
        key__startswith="card_en_"
    ).delete()

    # Images are named ``img_<id>_<lang>.jpg`` or ``img_<id>_<lang>_face<idx>.jpg``.
    # English images end in ``_en.jpg`` or contain ``_en_face``; drop the rest.
    ScryfallImage.objects.filter(name__startswith="img_").exclude(
        name__endswith="_en.jpg"
    ).exclude(name__contains="_en_face").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mtg_deck_analyzer", "0004_remove_deck_lang"),
    ]

    operations = [
        # Irreversible: deleted cache rows are simply re-fetched from Scryfall
        # on demand, so the reverse is a no-op.
        migrations.RunPython(purge_non_english_cache, migrations.RunPython.noop),
    ]

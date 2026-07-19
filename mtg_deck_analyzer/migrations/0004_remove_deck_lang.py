from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("mtg_deck_analyzer", "0003_alter_deck_id"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="deck",
            name="lang",
        ),
    ]

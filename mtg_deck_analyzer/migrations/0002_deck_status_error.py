from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mtg_deck_analyzer", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="deck",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                default="ready",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="deck",
            name="error",
            field=models.TextField(blank=True, null=True),
        ),
    ]

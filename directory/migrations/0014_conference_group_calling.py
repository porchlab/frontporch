from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("directory", "0013_child_spoken_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="conferencegroup",
            name="calling_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Staff must enable calling before this group becomes dialable.",
            ),
        ),
        migrations.AddField(
            model_name="conferencegroup",
            name="dial_extension",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Leave blank to assign an unused four-digit extension when enabled."
                ),
                max_length=4,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="conferencegroup",
            name="ring_timeout_seconds",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text=(
                    "How long unanswered member phones ring, from 5 to 120 seconds."
                ),
                validators=[MinValueValidator(5), MaxValueValidator(120)],
            ),
        ),
    ]

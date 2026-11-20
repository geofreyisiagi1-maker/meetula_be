from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communities", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="community",
            name="rules",
            field=models.JSONField(blank=True, default=list),
        ),
    ]

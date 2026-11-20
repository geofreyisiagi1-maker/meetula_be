from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communities", "0002_community_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="community",
            name="country",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]

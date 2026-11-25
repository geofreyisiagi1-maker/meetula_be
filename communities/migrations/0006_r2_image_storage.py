from django.db import migrations, models


LEGACY_CLOUDINARY_PREFIX = "cloudinary-legacy://"


def preserve_cloudinary_images(apps, schema_editor):
    Community = apps.get_model("communities", "Community")
    for field in ("profile_image", "cover_image"):
        for community in Community.objects.exclude(**{f"{field}__isnull": True}).exclude(
            **{field: ""}
        ).iterator():
            image_name = getattr(community, field)
            if not image_name.startswith(LEGACY_CLOUDINARY_PREFIX):
                setattr(community, field, f"{LEGACY_CLOUDINARY_PREFIX}{image_name}")
                community.save(update_fields=[field])


def restore_cloudinary_image_names(apps, schema_editor):
    Community = apps.get_model("communities", "Community")
    for field in ("profile_image", "cover_image"):
        for community in Community.objects.filter(
            **{f"{field}__startswith": LEGACY_CLOUDINARY_PREFIX}
        ).iterator():
            image_name = getattr(community, field)
            setattr(community, field, image_name[len(LEGACY_CLOUDINARY_PREFIX) :])
            community.save(update_fields=[field])


class Migration(migrations.Migration):

    dependencies = [
        ("communities", "0005_alter_community_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="community",
            name="profile_image",
            field=models.ImageField(
                blank=True,
                max_length=512,
                null=True,
                upload_to="communities/profile/",
                verbose_name="profile image",
            ),
        ),
        migrations.AlterField(
            model_name="community",
            name="cover_image",
            field=models.ImageField(
                blank=True,
                max_length=512,
                null=True,
                upload_to="communities/cover/",
                verbose_name="cover image",
            ),
        ),
        migrations.RunPython(
            preserve_cloudinary_images,
            restore_cloudinary_image_names,
        ),
    ]

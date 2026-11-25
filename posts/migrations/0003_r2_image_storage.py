from django.db import migrations, models


LEGACY_CLOUDINARY_PREFIX = "cloudinary-legacy://"


def preserve_cloudinary_images(apps, schema_editor):
    for model_name, field in (
        ("PostImage", "image"),
        ("Comment", "image"),
        ("Reply", "image"),
    ):
        model = apps.get_model("posts", model_name)
        for obj in model.objects.exclude(**{f"{field}__isnull": True}).exclude(
            **{field: ""}
        ).iterator():
            image_name = getattr(obj, field)
            if not image_name.startswith(LEGACY_CLOUDINARY_PREFIX):
                setattr(obj, field, f"{LEGACY_CLOUDINARY_PREFIX}{image_name}")
                obj.save(update_fields=[field])


def restore_cloudinary_image_names(apps, schema_editor):
    for model_name, field in (
        ("PostImage", "image"),
        ("Comment", "image"),
        ("Reply", "image"),
    ):
        model = apps.get_model("posts", model_name)
        for obj in model.objects.filter(
            **{f"{field}__startswith": LEGACY_CLOUDINARY_PREFIX}
        ).iterator():
            image_name = getattr(obj, field)
            setattr(obj, field, image_name[len(LEGACY_CLOUDINARY_PREFIX) :])
            obj.save(update_fields=[field])


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0002_post_accepted_answer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="postimage",
            name="image",
            field=models.ImageField(max_length=512, upload_to="posts/", verbose_name="image"),
        ),
        migrations.AlterField(
            model_name="comment",
            name="image",
            field=models.ImageField(
                blank=True,
                max_length=512,
                null=True,
                upload_to="comments/",
                verbose_name="image",
            ),
        ),
        migrations.AlterField(
            model_name="reply",
            name="image",
            field=models.ImageField(
                blank=True,
                max_length=512,
                null=True,
                upload_to="replies/",
                verbose_name="image",
            ),
        ),
        migrations.RunPython(
            preserve_cloudinary_images,
            restore_cloudinary_image_names,
        ),
    ]

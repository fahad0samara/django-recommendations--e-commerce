# Generated by Django 5.1.3 on 2025-01-04 07:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0009_order_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="featured",
            field=models.BooleanField(default=False),
        ),
    ]

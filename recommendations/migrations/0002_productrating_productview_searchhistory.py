# Generated by Django 5.0 on 2025-01-03 14:36

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductRating",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "rating",
                    models.IntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ]
                    ),
                ),
                ("review", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ratings",
                        to="recommendations.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["product", "rating"],
                        name="recommendat_product_6f96ea_idx",
                    ),
                    models.Index(
                        fields=["user", "rating"], name="recommendat_user_id_6d5c26_idx"
                    ),
                ],
                "unique_together": {("user", "product")},
            },
        ),
        migrations.CreateModel(
            name="ProductView",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("view_count", models.IntegerField(default=1)),
                ("last_viewed", models.DateTimeField(auto_now=True)),
                ("session_id", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="views",
                        to="recommendations.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["product", "view_count"],
                        name="recommendat_product_f6901e_idx",
                    ),
                    models.Index(
                        fields=["last_viewed"], name="recommendat_last_vi_69c051_idx"
                    ),
                ],
                "unique_together": {("user", "product")},
            },
        ),
        migrations.CreateModel(
            name="SearchHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("query", models.CharField(max_length=255)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("results_count", models.IntegerField()),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="recommendations.category",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Search histories",
                "indexes": [
                    models.Index(
                        fields=["user", "timestamp"],
                        name="recommendat_user_id_aca658_idx",
                    ),
                    models.Index(fields=["query"], name="recommendat_query_8b904a_idx"),
                ],
            },
        ),
    ]

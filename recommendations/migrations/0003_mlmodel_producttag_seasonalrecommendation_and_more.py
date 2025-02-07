# Generated by Django 5.0 on 2025-01-03 14:43

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0002_productrating_productview_searchhistory"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MLModel",
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
                ("name", models.CharField(max_length=100)),
                (
                    "model_type",
                    models.CharField(
                        choices=[
                            ("collaborative", "Collaborative Filtering"),
                            ("content_based", "Content Based"),
                            ("hybrid", "Hybrid"),
                        ],
                        max_length=15,
                    ),
                ),
                ("version", models.CharField(max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("accuracy", models.FloatField(blank=True, null=True)),
                ("last_trained", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(default=dict)),
            ],
        ),
        migrations.CreateModel(
            name="ProductTag",
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
                ("name", models.CharField(max_length=50)),
                (
                    "products",
                    models.ManyToManyField(
                        related_name="tags", to="recommendations.product"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SeasonalRecommendation",
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
                ("name", models.CharField(max_length=100)),
                (
                    "season_type",
                    models.CharField(
                        choices=[
                            ("spring", "Spring"),
                            ("summer", "Summer"),
                            ("autumn", "Autumn"),
                            ("winter", "Winter"),
                            ("holiday", "Holiday"),
                            ("custom", "Custom"),
                        ],
                        max_length=10,
                    ),
                ),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("is_active", models.BooleanField(default=True)),
                ("priority", models.IntegerField(default=0)),
                (
                    "products",
                    models.ManyToManyField(
                        related_name="seasonal_recommendations",
                        to="recommendations.product",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MLPrediction",
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
                ("score", models.FloatField()),
                ("confidence", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="recommendations.mlmodel",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
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
                        fields=["user", "score"], name="recommendat_user_id_d870c0_idx"
                    ),
                    models.Index(
                        fields=["created_at"], name="recommendat_created_173d91_idx"
                    ),
                ],
                "unique_together": {("user", "product", "model")},
            },
        ),
        migrations.CreateModel(
            name="PriceAlert",
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
                ("target_price", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("below", "Price Below"),
                            ("above", "Price Above"),
                            ("percent_change", "Percentage Change"),
                        ],
                        max_length=15,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_notified", models.DateTimeField(blank=True, null=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
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
                "unique_together": {("user", "product", "alert_type")},
            },
        ),
        migrations.CreateModel(
            name="ProductAttribute",
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
                ("name", models.CharField(max_length=50)),
                ("value", models.CharField(max_length=255)),
                (
                    "attribute_type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("number", "Number"),
                            ("boolean", "Boolean"),
                            ("color", "Color"),
                            ("size", "Size"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attributes",
                        to="recommendations.product",
                    ),
                ),
            ],
            options={
                "unique_together": {("product", "name")},
            },
        ),
        migrations.CreateModel(
            name="RecentlyViewed",
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
                ("viewed_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
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
                "ordering": ["-viewed_at"],
                "unique_together": {("user", "product")},
            },
        ),
    ]

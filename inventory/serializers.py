"""
inventory/serializers.py

OWASP mapping:
- A01: cost_price is commercially sensitive (margin data) — cashiers should
  never see it, even read-only. Rather than trusting the frontend to hide
  a field, the serializer itself removes it based on the requesting user's
  role, so a direct API call (curl, Postman) can't extract it either.
"""
from rest_framework import serializers

from .models import Category, Product, Stock


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "category",
            "unit_price", "cost_price", "reorder_threshold", "is_active",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # Role-based field redaction: cost_price never leaves the server
        # for a cashier, regardless of what the frontend chooses to render.
        if request and getattr(request.user, "role", None) == "CASHIER":
            data.pop("cost_price", None)
        return data


class StockSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True
    )
    is_below_threshold = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = ["id", "product", "product_id", "branch", "quantity", "is_below_threshold", "updated_at"]
        read_only_fields = ["branch"]  # branch is set server-side from the request, never client-supplied

    def get_is_below_threshold(self, obj):
        return obj.is_below_threshold()

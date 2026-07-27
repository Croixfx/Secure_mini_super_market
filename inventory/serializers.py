"""
inventory/serializers.py

OWASP mapping:
- A01: cost_price is commercially sensitive (margin data) — cashiers should
  never see it, even read-only. Rather than trusting the frontend to hide
  a field, the serializer itself removes it based on the requesting user's
  role, so a direct API call (curl, Postman) can't extract it either.
"""
from rest_framework import serializers

from .models import Category, Product, Stock, StockMovement


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


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    performed_by_username = serializers.CharField(source="performed_by.username", read_only=True)
    reference_label = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "product_sku", "branch", "branch_name",
            "movement_type", "quantity_delta", "batch_number", "expiry_date", "unit_cost",
            "reason", "reference_label", "performed_by", "performed_by_username", "created_at",
        ]
        read_only_fields = fields  # this endpoint is read-only everywhere — see views.py

    def get_reference_label(self, obj):
        if obj.reference is None:
            return None
        # Human-readable pointer to whatever caused this movement, e.g.
        # "Sale #1042" or "PurchaseOrder #17" — the __str__ of the
        # referenced model does the real work, so each domain app controls
        # how its own objects are described here.
        return f"{obj.reference_content_type.model} #{obj.reference_object_id}"


class WastageRequestSerializer(serializers.Serializer):
    """Input serializer for the manual wastage-recording endpoint."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255)


class StocktakeRequestSerializer(serializers.Serializer):
    """Input serializer for reconciling a physical count against the system."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    counted_quantity = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

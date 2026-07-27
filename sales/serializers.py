"""
sales/serializers.py

OWASP mapping:
- A03/A04: the client sends product IDs and quantities ONLY — never a
  price or a total. Every price is looked up from Product.unit_price at
  validation time, server-side. A tampered request that adds a fake
  "unit_price": "0.01" field is simply ignored; there's no field for it to
  land in.
"""
from rest_framework import serializers

from inventory.models import Product

from .models import PaymentMethod, Sale, SaleItem


class SaleItemInputSerializer(serializers.Serializer):
    """What the client actually sends per line item — deliberately minimal."""

    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True), source="product")
    quantity = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    items = SaleItemInputSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("A sale must include at least one item.")
        seen = set()
        for item in items:
            pid = item["product"].id
            if pid in seen:
                raise serializers.ValidationError(
                    "Duplicate product in cart — combine into a single line with the total quantity."
                )
            seen.add(pid)
        return items


class SaleItemOutputSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "product_sku", "quantity", "unit_price_at_sale", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemOutputSerializer(many=True, read_only=True)
    cashier_username = serializers.CharField(source="cashier.username", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "branch", "branch_name", "cashier", "cashier_username", "payment_method",
            "status", "total_amount", "items", "created_at", "idempotency_key",
        ]
        read_only_fields = fields

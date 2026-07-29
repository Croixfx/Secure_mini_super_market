from decimal import Decimal

from rest_framework import serializers

from inventory.models import Product

from .models import PurchaseOrder, PurchaseOrderItem, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_name", "email", "phone", "is_active"]


class PurchaseOrderItemInputSerializer(serializers.Serializer):
    """What the client sends when CREATING an order — no quantity_received
    field exists here, since that's only ever set by the receiving flow."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity_ordered = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    quantity_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id", "product", "product_name", "product_sku", "quantity_ordered",
            "quantity_received", "quantity_remaining", "unit_cost", "batch_number", "expiry_date",
        ]
        read_only_fields = ["quantity_received"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "supplier", "supplier_name", "branch", "branch_name", "status",
            "created_by", "created_by_username", "created_at", "sent_at", "items", "total_cost",
        ]
        read_only_fields = ["status", "created_by", "branch", "created_at", "sent_at"]

    def get_total_cost(self, obj):
        return sum((item.quantity_ordered * item.unit_cost for item in obj.items.all()), start=0)


class PurchaseOrderCreateSerializer(serializers.Serializer):
    """Input-only serializer for creating an order with its line items in
    one call — branch and created_by are NEVER accepted from the client,
    same reasoning as everywhere else in this project (Sale, Stock, etc)."""

    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.filter(is_active=True))
    items = PurchaseOrderItemInputSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("An order must include at least one item.")
        return items


class ReceiveItemsSerializer(serializers.Serializer):
    class ReceiptLineSerializer(serializers.Serializer):
        item_id = serializers.IntegerField()
        quantity = serializers.IntegerField(min_value=1)

    receipts = ReceiptLineSerializer(many=True)

    def validate_receipts(self, receipts):
        if not receipts:
            raise serializers.ValidationError("Must specify at least one line to receive.")
        return receipts

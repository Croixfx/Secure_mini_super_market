from rest_framework import serializers

from branches.models import Branch
from .models import Product, StockTransfer


class TransferCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    from_branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    to_branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    quantity = serializers.IntegerField(min_value=1)


class ReceiveTransferSerializer(serializers.Serializer):
    quantity_received = serializers.IntegerField(min_value=0)


class StockTransferSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)
    discrepancy = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id", "product", "product_name", "from_branch", "from_branch_name",
            "to_branch", "to_branch_name", "quantity_requested", "quantity_received",
            "discrepancy", "status", "requested_by", "requested_by_username",
            "requested_at", "dispatched_at", "received_at",
        ]
        read_only_fields = [
            "status", "quantity_received", "requested_by", "requested_at", "dispatched_at", "received_at",
        ]

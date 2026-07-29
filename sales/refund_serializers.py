from rest_framework import serializers

from .models import Refund, RefundItem


class RefundLineInputSerializer(serializers.Serializer):
    sale_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    restock = serializers.BooleanField()  # no default - force an explicit choice every time


class RefundRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    lines = RefundLineInputSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("Must specify at least one item to refund.")
        seen = set()
        for line in lines:
            if line["sale_item_id"] in seen:
                raise serializers.ValidationError("Duplicate sale item in refund request.")
            seen.add(line["sale_item_id"])
        return lines


class RefundItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="sale_item.product.name", read_only=True)

    class Meta:
        model = RefundItem
        fields = ["id", "sale_item", "product_name", "quantity", "restocked"]


class RefundSerializer(serializers.ModelSerializer):
    items = RefundItemSerializer(many=True, read_only=True)
    processed_by_username = serializers.CharField(source="processed_by.username", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id", "sale", "processed_by", "processed_by_username", "reason",
            "total_refunded_amount", "items", "created_at",
        ]
        read_only_fields = fields

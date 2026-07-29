"""
branches/serializers.py

NOTE FOR CLAUDE CODE: this assumes Branch currently has at least a `name`
field (confirmed from earlier sessions — it was built minimally, "only the
field the tests actually need"). This serializer also references `address`
and `phone` as optional fields for real operational use (an owner opening
a second branch needs a way to note where it is and a contact number).
If those fields don't exist on the model yet, add them via a migration:

    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)

Adjust this serializer's `fields` list if you choose different field names.
"""
from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = ["id", "name", "address", "phone", "staff_count"]

    def get_staff_count(self, obj):
        return obj.staff.count()  # `staff` related_name already exists from CustomUser.branch FK


class BranchLookupSerializer(serializers.ModelSerializer):
    """id + name only — no address/phone/staff_count. Used by
    BranchViewSet.lookup so a Manager can see other branches exist by name
    (e.g. to pick a stock transfer destination) without exposing the
    Owner-only operational detail the full BranchSerializer carries."""

    class Meta:
        model = Branch
        fields = ["id", "name"]

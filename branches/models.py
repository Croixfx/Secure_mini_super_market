from django.db import models


class Branch(models.Model):
    """A physical supermarket branch/location that staff and data are scoped to."""

    name = models.CharField(max_length=150, unique=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/sales/", include("sales.urls")),
    path("api/procurement/", include("procurement.urls")),
]

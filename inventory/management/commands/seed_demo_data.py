"""
inventory/management/commands/seed_demo_data.py

Creates just enough data to click through the inventory demo in a browser:
two branches (so branch-scoping is actually visible — a single branch can't
demonstrate an owner seeing everything vs. a manager seeing only their own),
one category, two products, stock rows split across both branches, and one
test user per role.

Refuses to run outside DEBUG to avoid ever seeding known demo credentials
into a real deployment.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role
from branches.models import Branch
from inventory.models import Category, Product, Stock

User = get_user_model()

DEMO_PASSWORD = "DemoPass123!"


class Command(BaseCommand):
    help = "Seed demo data (branches, users, products, stock) for the inventory browser demo."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to seed demo data outside DEBUG — this creates "
                "accounts with a known, published password."
            )

        with transaction.atomic():
            branch_a, _ = Branch.objects.get_or_create(name="Kimironko")
            branch_b, _ = Branch.objects.get_or_create(name="Remera")

            owner, _ = User.objects.get_or_create(
                username="owner_demo", defaults={"role": Role.OWNER}
            )
            owner.set_password(DEMO_PASSWORD)
            owner.role = Role.OWNER
            owner.branch = None
            owner.save()

            manager, _ = User.objects.get_or_create(
                username="manager_demo", defaults={"role": Role.MANAGER}
            )
            manager.set_password(DEMO_PASSWORD)
            manager.role = Role.MANAGER
            manager.branch = branch_a
            manager.save()

            cashier, _ = User.objects.get_or_create(
                username="cashier_demo", defaults={"role": Role.CASHIER}
            )
            cashier.set_password(DEMO_PASSWORD)
            cashier.role = Role.CASHIER
            cashier.branch = branch_a
            cashier.save()

            category, _ = Category.objects.get_or_create(name="Beverages")

            coke, _ = Product.objects.get_or_create(
                sku="COKE500",
                defaults={
                    "name": "Coca-Cola 500ml",
                    "category": category,
                    "unit_price": "1.50",
                    "cost_price": "0.90",
                    "reorder_threshold": 20,
                },
            )
            fanta, _ = Product.objects.get_or_create(
                sku="FANTA500",
                defaults={
                    "name": "Fanta 500ml",
                    "category": category,
                    "unit_price": "1.50",
                    "cost_price": "0.85",
                    "reorder_threshold": 20,
                },
            )

            # Deliberately uneven quantities: branch A looks healthy, branch
            # B is below its reorder threshold, so the "low stock" warning
            # in the UI has something real to show.
            Stock.objects.update_or_create(product=coke, branch=branch_a, defaults={"quantity": 100})
            Stock.objects.update_or_create(product=fanta, branch=branch_a, defaults={"quantity": 40})
            Stock.objects.update_or_create(product=coke, branch=branch_b, defaults={"quantity": 5})

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write(f"  Branches: {branch_a.name}, {branch_b.name}")
        self.stdout.write(f"  Products: {coke.sku}, {fanta.sku}")
        self.stdout.write("  Login as (password for all: %s):" % DEMO_PASSWORD)
        self.stdout.write(f"    owner_demo    (OWNER, all branches)")
        self.stdout.write(f"    manager_demo  (MANAGER, {branch_a.name})")
        self.stdout.write(f"    cashier_demo  (CASHIER, {branch_a.name})")

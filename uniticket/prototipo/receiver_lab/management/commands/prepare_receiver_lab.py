"""Prepara soltanto il manager e la struttura del laboratorio locale."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.urls import reverse
from organizational_area.models import (
    OrganizationalStructure,
    OrganizationalStructureOfficeEmployee,
    UserManageOrganizationalStructure,
)


class Command(BaseCommand):
    help = "Prepara l’accesso alla UI originale esclusivamente nel laboratorio receiver."

    def handle(self, *args, **options):
        if not getattr(settings, "RECEIVER_DEMO", False):
            raise CommandError("Comando riservato al laboratorio locale dei receiver.")
        database = str(connection.settings_dict["NAME"])
        isolated_test = (
            getattr(settings, "TICKET_EVENTS_ISOLATED_TEST", False)
            and connection.vendor == "sqlite" and "memory" in database
        )
        # Il comando non deve inizializzare altri database, neppure con il flag demo.
        if not isolated_test and (
            connection.vendor != "sqlite"
            or Path(database).resolve() != Path("/sandbox/receiver-demo.sqlite3").resolve()
        ):
            raise CommandError("È richiesto il database SQLite dedicato del laboratorio.")
        with transaction.atomic():
            structure, _ = OrganizationalStructure.objects.get_or_create(
                slug="receiver-demo-only",
                defaults={"name": "Laboratorio receiver", "unique_code": "RECEIVER-LAB", "is_active": True},
            )
            # Il receiver originale UniTicket crea automaticamente l’ufficio predefinito.
            office = structure.get_default_office()
            if office is None:
                raise CommandError("Ufficio predefinito assente: verificare i receiver originali.")
            manager, created = get_user_model().objects.get_or_create(
                username="receiver-manager",
                defaults={"first_name": "Manager", "last_name": "Laboratorio", "is_staff": True},
            )
            if created:
                manager.set_password("local-receivers-only")
                manager.save(update_fields=["password"])
            # Le autorizzazioni sono quelle originali: manager della struttura e membro dell’ufficio.
            UserManageOrganizationalStructure.objects.get_or_create(
                user=manager, organizational_structure=structure,
            )
            OrganizationalStructureOfficeEmployee.objects.get_or_create(employee=manager, office=office)
        dashboard = reverse("uni_ticket:manager_dashboard", kwargs={"structure_slug": structure.slug})
        self.stdout.write("Laboratorio pronto. Login: /local/login/; gestione: " + dashboard)

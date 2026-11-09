"""Verifica che la preparazione della UI originale sia confinata al laboratorio."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from organizational_area.models import OrganizationalStructure
from uni_ticket.models import TicketCategory
from uni_ticket.utils import user_is_manager

from ticket_events.tests.helpers import CategoryTestsSetup


class LabSetupTests(CategoryTestsSetup, TestCase):
    def test_command_refuses_standard_settings_without_writes(self):
        with self.assertRaisesMessage(CommandError, "riservato al laboratorio"):
            call_command("prepare_receiver_lab", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(username="receiver-manager").exists())

    @override_settings(RECEIVER_DEMO=True)
    def test_command_creates_original_manager_without_categories(self):
        output = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("prepare_receiver_lab", stdout=output)
        manager = get_user_model().objects.get(username="receiver-manager")
        structure = OrganizationalStructure.objects.get(slug="receiver-demo-only")
        self.assertTrue(user_is_manager(manager, structure))
        self.assertTrue(manager.check_password("local-receivers-only"))
        self.assertFalse(TicketCategory.objects.exists())
        self.assertEqual(self.notifier.events, [])
        self.assertIn("/local/login/", output.getvalue())

    @override_settings(RECEIVER_DEMO=True)
    def test_command_is_idempotent_and_preserves_changed_password(self):
        call_command("prepare_receiver_lab", stdout=StringIO())
        manager = get_user_model().objects.get(username="receiver-manager")
        manager.set_password("password-locale-cambiata")
        manager.save(update_fields=["password"])
        call_command("prepare_receiver_lab", stdout=StringIO())
        manager.refresh_from_db()
        self.assertTrue(manager.check_password("password-locale-cambiata"))
        self.assertEqual(get_user_model().objects.filter(username="receiver-manager").count(), 1)
        self.assertEqual(OrganizationalStructure.objects.filter(slug="receiver-demo-only").count(), 1)
        self.assertEqual(manager.usermanageorganizationalstructure_set.count(), 1)

    @override_settings(RECEIVER_DEMO=True, TICKET_EVENTS_ISOLATED_TEST=False)
    def test_demo_flag_alone_does_not_authorize_another_database(self):
        # Il database in memoria resta intatto: la guardia deve fermare il comando prima delle scritture.
        with self.assertRaisesMessage(CommandError, "database SQLite dedicato"):
            call_command("prepare_receiver_lab", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(username="receiver-manager").exists())

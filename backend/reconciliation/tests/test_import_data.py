"""
Runs the import_data command using the assignment's sample CSV files.

The test verifies that the known dirty data, such as different record
reference formats and invalid values, is normalized and stored correctly.

This complements test_compare.py, which tests the comparison logic after
the data has already been parsed.
"""

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from reconciliation.models import SystemARecord, SystemBEntry

DATA_DIR = Path(settings.BASE_DIR) / "data"


class ImportDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_data", "--data-dir", str(DATA_DIR))

    def test_all_120_system_a_rows_are_imported(self):
        self.assertEqual(SystemARecord.objects.count(), 120)

    def test_all_121_system_b_rows_are_imported(self):
        self.assertEqual(SystemBEntry.objects.count(), 121)

    def test_lowercase_ref_without_dashes_normalizes(self):
        entry = SystemBEntry.objects.get(record_ref_raw="rec1034")
        self.assertEqual(entry.record_ref_normalized, "REC-1034")
        self.assertEqual(entry.matched_record_id, "REC-1034")

    def test_bare_numeric_ref_normalizes(self):
        entry = SystemBEntry.objects.get(record_ref_raw="1112")
        self.assertEqual(entry.record_ref_normalized, "REC-1112")

    def test_ref_to_nonexistent_record_is_kept_with_no_match(self):
        entry = SystemBEntry.objects.get(entry_id="ENT/2026/4901")
        self.assertEqual(entry.record_ref_normalized, "REC-1999")
        self.assertIsNone(entry.matched_record)
        self.assertTrue(entry.import_issues)  # flagged, not silently accepted

    def test_comma_formatted_value_is_parsed(self):
        entry = SystemBEntry.objects.get(entry_id="ENT/2026/4064")
        self.assertEqual(entry.value_raw, "1,25,400.00")
        self.assertEqual(entry.value, 125400)
"""
Tests for reconciliation/services/compare.py.

These tests create ARecord and BEntry objects directly without using the
database, fixtures, or Django test client.

The comparison logic contains the main business rules of the assignment,
so it is tested separately with different disagreement cases. The import
command and API view mainly use this logic and can be tested separately
at the integration level.

SimpleTestCase is used instead of TestCase because these tests don't need
the database. This avoids unnecessary database setup and keeps the tests
simple and fast.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from reconciliation.services.compare import ARecord, BEntry, Reason, find_discrepancies

ORG = "ORG-A"
LOC = "LOC-101"


def a(record_id, total_value):
    return ARecord(record_id=record_id, org_id=ORG, location_id=LOC, total_value=total_value)


def b(entry_id, ref, value):
    return BEntry(entry_id=entry_id, record_ref_normalized=ref, org_id=ORG, value=value)


class FindDiscrepanciesTests(SimpleTestCase):

    def test_matching_record_produces_no_discrepancy(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = [b("ENT-1", "REC-1", Decimal("100.00"))]

        self.assertEqual(find_discrepancies(records, entries), [])

    def test_matching_record_within_one_cent_tolerance_is_not_flagged(self):
        # Upstream rounding, not a real disagreement.
        records = [a("REC-1", Decimal("100.00"))]
        entries = [b("ENT-1", "REC-1", Decimal("100.005"))]

        self.assertEqual(find_discrepancies(records, entries), [])

    def test_record_with_no_entries_is_missing_in_b(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = []

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.MISSING_IN_B)
        self.assertEqual(result.record_id, "REC-1")
        self.assertEqual(result.a_value, Decimal("100.00"))
        self.assertIsNone(result.b_value)

    def test_entry_pointing_at_unknown_record_is_orphan_in_b(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = [b("ENT-1", "REC-999", Decimal("50.00"))]

        results = find_discrepancies(records, entries)

        # REC-1 itself is untouched (still missing its own entry), plus the
        # orphan entry -- two separate, independent problems.
        reasons = {r.reason for r in results}
        self.assertEqual(reasons, {Reason.MISSING_IN_B, Reason.ORPHAN_IN_B})

        orphan = next(r for r in results if r.reason == Reason.ORPHAN_IN_B)
        self.assertEqual(orphan.entry_id, "ENT-1")
        self.assertIsNone(orphan.record_id)
        self.assertEqual(orphan.b_value, Decimal("50.00"))

    def test_entry_with_unparseable_ref_is_orphan_in_b(self):
        records = []
        entries = [b("ENT-1", None, Decimal("50.00"))]

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.ORPHAN_IN_B)
        self.assertEqual(result.entry_id, "ENT-1")

    def test_two_entries_for_one_record_is_duplicate_in_b(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = [
            b("ENT-1", "REC-1", Decimal("60.00")),
            b("ENT-2", "REC-1", Decimal("40.00")),
        ]

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.DUPLICATE_IN_B)
        self.assertEqual(result.record_id, "REC-1")
        self.assertIn("ENT-1", result.entry_id)
        self.assertIn("ENT-2", result.entry_id)

    def test_duplicate_entries_are_flagged_even_when_their_values_sum_to_the_total(self):
        # Sample data has exactly this shape: a record split across two
        # System B entries whose values add up to the record's total. It's
        # still two entries for one record, which the brief calls out
        # explicitly as a case to catch -- summing correctly doesn't make
        # it not a duplicate.
        records = [a("REC-1", Decimal("100.00"))]
        entries = [
            b("ENT-1", "REC-1", Decimal("60.00")),
            b("ENT-2", "REC-1", Decimal("40.00")),
        ]

        [result] = find_discrepancies(records, entries)
        self.assertEqual(result.reason, Reason.DUPLICATE_IN_B)

    def test_single_entry_with_different_value_is_value_mismatch(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = [b("ENT-1", "REC-1", Decimal("75.00"))]

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.VALUE_MISMATCH)
        self.assertEqual(result.a_value, Decimal("100.00"))
        self.assertEqual(result.b_value, Decimal("75.00"))

    def test_unparseable_b_value_is_reported_not_dropped(self):
        records = [a("REC-1", Decimal("100.00"))]
        entries = [b("ENT-1", "REC-1", None)]

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.UNPARSEABLE_VALUE)
        self.assertEqual(result.entry_id, "ENT-1")

    def test_unparseable_a_value_is_reported_not_dropped(self):
        records = [a("REC-1", None)]
        entries = [b("ENT-1", "REC-1", Decimal("100.00"))]

        [result] = find_discrepancies(records, entries)

        self.assertEqual(result.reason, Reason.UNPARSEABLE_VALUE)

    def test_every_record_and_entry_is_accounted_for_in_a_larger_batch(self):
        # A rough end-to-end sanity check mirroring the shape of the real
        # dataset, so a refactor that quietly drops a row somewhere gets
        # caught even if the row-level tests above don't happen to cover
        # that exact combination.
        records = [
            a("REC-1", Decimal("10.00")),  # clean match
            a("REC-2", Decimal("20.00")),  # missing in B
            a("REC-3", Decimal("30.00")),  # duplicate in B
        ]
        entries = [
            b("ENT-1", "REC-1", Decimal("10.00")),
            b("ENT-2", "REC-3", Decimal("15.00")),
            b("ENT-3", "REC-3", Decimal("15.00")),
            b("ENT-4", "REC-404", Decimal("5.00")),  # orphan
        ]

        results = find_discrepancies(records, entries)
        reasons = sorted(r.reason.value for r in results)

        self.assertEqual(reasons, ["DUPLICATE_IN_B", "MISSING_IN_B", "ORPHAN_IN_B"])
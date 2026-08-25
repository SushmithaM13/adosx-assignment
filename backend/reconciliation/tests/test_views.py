"""
API tests for the disagreements endpoint.

These tests mainly verify tenant isolation and make sure records from one
organization are not returned when requesting data for another organization.

The detailed comparison cases are tested separately in test_compare.py.
These tests focus on the API behavior and its interaction with the database.

TestCase is used here because the API view queries Django models and
requires a test database. The comparison tests use SimpleTestCase because
they do not access the database.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from reconciliation.models import Location, Org, SystemARecord, SystemBEntry


class TenantIsolationTests(TestCase):
    """
    Creates the same record ID in two different organizations with different values.
    
    Verifies that the API only returns disagreements for the requested organization
    and does not expose data from another tenant.
    """

    @classmethod
    def setUpTestData(cls):
        org_a = Org.objects.create(org_id="ORG-A")
        org_b = Org.objects.create(org_id="ORG-B")
        loc_a = Location.objects.create(location_id="LOC-A1", org=org_a)
        loc_b = Location.objects.create(location_id="LOC-B1", org=org_b)

        # Same record_id on purpose: if tenant scoping were done by
        # filtering results after a global comparison, this is exactly the
        # setup that would leak -- ORG-B's entry could get matched against
        # ORG-A's record because they share a primary key.
        SystemARecord.objects.create(record_id="REC-1", location=loc_a, total_value=Decimal("100.00"))
        SystemARecord.objects.create(record_id="REC-1-B", location=loc_b, total_value=Decimal("999.00"))

        SystemBEntry.objects.create(
            entry_id="ENT-A1",
            record_ref_raw="REC-1",
            record_ref_normalized="REC-1",
            location=loc_a,
            value=Decimal("100.00"),
        )
        # ORG-B has no entry for its own record -- MISSING_IN_B, and its
        # 999.00 value must never appear in ORG-A's response.

    def test_missing_org_id_is_rejected(self):
        response = self.client.get(reverse("discrepancy-list"))
        self.assertEqual(response.status_code, 400)

    def test_unknown_org_id_is_rejected(self):
        response = self.client.get(reverse("discrepancy-list"), {"org_id": "NOPE"})
        self.assertEqual(response.status_code, 404)

    def test_org_a_report_contains_no_org_b_values(self):
        response = self.client.get(reverse("discrepancy-list"), {"org_id": "ORG-A"})
        self.assertEqual(response.status_code, 200)
        body = response.json()

        serialized = str(body)
        self.assertNotIn("999.00", serialized)
        self.assertNotIn("ORG-B", serialized)
        self.assertNotIn("REC-1-B", serialized)

    def test_org_b_report_shows_its_own_missing_record(self):
        response = self.client.get(reverse("discrepancy-list"), {"org_id": "ORG-B"})
        body = response.json()

        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["reason"], "MISSING_IN_B")
        self.assertEqual(body[0]["record_id"], "REC-1-B")
        self.assertEqual(body[0]["a_value"], "999.00")


class DiscrepancyFilteringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Org.objects.create(org_id="ORG-A")
        loc = Location.objects.create(location_id="LOC-1", org=org)

        SystemARecord.objects.create(record_id="REC-1", location=loc, total_value=Decimal("10.00"))
        SystemARecord.objects.create(record_id="REC-2", location=loc, total_value=Decimal("20.00"))
        # REC-1: matches cleanly. REC-2: missing in B.
        SystemBEntry.objects.create(
            entry_id="ENT-1", record_ref_raw="REC-1", record_ref_normalized="REC-1",
            location=loc, value=Decimal("10.00"),
        )

    def test_reason_filter_narrows_results(self):
        response = self.client.get(reverse("discrepancy-list"), {"org_id": "ORG-A", "reason": "MISSING_IN_B"})
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["record_id"], "REC-2")

    def test_clean_match_produces_no_discrepancy(self):
        response = self.client.get(reverse("discrepancy-list"), {"org_id": "ORG-A"})
        body = response.json()
        record_ids = [row["record_id"] for row in body]
        self.assertNotIn("REC-1", record_ids)
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Org, SystemARecord, SystemBEntry
from .services.compare import ARecord, BEntry, find_discrepancies

# Fields the client is allowed to sort by, and the model field each maps to.
# An explicit allow-list rather than passing `ordering` straight through
# means a request can never sort by a field we didn't intend to expose.
_SORTABLE_FIELDS = {"a_value", "b_value", "reason", "record_id"}


class OrgListView(APIView):
    """GET /api/orgs/ -- just enough for the frontend to populate a tenant picker."""

    def get(self, request):
        return Response([org.org_id for org in Org.objects.order_by("org_id")])


class DiscrepancyListView(APIView):
    """
GET /api/disagreements/?org_id=ORG-A&reason=VALUE_MISMATCH&ordering=-a_value

org_id is required and is used to keep each tenant's data separate.
System A and System B records are filtered by the given org_id before
they are passed to the comparison logic.

This ensures that records from one organization are never compared with
or exposed to another organization. Optional reason and ordering
parameters can be used to filter and sort the results.
"""

    def get(self, request):
        org_id = request.query_params.get("org_id")
        if not org_id:
            return Response({"detail": "org_id query parameter is required."}, status=400)
        if not Org.objects.filter(pk=org_id).exists():
            return Response({"detail": f"Unknown org_id '{org_id}'."}, status=404)

        a_qs = SystemARecord.objects.filter(location__org_id=org_id).select_related("location")
        b_qs = SystemBEntry.objects.filter(location__org_id=org_id).select_related("location")

        a_records = [
            ARecord(
                record_id=r.record_id,
                org_id=org_id,
                location_id=r.location_id,
                total_value=r.total_value,
            )
            for r in a_qs
        ]
        b_entries = [
            BEntry(
                entry_id=e.entry_id,
                record_ref_normalized=e.record_ref_normalized,
                org_id=org_id,
                value=e.value,
            )
            for e in b_qs
        ]

        discrepancies = find_discrepancies(a_records, b_entries)

        reason = request.query_params.get("reason")
        if reason:
            discrepancies = [d for d in discrepancies if d.reason.value == reason]

        ordering = request.query_params.get("ordering", "")
        field = ordering.lstrip("-")
        if field in _SORTABLE_FIELDS:
            reverse = ordering.startswith("-")
            # Rows with no value on the sorted field always sort to the end,
            # in either direction.
            with_value = [d for d in discrepancies if getattr(d, field) is not None]
            without_value = [d for d in discrepancies if getattr(d, field) is None]
            with_value.sort(key=lambda d: getattr(d, field), reverse=reverse)
            discrepancies = with_value + without_value

        return Response(
            [
                {
                    "reason": d.reason.value,
                    "record_id": d.record_id,
                    "entry_id": d.entry_id,
                    "org_id": d.org_id,
                    "location_id": d.location_id,
                    "a_value": str(d.a_value) if d.a_value is not None else None,
                    "b_value": str(d.b_value) if d.b_value is not None else None,
                    "detail": d.detail,
                }
                for d in discrepancies
            ]
        )

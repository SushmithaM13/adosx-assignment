from django.db import models

# Create your models here.

class Org(models.Model):
    """
    A tenant. Everything downstream (locations, records, entries) hangs off
    an org, either directly or through its location. This is the boundary
    the reconciliation view must never cross.
    """

    org_id = models.CharField(max_length=32, primary_key=True)

    def __str__(self):
        return self.org_id


class Location(models.Model):
    """
    locations.csv. Small and clean in this dataset, but it's the join point
    that tells us *which tenant a row belongs to* -- a System A record or
    System B entry doesn't carry an org_id itself, only a location_id, so
    location is where tenant scoping actually happens.
    """

    location_id = models.CharField(max_length=32, primary_key=True)
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="locations")
    name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.location_id} ({self.org_id})"


class SystemARecord(models.Model):
    """
    One row of system_a.csv.

    Every value that can be dirty (dates, numbers, the location reference)
    is stored twice: once as the raw string exactly as it appeared in the
    CSV, and once parsed. If parsing fails, the parsed field is left null
    and the reason goes into `import_issues` -- the row itself is still
    imported. The brief is explicit that dirty rows must survive import,
    just flagged, not skipped, so a parse failure is data to report, not
    a reason to lose the row.
    """

    record_id = models.CharField(max_length=32, primary_key=True)

    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="a_records"
    )
    location_id_raw = models.CharField(max_length=64, blank=True)

    event_date = models.DateField(null=True, blank=True)
    event_date_raw = models.CharField(max_length=64, blank=True)

    category_code = models.CharField(max_length=32, blank=True)
    actor_id = models.CharField(max_length=32, blank=True)

    base_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    adjustment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_value_raw = models.CharField(max_length=64, blank=True)

    state = models.CharField(max_length=32, blank=True)

    import_issues = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["record_id"]

    def __str__(self):
        return self.record_id


class SystemBEntry(models.Model):
    """
    One row of system_b.csv.

    `record_ref_raw` is System B's free-text pointer back to a System A
    record (formats seen in the sample data: "REC-1042", "rec1034",
    "REC - 1070", even a bare "1112"). `record_ref_normalized` is that
    string reduced to a canonical "REC-<digits>" key -- see
    services/compare.py and the import command for exactly how. It is
    intentionally kept even when it doesn't resolve to a real
    SystemARecord, because "points at a record that doesn't exist" is
    itself one of the discrepancies we need to report, not an import
    error to hide.

    `matched_record` is a convenience FK for the common case (admin
    browsing, quick joins) but the comparison logic in services/compare.py
    does NOT rely on it -- it recomputes the match by org-scoped record_id
    lookups so tenant filtering happens in one place.
    """

    entry_id = models.CharField(max_length=32, primary_key=True)

    record_ref_raw = models.CharField(max_length=64)
    record_ref_normalized = models.CharField(max_length=32, null=True, blank=True)
    matched_record = models.ForeignKey(
        SystemARecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="b_entries"
    )

    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="b_entries"
    )
    location_id_raw = models.CharField(max_length=64, blank=True)

    recorded_on = models.DateField(null=True, blank=True)
    recorded_on_raw = models.CharField(max_length=64, blank=True)

    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    value_raw = models.CharField(max_length=64, blank=True)

    label = models.CharField(max_length=255, blank=True)

    import_issues = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["entry_id"]
        verbose_name_plural = "System B entries"

    def __str__(self):
        return self.entry_id
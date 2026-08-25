"""
Usage: python manage.py import_data [--data-dir path/to/csvs]

Loads locations.csv, system_a.csv, system_b.csv into the database.
"""

import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from reconciliation.models import Location, Org, SystemARecord, SystemBEntry


class Command(BaseCommand):
    help = "Imports locations.csv, system_a.csv, and system_b.csv into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=str(Path(settings.BASE_DIR) / "data"),
            help="Directory containing locations.csv, system_a.csv, system_b.csv",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        self._import_locations(data_dir / "locations.csv")
        self._import_system_a(data_dir / "system_a.csv")
        self._import_system_b(data_dir / "system_b.csv")

    def _import_locations(self, path: Path):
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                org, _ = Org.objects.get_or_create(org_id=row["org_id"].strip())
                Location.objects.update_or_create(
                    location_id=row["location_id"].strip(),
                    defaults={"org": org, "name": row.get("location_name", "").strip()},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"locations.csv: imported {count} rows"))

    def _import_system_a(self, path: Path):
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                location = Location.objects.filter(pk=row["location_id"].strip()).first()
                SystemARecord.objects.update_or_create(
                    record_id=row["record_id"].strip(),
                    defaults=dict(
                        location=location,
                        event_date=row.get("event_date", "").strip() or None,
                        category_code=row.get("category_code", "").strip(),
                        actor_id=row.get("actor_id", "").strip(),
                        base_value=row.get("base_value", "").strip() or None,
                        adjustment=row.get("adjustment", "").strip() or None,
                        total_value=row.get("total_value", "").strip() or None,
                        state=row.get("state", "").strip(),
                    ),
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"system_a.csv: imported {count} rows"))

    def _import_system_b(self, path: Path):
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                ref = row["record_ref"].strip()
                matched = SystemARecord.objects.filter(pk=ref).first()
                location = Location.objects.filter(pk=row["location_id"].strip()).first()
                SystemBEntry.objects.update_or_create(
                    entry_id=row["entry_id"].strip(),
                    defaults=dict(
                        record_ref_raw=ref,
                        record_ref_normalized=ref,
                        matched_record=matched,
                        location=location,
                        recorded_on=row.get("recorded_on", "").strip() or None,
                        value=row.get("value", "").strip() or None,
                        label=row.get("label", "").strip(),
                    ),
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"system_b.csv: imported {count} rows"))
"""
Usage: python manage.py import_data [--data-dir path/to/csvs]

Loads locations.csv, system_a.csv, system_b.csv into the database.

Guiding rule: a row with a usable primary key (record_id / entry_id) is
ALWAYS imported, even if every other field on it is garbage. Bad fields are
recorded in that row's import_issues list, not used as a reason to drop the
row -- the discrepancy report is supposed to surface bad data, so the bad
data has to make it into the database first. The only rows this command
actually skips are ones with no primary key at all, since there would be
nothing to attach an issue to or link a B entry against; those are logged
to stderr rather than silently vanishing.

Re-running this command is safe: everything is update_or_create on the
natural key from the CSV, so importing the same files twice just re-syncs
the same rows.
"""

import csv
import re
import datetime as dt
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from reconciliation.models import Location, Org, SystemARecord, SystemBEntry


def parse_decimal(raw: str | None) -> tuple[Decimal | None, str | None]:
    """Returns (value, issue). Handles blanks and thousands-separator commas
    (e.g. "1,25,400.00" in the sample data) by stripping commas before
    parsing -- Decimal has no opinion on grouping, only on the digits."""
    if raw is None:
        return None, None
    text = raw.strip()
    if text == "":
        return None, None
    cleaned = text.replace(",", "")
    try:
        return Decimal(cleaned), None
    except InvalidOperation:
        return None, f"could not parse '{raw}' as a number"


def parse_date(raw: str | None) -> tuple[dt.date | None, str | None]:
    if raw is None:
        return None, None
    text = raw.strip()
    if text == "":
        return None, None
    try:
        return dt.datetime.strptime(text, "%Y-%m-%d").date(), None
    except ValueError:
        return None, f"could not parse '{raw}' as a date (expected YYYY-MM-DD)"


def normalize_ref(raw: str | None) -> str | None:
    """
    Reduces a System B record_ref to a canonical "REC-<digits>" key.

    Sample data shows the same reference written as "REC-1042", "rec1034",
    "REC - 1070", and a bare "1112". Pulling out the first run of digits and
    ignoring everything else (case, dashes, spaces, prefix) handles all four
    with one rule instead of a growing pile of special cases. If a ref has
    no digits in it at all, there's nothing to normalize -- return None and
    let the caller treat it as an orphan reference.
    """
    if raw is None:
        return None
    match = re.search(r"(\d+)", raw)
    if not match:
        return None
    return f"REC-{match.group(1)}"


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
                org_id = (row.get("org_id") or "").strip()
                location_id = (row.get("location_id") or "").strip()
                if not org_id or not location_id:
                    self.stderr.write(self.style.WARNING(f"locations.csv: skipping row missing id: {row}"))
                    continue
                org, _ = Org.objects.get_or_create(org_id=org_id)
                Location.objects.update_or_create(
                    location_id=location_id,
                    defaults={"org": org, "name": (row.get("location_name") or "").strip()},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"locations.csv: imported {count} rows"))

    def _import_system_a(self, path: Path):
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                record_id = (row.get("record_id") or "").strip()
                if not record_id:
                    self.stderr.write(self.style.WARNING(f"system_a.csv: skipping row with no record_id: {row}"))
                    continue

                issues: list[str] = []

                loc_id = (row.get("location_id") or "").strip()
                location = Location.objects.filter(pk=loc_id).first() if loc_id else None
                if loc_id and location is None:
                    issues.append(f"unknown location_id '{loc_id}'")

                event_date, issue = parse_date(row.get("event_date"))
                if issue:
                    issues.append(issue)

                base_value, issue = parse_decimal(row.get("base_value"))
                if issue:
                    issues.append(f"base_value: {issue}")

                adjustment, issue = parse_decimal(row.get("adjustment"))
                if issue:
                    issues.append(f"adjustment: {issue}")

                total_value, issue = parse_decimal(row.get("total_value"))
                if issue:
                    issues.append(f"total_value: {issue}")

                actor_id = (row.get("actor_id") or "").strip()
                if not actor_id:
                    issues.append("actor_id is blank")

                SystemARecord.objects.update_or_create(
                    record_id=record_id,
                    defaults=dict(
                        location=location,
                        location_id_raw=loc_id,
                        event_date=event_date,
                        event_date_raw=(row.get("event_date") or "").strip(),
                        category_code=(row.get("category_code") or "").strip(),
                        actor_id=actor_id,
                        base_value=base_value,
                        adjustment=adjustment,
                        total_value=total_value,
                        total_value_raw=(row.get("total_value") or "").strip(),
                        state=(row.get("state") or "").strip(),
                        import_issues=issues,
                    ),
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"system_a.csv: imported {count} rows"))

    def _import_system_b(self, path: Path):
        count = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                entry_id = (row.get("entry_id") or "").strip()
                if not entry_id:
                    self.stderr.write(self.style.WARNING(f"system_b.csv: skipping row with no entry_id: {row}"))
                    continue

                issues: list[str] = []

                raw_ref = row.get("record_ref") or ""
                normalized_ref = normalize_ref(raw_ref)
                matched = None
                if normalized_ref is None:
                    issues.append(f"record_ref '{raw_ref}' has no digits, could not normalize")
                else:
                    matched = SystemARecord.objects.filter(pk=normalized_ref).first()
                    if matched is None:
                        issues.append(
                            f"record_ref normalizes to '{normalized_ref}', which does not exist in System A"
                        )

                loc_id = (row.get("location_id") or "").strip()
                location = Location.objects.filter(pk=loc_id).first() if loc_id else None
                if loc_id and location is None:
                    issues.append(f"unknown location_id '{loc_id}'")

                recorded_on, issue = parse_date(row.get("recorded_on"))
                if issue:
                    issues.append(issue)

                value_text = (row.get("value") or "").strip()
                value, issue = parse_decimal(row.get("value"))
                if issue:
                    issues.append(issue)
                elif value_text == "":
                    issues.append("value is blank")

                SystemBEntry.objects.update_or_create(
                    entry_id=entry_id,
                    defaults=dict(
                        record_ref_raw=raw_ref.strip(),
                        record_ref_normalized=normalized_ref,
                        matched_record=matched,
                        location=location,
                        location_id_raw=loc_id,
                        recorded_on=recorded_on,
                        recorded_on_raw=(row.get("recorded_on") or "").strip(),
                        value=value,
                        value_raw=(row.get("value") or "").strip(),
                        label=(row.get("label") or "").strip(),
                        import_issues=issues,
                    ),
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"system_b.csv: imported {count} rows"))
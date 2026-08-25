"""
Reconciliation logic for comparing System A and System B records.

This module contains the main comparison logic and does not depend on the
Django ORM or database. It takes ARecord and BEntry objects as input and
returns the detected discrepancies. Keeping this logic separate also makes
it easier to test.

The following discrepancy types are handled:

MISSING_IN_B
    A System A record has no matching entry in System B.

ORPHAN_IN_B
    A System B entry refers to a record that does not exist in System A
    for the current tenant.

DUPLICATE_IN_B
    More than one System B entry refers to the same System A record.

VALUE_MISMATCH
    A matching System B entry exists, but its value is different from
    the System A total value.

UNPARSEABLE_VALUE
    A matching entry exists, but the value from either system cannot be
    parsed as a number.

If a System A record has exactly one matching System B entry and the values
match, no discrepancy is returned.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

# Two values within a cent of each other are treated as equal. This is a
# reconciliation report, not an audit ledger -- rounding from upstream
# systems doing their own decimal math is expected and isn't a discrepancy.
VALUE_TOLERANCE = Decimal("0.01")


class Reason(str, Enum):
    MISSING_IN_B = "MISSING_IN_B"
    ORPHAN_IN_B = "ORPHAN_IN_B"
    DUPLICATE_IN_B = "DUPLICATE_IN_B"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    UNPARSEABLE_VALUE = "UNPARSEABLE_VALUE"


@dataclass(frozen=True)
class ARecord:
    """The subset of a SystemARecord that the comparison actually needs."""

    record_id: str
    org_id: Optional[str]
    location_id: Optional[str]
    total_value: Optional[Decimal]


@dataclass(frozen=True)
class BEntry:
    """The subset of a SystemBEntry that the comparison actually needs."""

    entry_id: str
    record_ref_normalized: Optional[str]
    org_id: Optional[str]
    value: Optional[Decimal]


@dataclass(frozen=True)
class Discrepancy:
    reason: Reason
    record_id: Optional[str]
    entry_id: Optional[str]
    org_id: Optional[str]
    location_id: Optional[str]
    a_value: Optional[Decimal]
    b_value: Optional[Decimal]
    detail: str


def find_discrepancies(a_records: list[ARecord], b_entries: list[BEntry]) -> list[Discrepancy]:
    """
    Callers are expected to have already scoped both lists to a single
    tenant (see reconciliation/views.py). This function does not look at
    org_id to decide what to compare -- it only carries org_id through onto
    the output rows for display. Enforcing the tenant boundary by filtering
    *before* this function is called, rather than filtering its output
    afterwards, is what makes cross-tenant leakage structurally impossible
    rather than something a filter has to remember to do.
    """

    a_by_id = {r.record_id: r for r in a_records}

    entries_by_ref: dict[str, list[BEntry]] = defaultdict(list)
    for entry in b_entries:
        if entry.record_ref_normalized is not None:
            entries_by_ref[entry.record_ref_normalized].append(entry)

    discrepancies: list[Discrepancy] = []

    # --- B entries that don't land on a real record in this tenant ---
    for entry in b_entries:
        ref = entry.record_ref_normalized
        if ref is None or ref not in a_by_id:
            if ref is None:
                detail = "System B entry's record reference could not be parsed."
            else:
                detail = f"System B entry references '{ref}', which does not exist in System A."
            discrepancies.append(
                Discrepancy(
                    reason=Reason.ORPHAN_IN_B,
                    record_id=None,
                    entry_id=entry.entry_id,
                    org_id=entry.org_id,
                    location_id=None,
                    a_value=None,
                    b_value=entry.value,
                    detail=detail,
                )
            )

    # --- Every System A record, checked against its matched entry/entries ---
    for record in a_records:
        matches = entries_by_ref.get(record.record_id, [])

        if len(matches) == 0:
            discrepancies.append(
                Discrepancy(
                    reason=Reason.MISSING_IN_B,
                    record_id=record.record_id,
                    entry_id=None,
                    org_id=record.org_id,
                    location_id=record.location_id,
                    a_value=record.total_value,
                    b_value=None,
                    detail="No System B entry references this record.",
                )
            )
            continue

        if len(matches) > 1:
            entry_ids = ", ".join(m.entry_id for m in matches)
            discrepancies.append(
                Discrepancy(
                    reason=Reason.DUPLICATE_IN_B,
                    record_id=record.record_id,
                    entry_id=entry_ids,
                    org_id=record.org_id,
                    location_id=record.location_id,
                    a_value=record.total_value,
                    b_value=None,
                    detail=(
                        f"{len(matches)} System B entries reference this record: {entry_ids}. "
                        "Their values: " + ", ".join(
                            (str(m.value) if m.value is not None else "unparseable") for m in matches
                        ) + "."
                    ),
                )
            )
            continue

        # Exactly one match: this is the normal, healthy case unless the
        # values disagree or one of them didn't parse.
        entry = matches[0]
        if record.total_value is None or entry.value is None:
            discrepancies.append(
                Discrepancy(
                    reason=Reason.UNPARSEABLE_VALUE,
                    record_id=record.record_id,
                    entry_id=entry.entry_id,
                    org_id=record.org_id,
                    location_id=record.location_id,
                    a_value=record.total_value,
                    b_value=entry.value,
                    detail="One side's value could not be parsed as a number, so it cannot be compared.",
                )
            )
        elif abs(record.total_value - entry.value) > VALUE_TOLERANCE:
            discrepancies.append(
                Discrepancy(
                    reason=Reason.VALUE_MISMATCH,
                    record_id=record.record_id,
                    entry_id=entry.entry_id,
                    org_id=record.org_id,
                    location_id=record.location_id,
                    a_value=record.total_value,
                    b_value=entry.value,
                    detail=f"System A total_value {record.total_value} != System B value {entry.value}.",
                )
            )

    return discrepancies
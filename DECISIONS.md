# Decisions

This file records the main implementation decisions made while building the assignment, the alternatives considered, and why I chose each approach.

## 1. Filter by tenant before comparison

**Decision:** Filter both System A and System B records by `org_id` before running the comparison logic.

**Alternative:** Compare records from all organizations first and filter the disagreements afterward.

**Reasoning:** Filtering before comparison keeps each tenant's data separate throughout the process and prevents records from different organizations from being compared.

## 2. Normalize System B record references

**Decision:** Extract the numeric part of `record_ref` and normalize it to the `REC-<digits>` format.

For example:

- `REC-1042` → `REC-1042`
- `rec1034` → `REC-1034`
- `1112` → `REC-1112`

**Alternative:** Handle each reference format separately with multiple string replacements or special cases.

**Reasoning:** The provided reference formats follow the same basic pattern, so using one normalization rule keeps the importer simpler and also handles similar formatting variations.

## 3. Preserve dirty input values

**Decision:** Keep the original raw value for fields that may contain invalid data and store a parsed value separately when parsing succeeds. Import problems are also recorded instead of dropping the row.

**Alternative:** Store only parsed values and reject rows when parsing fails.

**Reasoning:** The assignment requires dirty rows to survive the import. Preserving the original value also makes parsing problems easier to inspect.

## 4. Keep comparison logic separate from Django models

**Decision:** The main comparison logic works with simple Python objects and does not query the database directly.

**Alternative:** Put the matching and disagreement rules directly into Django ORM queries or API views.

**Reasoning:** Keeping the comparison rules separate from the database makes the logic easier to understand and allows each disagreement case to be tested independently without database setup.

## 5. Treat multiple System B entries as duplicates

**Decision:** If more than one System B entry references the same System A record, report it as `DUPLICATE_IN_B`, even when the values happen to add up to the System A total.

**Alternative:** Ignore duplicates when their combined value matches the System A value.

**Reasoning:** The assignment specifically requires detecting cases where the same record is entered into System B more than once. I therefore kept duplicate detection separate from value comparison.

## 6. Allow a one-cent tolerance when comparing values

**Decision:** Values with a difference of no more than one cent are treated as matching.

**Alternative:** Require exact numeric equality.

**Reasoning:** A small tolerance avoids reporting minor rounding differences as value mismatches while still identifying meaningful differences between the systems.

## 7. Require the tenant in the API request

**Decision:** The disagreements endpoint requires an `org_id` query parameter.

Example:

```text
/api/discrepancies/?org_id=ORG-A
```

**Alternative:** Determine the organization from an authenticated user or session.

**Reasoning:** Authentication is outside the scope of this assignment, so requiring the organization explicitly keeps the tenant behavior simple and testable.

## 8. Keep the frontend simple

**Decision:** Use a simple React interface with native select elements and an HTML table, with basic CSS for styling.

**Alternative:** Add a UI component library or data-grid library.

**Reasoning:** The assignment focuses on correctness and functionality rather than visual design, so I kept the frontend small and focused on the required filtering and sorting features.
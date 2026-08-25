# DealerOS Reconciliation Assignment

A full-stack application that compares System A records with System B entries for each tenant and reports where the two systems disagree.

## What It Does

- Imports three CSV files (`locations.csv`, `system_a.csv`, and `system_b.csv`) into the database.
- Handles dirty data such as different record-reference formats, comma-formatted numbers, blank values, and references to records that do not exist without silently dropping rows.
- Matches System A records with their corresponding System B entries and identifies the following disagreement types:
  - `MISSING_IN_B` — no System B entry references the System A record.
  - `ORPHAN_IN_B` — a System B entry references a record that does not exist in the current tenant.
  - `DUPLICATE_IN_B` — more than one System B entry references the same System A record.
  - `VALUE_MISMATCH` — one matching entry exists, but its value does not match the System A total value.
  - `UNPARSEABLE_VALUE` — one matching entry exists, but a value from either system cannot be parsed as a number.
- Provides a tenant-scoped JSON API with filtering by disagreement reason and sorting by value.
- Provides a small React frontend where the user can select an organization, filter by reason, and sort the System A and System B value columns.

See `DECISIONS.md` for the reasoning behind the main implementation choices.

## Project Layout

```text
backend/
├── config/                         # Django project settings and URLs
├── reconciliation/
│   ├── models.py                   # Org, Location, SystemARecord, SystemBEntry
│   ├── services/
│   │   └── compare.py              # Comparison logic
│   ├── management/
│   │   └── commands/
│   │       └── import_data.py      # CSV import and dirty-data handling
│   ├── views.py                    # API endpoints
│   └── tests/
│       ├── test_compare.py         # Comparison logic tests
│       ├── test_import_data.py     # CSV import tests
│       └── test_views.py           # API and tenant-isolation tests
├── data/                           # Source CSV files
└── manage.py

frontend/
└── src/
    └── App.jsx                     # Org picker, reason filter and results table
```

## Running the Project

### Backend

```bash
cd backend

python -m venv venv
```

Activate the virtual environment on Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the database migrations:

```bash
python manage.py migrate
```

Import the provided CSV data:

```bash
python manage.py import_data
```

Run the tests:

```bash
python manage.py test reconciliation
```

Start the Django development server:

```bash
python manage.py runserver
```

The backend will run at `http://127.0.0.1:8000`.

### Frontend

Open another terminal while keeping the Django server running:

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at `http://localhost:5173`.

The Vite development server proxies `/api/*` requests to the Django server at `127.0.0.1:8000`, as configured in `vite.config.js`.

## What I Built

I implemented the main requirements from the assignment: CSV import, dirty-data handling, record comparison, tenant-scoped APIs, tests, and a React interface for viewing the results.

Before implementing the comparison logic, I inspected the provided CSV files to understand the dirty-data cases. These included:

- Record references written in different formats, such as `REC-1042`, `rec1034`, and a numeric reference such as `1112`.
- A System B reference to a record that does not exist.
- Records with multiple System B entries.
- Values in System B that differ from System A's `total_value`.
- A value formatted with thousands separators.
- A blank System B value.
- Records that could potentially match across different organizations, making tenant isolation important.

The importer preserves the source rows while normalizing the fields needed for comparison.

## What I Deliberately Did Not Build

- **Authentication** — the assignment explicitly lists authentication as out of scope.
- **Pagination** — the provided dataset is small enough that pagination is unnecessary for this implementation.
- **Bulk import optimization** — the current approach is sufficient for the provided dataset, although I would use bulk operations for significantly larger imports.
- **Disagreement resolution/editing** — the application identifies and displays disagreements but does not provide functionality to modify the source data.
- **A UI component library or CSS framework** — I kept the frontend intentionally simple and focused on functionality.

## How I Worked With the AI Agent

I used Claude as an AI assistant while working through the assignment. I used it step by step for areas such as the Django structure, importer, comparison logic, API, tests, and frontend rather than asking it to generate the complete project at once.

I reviewed the generated suggestions, ran the application and tests myself, checked API responses, and verified specific records against the provided CSV files before continuing.

I also documented the main implementation choices and alternatives in `DECISIONS.md`.

### a. Name one thing the AI agent got wrong. How did you notice?

An early version of the comparison tests used plain `assert` statements inside standalone test functions. When I ran:

```bash
python manage.py test
```

Django reported that it found zero tests.

That showed me that the tests were not being discovered by Django's default test runner. I changed them to Django test classes with test methods and assertions such as `self.assertEqual()`, then ran the test suite again to confirm that they were discovered and executed.

### b. Which part of your submission are you least confident about, and why?

The duplicate-handling rule is the part I am least confident about.

The sample data contains a case where multiple System B entries reference the same System A record. I chose to report this as `DUPLICATE_IN_B` whenever more than one System B entry points to the same record because the assignment explicitly asks for this case to be detected.

In a production reconciliation system, I would want to confirm whether some multi-entry cases are valid splits before treating all of them as the same type of disagreement.

### c. If you had a second day, what would you fix first?

I would improve the API response for `DUPLICATE_IN_B`.

Currently, duplicate entries have to fit into the same response structure used by the other disagreement types. A cleaner design would return the matching System B entries as a nested list and let the frontend display each duplicate entry separately.

After that, I would add pagination so the API and frontend can handle a much larger dataset more cleanly.
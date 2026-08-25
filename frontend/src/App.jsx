import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "/api";

const REASONS = [
  "MISSING_IN_B",
  "ORPHAN_IN_B",
  "DUPLICATE_IN_B",
  "VALUE_MISMATCH",
  "UNPARSEABLE_VALUE",
];

function App() {
  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState("");
  const [reason, setReason] = useState("");
  const [ordering, setOrdering] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Orgs are fetched once, on mount, purely to populate the tenant picker.
  useEffect(() => {
    fetch(`${API_BASE}/orgs/`)
      .then((res) => res.json())
      .then((data) => {
        setOrgs(data);
        if (data.length > 0) setOrgId(data[0]);
      })
      .catch(() => setError("Could not reach the API. Is the Django server running?"));
  }, []);

  // Re-fetch discrepancies whenever the tenant, filter, or sort changes.
  useEffect(() => {
    if (!orgId) return;

    const params = new URLSearchParams({ org_id: orgId });
    if (reason) params.set("reason", reason);
    if (ordering) params.set("ordering", ordering);

    
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/discrepancies/?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        return res.json();
      })
      .then(setRows)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [orgId, reason, ordering]);

  const toggleValueSort = (field) => {
    setOrdering((current) => {
      if (current === field) return `-${field}`;
      if (current === `-${field}`) return "";
      return field;
    });
  };

  const sortIndicator = (field) => {
    if (ordering === field) return " \u2191";
    if (ordering === `-${field}`) return " \u2193";
    return "";
  };

  const summary = useMemo(() => {
    if (loading) return "Loading...";
    if (rows.length === 0) return "No discrepancies found for this selection.";
    return `${rows.length} discrepanc${rows.length === 1 ? "y" : "ies"}`;
  }, [rows, loading]);

  return (
    <div className="page">
      <header>
        <h1>DealerOS Reconciliation</h1>
        <p className="subtitle">System A vs. System B, per tenant.</p>
      </header>

      <div className="controls">
        <label>
          Org
          <select value={orgId} onChange={(e) => setOrgId(e.target.value)}>
            {orgs.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>

        <label>
          Reason
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="">All reasons</option>
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>

        <span className="summary">{summary}</span>
      </div>

      {error && <p className="error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Reason</th>
            <th>Record</th>
            <th>Entry</th>
            <th>Location</th>
            <th onClick={() => toggleValueSort("a_value")} className="sortable">
              System A value{sortIndicator("a_value")}
            </th>
            <th onClick={() => toggleValueSort("b_value")} className="sortable">
              System B value{sortIndicator("b_value")}
            </th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${row.record_id ?? ""}-${row.entry_id ?? ""}-${i}`}>
              <td>
                <span className={`badge badge-${row.reason}`}>{row.reason}</span>
              </td>
              <td>{row.record_id ?? "\u2014"}</td>
              <td>{row.entry_id ?? "\u2014"}</td>
              <td>{row.location_id ?? "\u2014"}</td>
              <td className="num">{row.a_value ?? "\u2014"}</td>
              <td className="num">{row.b_value ?? "\u2014"}</td>
              <td className="detail">{row.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
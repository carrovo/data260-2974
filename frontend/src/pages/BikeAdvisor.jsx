import { useState } from "react";
import { Link } from "react-router-dom";

import { analyzeBikeMembership } from "../api";


const OFFICIAL_PRICING_URL =
  "https://www.lyft.com/bikes/bay-wheels/pricing";


function money(value) {
  return `$${Number(value).toFixed(2)}`;
}


export default function BikeAdvisor() {
  const [csvFile, setCsvFile] = useState(null);
  const [pricingUrl, setPricingUrl] = useState(OFFICIAL_PRICING_URL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState(null);


  async function handleSubmit(event) {
    event.preventDefault();
    if (!csvFile) {
      setError("Choose a CSV file first.");
      return;
    }

    setLoading(true);
    setError("");
    setAnalysis(null);
    try {
      setAnalysis(await analyzeBikeMembership(csvFile, pricingUrl));
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(
        detail?.message ||
        (typeof detail === "string" ? detail : null) ||
        "The analysis could not be completed.",
      );
    } finally {
      setLoading(false);
    }
  }


  const result = analysis?.result;

  return (
    <section>
      <div className="page-heading-row">
        <div>
          <h2>Bike Membership Advisor</h2>
          <p>
            Analyze only the CSV rows marked as the scenario target.
          </p>
        </div>
        <Link className="button-link secondary-button" to="/">
          Rental Listings
        </Link>
      </div>

      <form className="form-card advisor-form" onSubmit={handleSubmit}>
        <label>
          Bay Wheels scenario CSV
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
          />
        </label>

        <label>
          Official pricing URL
          <input
            type="url"
            value={pricingUrl}
            onChange={(event) => setPricingUrl(event.target.value)}
            required
          />
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Running bounded analysis..." : "Run Analysis"}
        </button>
      </form>

      {error && <p className="error-message">{error}</p>}

      {analysis && result && (
        <>
          <section className="advisor-result">
            <h3>{result.recommendation}</h3>
            <div className="metric-grid">
              <p><strong>Membership:</strong> {money(result.membership_cost)}</p>
              <p><strong>Pay per use:</strong> {money(result.pay_per_use_cost)}</p>
              <p><strong>Savings:</strong> {money(result.dollar_savings)}</p>
              <p><strong>Target rides:</strong> {result.target_ride_count}</p>
              <p><strong>Target minutes:</strong> {result.target_minutes}</p>
              <p><strong>Average ride:</strong> {result.average_target_minutes} minutes</p>
              <p><strong>Classic / ebike:</strong> {result.classic_target_count} / {result.ebike_target_count}</p>
            </div>
            <p><strong>Stop reason:</strong> {analysis.stop_reason}</p>
            <p>
              <strong>Model / tool calls:</strong>{" "}
              {analysis.metrics.model_calls} / {analysis.metrics.tool_calls}
            </p>
            <p><strong>Total tokens:</strong> {analysis.metrics.total_tokens}</p>
            <p>
              <strong>Progress repairs:</strong>{" "}
              {analysis.metrics.progress_repair_count}
            </p>

            <h4>Assumptions</h4>
            <ul>
              {result.assumptions.map((assumption) => (
                <li key={assumption}>{assumption}</li>
              ))}
            </ul>

            <h4>Official citations</h4>
            <p><a href={result.official_source_url}>{result.official_source_url}</a></p>
            <ul>
              {result.citations.map((citation) => (
                <li key={citation}><q>{citation}</q></li>
              ))}
            </ul>
          </section>

          <section className="advisor-panel">
            <h3>Weekly target rides</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Week</th><th>Rides</th><th>Minutes</th></tr>
                </thead>
                <tbody>
                  {result.weekly_table.map((row) => (
                    <tr key={row.week}>
                      <td>{row.week}</td>
                      <td>{row.target_rides}</td>
                      <td>{row.target_minutes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="advisor-panel">
            <h3>Tool timeline</h3>
            <ol className="tool-timeline">
              {analysis.timeline.map((event, index) => (
                <li key={`${event.tool}-${index}`}>
                  <strong>{event.tool}</strong> — {event.success ? "success" : "failed"}
                  {event.source && <> — source: {event.source}</>}
                  <> — {event.latency_ms} ms</>
                  <details>
                    <summary>Safe inputs</summary>
                    <pre>{JSON.stringify(event.inputs, null, 2)}</pre>
                  </details>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </section>
  );
}

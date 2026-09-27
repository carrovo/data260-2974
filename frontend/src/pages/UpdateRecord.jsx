import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getListingById, updateListing } from "../api";

export default function UpdateRecord({ onUpdated }) {
  const { id } = useParams();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    listingTitle: "",
    address: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Load the existing listing before editing.
  useEffect(() => {
    let active = true;

    async function loadListing() {
      try {
        const data = await getListingById(id);

        if (active) {
          setForm({
            listingTitle: data.listingTitle,
            address: data.address,
          });
        }
      } catch (err) {
        if (active) {
          setError(
            err.response?.data?.detail || "Could not load the listing."
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadListing();

    // Prevent state updates after leaving the page.
    return () => {
      active = false;
    };
  }, [id]);

  // Update one form field.
  function handleChange(event) {
    const { name, value } = event.target;

    setForm((current) => ({
      ...current,
      [name]: value,
    }));
  }

  // Submit the PUT request.
  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const updatedListing = await updateListing(id, form);

      onUpdated(updatedListing);
      navigate("/");
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not update the listing."
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p>Loading listing...</p>;
  }

  return (
    <section className="form-card">
      <h2>Update Listing</h2>

      {error && <p className="error-message">{error}</p>}

      <form onSubmit={handleSubmit}>
        <label>
          Listing title
          <input
            name="listingTitle"
            value={form.listingTitle}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Address
          <input
            name="address"
            value={form.address}
            onChange={handleChange}
            required
          />
        </label>

        <div className="form-actions">
          <button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Update Listing"}
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={() => navigate("/")}
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
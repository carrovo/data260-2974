import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createListing } from "../api";


export default function CreateRecord({ onCreated }) {
  const navigate = useNavigate();

  const [listingTitle, setListingTitle] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setLoading(true);

    try {
      // The backend supplies default values for the remaining fields.
      const createdListing = await createListing({
        listingTitle,
        address,
      });

      onCreated(createdListing);
      navigate("/");
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(detail || "Unable to create the listing.");
    } finally {
      setLoading(false);
    }
  }


  return (
    <main className="page-container">
      <section className="card">
        <h1>Add Rental Listing</h1>
        <p className="subtitle">
          Enter the primary and secondary listing fields.
        </p>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label htmlFor="listingTitle">
            Listing Title
          </label>

          <input
            id="listingTitle"
            type="text"
            value={listingTitle}
            onChange={(event) => {
              setListingTitle(event.target.value);
            }}
            placeholder="Example: Studio Near SJSU"
            required
          />

          <label htmlFor="address">
            Address
          </label>

          <input
            id="address"
            type="text"
            value={address}
            onChange={(event) => {
              setAddress(event.target.value);
            }}
            placeholder="Example: 101 S 1st Street, San Jose"
            required
          />

          <div className="action-row">
            <button
              type="submit"
              disabled={loading}
            >
              {loading ? "Creating..." : "Add Listing"}
            </button>

            <button
              type="button"
              className="secondary"
              onClick={() => navigate("/")}
            >
              Cancel
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
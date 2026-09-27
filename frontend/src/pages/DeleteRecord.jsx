import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteListing } from "../api";

export default function DeleteRecord({ onDeleted }) {
  const { id } = useParams();
  const navigate = useNavigate();

  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  // Delete the selected listing.
  async function handleDelete() {
    setDeleting(true);
    setError("");

    try {
      await deleteListing(id);

      onDeleted(Number(id));
      navigate("/");
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not delete the listing."
      );
      setDeleting(false);
    }
  }

  return (
    <section className="form-card">
      <h2>Delete Listing</h2>

      <p>Are you sure you want to delete listing #{id}?</p>

      {error && <p className="error-message">{error}</p>}

      <div className="form-actions">
        <button
          className="danger-button"
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? "Deleting..." : "Yes, Delete"}
        </button>

        <button
          type="button"
          className="secondary-button"
          onClick={() => navigate("/")}
        >
          Cancel
        </button>
      </div>
    </section>
  );
}
import { useEffect } from "react";
import {
  useDispatch,
  useSelector,
} from "react-redux";
import { Link } from "react-router-dom";

import {
  deleteListing,
  fetchListings,
} from "../features/listings/listingsSlice";


export default function Home({ user }) {
  const dispatch = useDispatch();

  const {
    items,
    loading,
    saving,
    initialized,
    error,
  } = useSelector((state) => state.listings);


  useEffect(() => {
    if (!initialized && !loading) {
      dispatch(fetchListings());
    }
  }, [dispatch, initialized, loading]);


  async function handleDelete(listingId) {
    const confirmed = window.confirm(
      `Delete rental listing #${listingId}?`,
    );

    if (!confirmed) {
      return;
    }

    await dispatch(deleteListing(listingId));
  }


  return (
    <section>
      <h2>Rental Housing Listings</h2>

      <p>
        Welcome, {user?.name || user?.email}.
      </p>

      <div className="page-actions">
        <Link
          className="button-link"
          to="/create"
        >
          Add Listing
        </Link>

        <button
          className="secondary-button"
          onClick={() => dispatch(fetchListings())}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {loading && (
        <p>Loading listings from Redux...</p>
      )}

      {error && (
        <p className="error-message">
          {error}
        </p>
      )}

      {!loading && items.length === 0 && (
        <p className="empty-message">
          No rental listings found.
        </p>
      )}

      {!loading &&
        items.map((listing) => (
          <article
            className="listing-card"
            key={listing.id}
          >
            <h3>{listing.listingTitle}</h3>

            <p>
              <strong>ID:</strong> {listing.id}
            </p>

            <p>
              <strong>Code:</strong> {listing.listingCode}
            </p>

            <p>
              <strong>Address:</strong> {listing.address}
            </p>

            <p>
              <strong>Type:</strong> {listing.propertyType}
            </p>

            <p>
              <strong>Monthly rent:</strong>{" "}
              ${Number(listing.monthlyRent).toFixed(2)}
            </p>

            <p>
              <strong>Available units:</strong>{" "}
              {listing.availableUnits}
            </p>

            <p>
              <strong>Property manager ID:</strong>{" "}
              {listing.propertyManagerId}
            </p>

            <p>{listing.description}</p>

            <div className="listing-actions">
              <Link
                className="button-link"
                to={`/update/${listing.id}`}
              >
                Update
              </Link>

              <button
                className="danger-button"
                onClick={() => {
                  handleDelete(listing.id);
                }}
                disabled={saving}
              >
                Delete
              </button>
            </div>
          </article>
        ))}
    </section>
  );
}
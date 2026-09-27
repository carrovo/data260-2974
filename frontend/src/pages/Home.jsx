import { Link } from "react-router-dom";

export default function Home({ user, listings, loading }) {
  return (
    <section>
      <h2>Rental Housing Listings</h2>

      <p>
        Welcome, {user?.name || user?.email}.
      </p>

      <Link className="button-link" to="/create">
        Add Listing
      </Link>

      {loading && <p>Loading listings...</p>}

      {!loading && listings.length === 0 && (
        <p className="empty-message">
          No rental listings found.
        </p>
      )}

      {!loading &&
        listings.map((listing) => (
          <article className="listing-card" key={listing.id}>
            <h3>{listing.listingTitle}</h3>

            <p>ID: {listing.id}</p>
            <p>{listing.address}</p>
            <p>Type: {listing.propertyType}</p>
            <p>{listing.description}</p>
            <p>
              Related events: {listing.events?.length || 0}
            </p>

            {/* Keep action links separated with consistent spacing. */}
            <div className="listing-actions">
              <Link
                className="button-link"
                to={`/update/${listing.id}`}
              >
                Update
              </Link>

              <Link
                className="danger-link"
                to={`/delete/${listing.id}`}
              >
                Delete
              </Link>
            </div>
          </article>
        ))}
    </section>
  );
}
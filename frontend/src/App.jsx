import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import {
  getCurrentUser,
  getListings,
  logoutUser,
} from "./api";

import Login from "./pages/Login";
import Home from "./pages/Home";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";
import DeleteRecord from "./pages/DeleteRecord";

// Protect pages that require login.
function RequireAuth({ user, loading, children }) {
  if (loading) {
    return <p>Checking login session...</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  const navigate = useNavigate();

  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [listings, setListings] = useState([]);
  const [listingsLoading, setListingsLoading] = useState(false);

  // Check the existing session when the app starts.
  useEffect(() => {
    async function checkSession() {
      try {
        const currentUser = await getCurrentUser();
        setUser(currentUser);
      } catch {
        setUser(null);
      } finally {
        setAuthLoading(false);
      }
    }

    checkSession();
  }, []);

  // Load listings after a valid session is found.
  useEffect(() => {
    if (!user) {
      setListings([]);
      return;
    }

    async function loadListings() {
      setListingsLoading(true);

      try {
        const data = await getListings();
        setListings(data);
      } catch {
        setListings([]);
      } finally {
        setListingsLoading(false);
      }
    }

    loadListings();
  }, [user]);

  // Refresh user information after login.
  async function handleLogin() {
    const currentUser = await getCurrentUser();
    setUser(currentUser);
  }

  // Clear the server session and return to login.
  async function handleLogout() {
    await logoutUser();
    setUser(null);
    setListings([]);
    navigate("/login");
  }

  // Add the newly created listing to the current list.
  function handleCreated(newListing) {
    setListings((current) => [...current, newListing]);
  }

  // Replace the edited listing in the current list.
  function handleUpdated(updatedListing) {
    setListings((current) =>
      current.map((listing) =>
        listing.id === updatedListing.id ? updatedListing : listing
      )
    );
  }

  // Remove the deleted listing from the current list.
  function handleDeleted(deletedId) {
    setListings((current) =>
      current.filter((listing) => listing.id !== deletedId)
    );
  }

  return (
    <main className="app-container">
      <header className="app-header">
        <h1>Rental Housing Listings</h1>

        {user && (
          <div className="user-area">
            <span>Welcome, {user.name}</span>
            <button onClick={handleLogout}>Log out</button>
          </div>
        )}
      </header>

      <Routes>
        <Route
          path="/login"
          element={
            user ? (
              <Navigate to="/" replace />
            ) : (
              <Login onLogin={handleLogin} />
            )
          }
        />

        <Route
          path="/"
          element={
            <RequireAuth user={user} loading={authLoading}>
              <Home
                user={user}
                listings={listings}
                loading={listingsLoading}
              />
            </RequireAuth>
          }
        />

        <Route
          path="/create"
          element={
            <RequireAuth user={user} loading={authLoading}>
              <CreateRecord onCreated={handleCreated} />
            </RequireAuth>
          }
        />

        <Route
          path="/update/:id"
          element={
            <RequireAuth user={user} loading={authLoading}>
              <UpdateRecord onUpdated={handleUpdated} />
            </RequireAuth>
          }
        />

        <Route
          path="/delete/:id"
          element={
            <RequireAuth user={user} loading={authLoading}>
              <DeleteRecord onDeleted={handleDeleted} />
            </RequireAuth>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
  );
}
import { useDispatch } from "react-redux";
import { resetListings } from "./features/listings/listingsSlice";
import { useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";

import {
  getCurrentUser,
  logoutUser,
} from "./api";

import Login from "./pages/Login";
import Home from "./pages/Home";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";


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
  const dispatch = useDispatch();

  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);


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


  async function handleLogin() {
    const currentUser = await getCurrentUser();
    setUser(currentUser);
  }


  async function handleLogout() {
    await logoutUser();
    dispatch(resetListings());
    setUser(null);
    navigate("/login");
  }


  return (
    <main className="app-container">
      <header className="app-header">
        <h1>Rental Housing Listings</h1>

        {user && (
          <div className="user-area">
            <span>Welcome, {user.name}</span>

            <button onClick={handleLogout}>
              Log out
            </button>
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
            <RequireAuth
              user={user}
              loading={authLoading}
            >
              <Home user={user} />
            </RequireAuth>
          }
        />

        <Route
          path="/create"
          element={
            <RequireAuth
              user={user}
              loading={authLoading}
            >
              <CreateRecord />
            </RequireAuth>
          }
        />

        <Route
          path="/update/:id"
          element={
            <RequireAuth
              user={user}
              loading={authLoading}
            >
              <UpdateRecord />
            </RequireAuth>
          }
        />

        <Route
          path="*"
          element={<Navigate to="/" replace />}
        />
      </Routes>
    </main>
  );
}
import { useDispatch } from "react-redux";
import { resetListings } from "./features/listings/listingsSlice";
import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";

import {
  AUTH_UNAUTHORIZED_EVENT,
  getCurrentUser,
  getStoredAccessToken,
  logoutUser,
} from "./api";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";
import BikeAdvisor from "./pages/BikeAdvisor";


function RequireAuth({ user, loading, children }) {
  if (loading) {
    return <p>Checking authentication...</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}


function RequireRole({ user, loading, roles, children }) {
  if (loading) {
    return <p>Checking authentication...</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}


export default function App() {
  const navigate = useNavigate();
  const dispatch = useDispatch();

  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);


  useEffect(() => {
    let active = true;

    function handleUnauthorized() {
      if (!active) {
        return;
      }

      dispatch(resetListings());
      setUser(null);
      setAuthLoading(false);
      navigate("/login?reason=session-expired", {
        replace: true,
      });
    }

    async function restoreAuthentication() {
      if (!getStoredAccessToken()) {
        setAuthLoading(false);
        return;
      }

      try {
        const currentUser = await getCurrentUser();

        if (active) {
          setUser(currentUser);
        }
      } catch {
        if (active) {
          setUser(null);
        }
      } finally {
        if (active) {
          setAuthLoading(false);
        }
      }
    }

    window.addEventListener(
      AUTH_UNAUTHORIZED_EVENT,
      handleUnauthorized,
    );
    restoreAuthentication();

    return () => {
      active = false;
      window.removeEventListener(
        AUTH_UNAUTHORIZED_EVENT,
        handleUnauthorized,
      );
    };
  }, [dispatch, navigate]);


  async function handleLogin() {
    const currentUser = await getCurrentUser();

    dispatch(resetListings());
    setUser(currentUser);
  }


  function handleLogout() {
    logoutUser();
    dispatch(resetListings());
    setUser(null);
    navigate("/login", { replace: true });
  }


  return (
    <main className="app-container">
      <header className="app-header">
        <h1>Rental Housing Listings</h1>

        {user && (
          <div className="user-area">
            <span>
              Welcome, {user.name} ({user.role})
            </span>

            <button onClick={handleLogout}>
              Log out
            </button>
          </div>
        )}
      </header>

      {user && (
        <nav className="main-nav" aria-label="Application navigation">
          <Link to="/">Rental Listings</Link>
          <Link to="/bike-advisor">Bike Membership Advisor</Link>
        </nav>
      )}

      <Routes>
        <Route
          path="/bike-advisor"
          element={
            <RequireAuth user={user} loading={authLoading}>
              <BikeAdvisor />
            </RequireAuth>
          }
        />

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
          path="/register"
          element={
            user ? (
              <Navigate to="/" replace />
            ) : (
              <Register />
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
            <RequireRole
              user={user}
              loading={authLoading}
              roles={["writer", "moderator"]}
            >
              <CreateRecord />
            </RequireRole>
          }
        />

        <Route
          path="/update/:id"
          element={
            <RequireRole
              user={user}
              loading={authLoading}
              roles={["writer", "moderator"]}
            >
              <UpdateRecord />
            </RequireRole>
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

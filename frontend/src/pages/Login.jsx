import { useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";

import { loginUser } from "../api";

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Submit the login form.
  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setLoading(true);

    try {
      await loginUser({
        username,
        password,
      });

      // Verify the token and load the current database role.
      await onLogin();

      navigate("/");
    } catch (requestError) {
      // Display a readable backend error message.
      const detail = requestError.response?.data?.detail;

      setError(
        detail || "Login failed. Please check your credentials."
      );
    } finally {
      setLoading(false);
    }
  }


  const sessionExpired = (
    searchParams.get("reason") === "session-expired"
  );
  const registrationComplete = Boolean(
    location.state?.registrationComplete,
  );

  return (
    <main className="page-container">
      <section className="card">
        <h1>Login</h1>

        <p className="subtitle">
          Sign in to manage rental housing listings.
        </p>

        {sessionExpired && !error && (
          <div className="error-message">
            Your login is no longer valid. Please sign in again.
          </div>
        )}

        {registrationComplete && (
          <div className="success-message">
            Account created as a reader. You can now sign in.
          </div>
        )}

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label htmlFor="username">
            Username
          </label>

          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />

          <label htmlFor="password">
            Password
          </label>

          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />

          <button
            type="submit"
            disabled={loading}
          >
            {loading ? "Logging in..." : "Login"}
          </button>
        </form>

        <p>
          Need an account? <Link to="/register">Register</Link>
        </p>
      </section>
    </main>
  );
}

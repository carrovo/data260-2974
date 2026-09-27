import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { loginUser } from "../api";

export default function Login({ onLogin }) {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Submit the login form.
  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setLoading(true);

    try {
      // The browser stores the HTTP-only session cookie.
      const loginResult = await loginUser({
        email,
        password,
      });

      // Wait until App.jsx confirms the current user.
      await onLogin(loginResult);

      // Navigate only after the session is ready.
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

  return (
    <main className="page-container">
      <section className="card">
        <h1>Login</h1>

        <p className="subtitle">
          Sign in to manage rental housing listings.
        </p>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label htmlFor="email">
            Email
          </label>

          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
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
      </section>
    </main>
  );
}
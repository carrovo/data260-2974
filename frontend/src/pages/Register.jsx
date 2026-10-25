import { useState } from "react";
import {
  Link,
  useNavigate,
} from "react-router-dom";

import { registerUser } from "../api";


export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    username: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);


  function handleChange(event) {
    const { name, value } = event.target;

    setForm((current) => ({
      ...current,
      [name]: value,
    }));
  }


  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaving(true);

    try {
      await registerUser(form);
      navigate("/login", {
        replace: true,
        state: {
          registrationComplete: true,
        },
      });
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;

      if (typeof detail === "string") {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(
          detail.map((item) => item.msg).join("; "),
        );
      } else {
        setError("Registration failed. Please check the form.");
      }
    } finally {
      setSaving(false);
    }
  }


  return (
    <section className="form-card">
      <h2>Create Reader Account</h2>

      <p>
        Public registration creates a reader account. Elevated roles
        are assigned only through controlled administration.
      </p>

      {error && (
        <p className="error-message">{error}</p>
      )}

      <form onSubmit={handleSubmit}>
        <label>
          Name
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            autoComplete="name"
            maxLength="100"
            required
          />
        </label>

        <label>
          Email
          <input
            name="email"
            type="email"
            value={form.email}
            onChange={handleChange}
            autoComplete="email"
            required
          />
        </label>

        <label>
          Username
          <input
            name="username"
            value={form.username}
            onChange={handleChange}
            autoComplete="username"
            minLength="3"
            maxLength="100"
            pattern="[A-Za-z0-9_.-]+"
            required
          />
        </label>

        <label>
          Password
          <input
            name="password"
            type="password"
            value={form.password}
            onChange={handleChange}
            autoComplete="new-password"
            minLength="8"
            maxLength="72"
            required
          />
        </label>

        <button type="submit" disabled={saving}>
          {saving ? "Creating account..." : "Register"}
        </button>
      </form>

      <p>
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </section>
  );
}

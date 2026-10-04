import {
  useEffect,
  useState,
} from "react";
import {
  useDispatch,
  useSelector,
} from "react-redux";
import { useNavigate } from "react-router-dom";

import {
  clearListingError,
  createListing,
} from "../features/listings/listingsSlice";
import { getPropertyManagers } from "../api";


const INITIAL_FORM = {
  listingTitle: "",
  listingCode: "",
  address: "",
  submitterEmail: "xuanhua.hw5.2974@example.com",
  description:
    "A rental listing created through the HW5 Redux application.",
  propertyType: "Apartment",
  monthlyRent: "",
  availableUnits: 1,
  termsAccepted: true,
  propertyManagerId: "",
};


function getRequestError(error, fallbackMessage) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  return error.message || fallbackMessage;
}


export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const {
    saving,
    error: reduxError,
  } = useSelector((state) => state.listings);

  const [form, setForm] = useState(INITIAL_FORM);
  const [managers, setManagers] = useState([]);
  const [localError, setLocalError] = useState("");


  useEffect(() => {
    let active = true;

    dispatch(clearListingError());

    async function loadManagers() {
      try {
        const data = await getPropertyManagers();

        if (!active) {
          return;
        }

        setManagers(data);

        if (data.length > 0) {
          setForm((current) => ({
            ...current,
            propertyManagerId: String(data[0].id),
          }));
        }
      } catch (error) {
        if (active) {
          setLocalError(
            getRequestError(
              error,
              "Unable to load property managers.",
            ),
          );
        }
      }
    }

    loadManagers();

    return () => {
      active = false;
    };
  }, [dispatch]);


  function handleChange(event) {
    const {
      name,
      type,
      checked,
      value,
    } = event.target;

    setForm((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : value,
    }));
  }


  async function handleSubmit(event) {
    event.preventDefault();
    setLocalError("");

    if (!form.propertyManagerId) {
      setLocalError(
        "Create a property manager before adding a listing.",
      );
      return;
    }

    const payload = {
      ...form,
      monthlyRent: Number(form.monthlyRent),
      availableUnits: Number(form.availableUnits),
      propertyManagerId: Number(form.propertyManagerId),
    };

    try {
      await dispatch(
        createListing(payload),
      ).unwrap();

      navigate("/");
    } catch {
      // Redux stores the readable error message.
    }
  }


  const displayedError = localError || reduxError;


  return (
    <section className="form-card">
      <h2>Create Rental Listing</h2>

      <p>
        Add a listing and associate it with a property manager.
      </p>

      {displayedError && (
        <p className="error-message">
          {displayedError}
        </p>
      )}

      <form onSubmit={handleSubmit}>
        <label>
          Listing title
          <input
            name="listingTitle"
            value={form.listingTitle}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Listing code
          <input
            name="listingCode"
            value={form.listingCode}
            onChange={handleChange}
            placeholder="Example: S2974-DEMO-01"
            pattern="[A-Za-z0-9-]+"
            required
          />
        </label>

        <label>
          Address
          <input
            name="address"
            value={form.address}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Submitter email
          <input
            name="submitterEmail"
            type="email"
            value={form.submitterEmail}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Description
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            minLength="26"
            rows="4"
            required
          />
        </label>

        <label>
          Property type
          <select
            name="propertyType"
            value={form.propertyType}
            onChange={handleChange}
          >
            <option value="Apartment">Apartment</option>
            <option value="House">House</option>
            <option value="Studio">Studio</option>
            <option value="Shared Room">Shared Room</option>
          </select>
        </label>

        <label>
          Monthly rent
          <input
            name="monthlyRent"
            type="number"
            min="0.01"
            step="0.01"
            value={form.monthlyRent}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Available units
          <input
            name="availableUnits"
            type="number"
            min="0"
            step="1"
            value={form.availableUnits}
            onChange={handleChange}
            required
          />
        </label>

        <label>
          Property manager
          <select
            name="propertyManagerId"
            value={form.propertyManagerId}
            onChange={handleChange}
            disabled={managers.length === 0}
            required
          >
            {managers.length === 0 && (
              <option value="">
                No property managers available
              </option>
            )}

            {managers.map((manager) => (
              <option
                key={manager.id}
                value={manager.id}
              >
                {manager.id} - {manager.firstName}{" "}
                {manager.lastName}
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox-label">
          <input
            name="termsAccepted"
            type="checkbox"
            checked={form.termsAccepted}
            onChange={handleChange}
            required
          />
          Terms accepted
        </label>

        <div className="form-actions">
          <button
            type="submit"
            disabled={
              saving ||
              managers.length === 0
            }
          >
            {saving ? "Creating..." : "Create Listing"}
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={() => navigate("/")}
            disabled={saving}
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
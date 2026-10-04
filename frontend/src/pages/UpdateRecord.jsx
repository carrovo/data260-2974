import {
  useEffect,
  useState,
} from "react";
import {
  useDispatch,
  useSelector,
} from "react-redux";
import {
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  clearListingError,
  updateListing,
} from "../features/listings/listingsSlice";
import {
  getListingById,
  getPropertyManagers,
} from "../api";


function getRequestError(error, fallbackMessage) {
  const detail = error.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  return error.message || fallbackMessage;
}


export default function UpdateRecord() {
  const { id } = useParams();
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const {
    saving,
    error: reduxError,
  } = useSelector((state) => state.listings);

  const [form, setForm] = useState({
    listingTitle: "",
    listingCode: "",
    address: "",
    submitterEmail: "",
    description: "",
    propertyType: "Apartment",
    monthlyRent: "",
    availableUnits: 0,
    termsAccepted: true,
    propertyManagerId: "",
  });

  const [managers, setManagers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [localError, setLocalError] = useState("");


  useEffect(() => {
    let active = true;

    dispatch(clearListingError());

    async function loadPageData() {
      try {
        const [
          listing,
          managerData,
        ] = await Promise.all([
          getListingById(id),
          getPropertyManagers(),
        ]);

        if (!active) {
          return;
        }

        setManagers(managerData);

        setForm({
          listingTitle: listing.listingTitle,
          listingCode: listing.listingCode,
          address: listing.address,
          submitterEmail: listing.submitterEmail,
          description: listing.description,
          propertyType: listing.propertyType,
          monthlyRent: listing.monthlyRent,
          availableUnits: listing.availableUnits,
          termsAccepted: listing.termsAccepted,
          propertyManagerId: String(
            listing.propertyManagerId,
          ),
        });
      } catch (error) {
        if (active) {
          setLocalError(
            getRequestError(
              error,
              "Unable to load the rental listing.",
            ),
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadPageData();

    return () => {
      active = false;
    };
  }, [dispatch, id]);


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

    const payload = {
      ...form,
      monthlyRent: Number(form.monthlyRent),
      availableUnits: Number(form.availableUnits),
      propertyManagerId: Number(form.propertyManagerId),
    };

    try {
      await dispatch(
        updateListing({
          listingId: Number(id),
          payload,
        }),
      ).unwrap();

      navigate("/");
    } catch {
      // Redux stores the readable error message.
    }
  }


  if (loading) {
    return <p>Loading listing and property managers...</p>;
  }


  const displayedError = localError || reduxError;


  return (
    <section className="form-card">
      <h2>Update Rental Listing #{id}</h2>

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
            required
          >
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
            disabled={saving}
          >
            {saving ? "Saving..." : "Update Listing"}
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
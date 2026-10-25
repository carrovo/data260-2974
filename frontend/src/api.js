import axios from "axios";


export const AUTH_UNAUTHORIZED_EVENT = "auth:unauthorized";
export const TOKEN_STORAGE_KEY = "hw7_access_token";


export function getStoredAccessToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}


export function storeAccessToken(token) {
  if (typeof token !== "string" || !token.trim()) {
    throw new Error("The login response did not include an access token.");
  }

  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}


export function clearAccessToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}


const api = axios.create({
  baseURL: "http://localhost:8274",
  headers: {
    "Content-Type": "application/json",
  },
});


api.interceptors.request.use((config) => {
  const token = getStoredAccessToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});


api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const hadToken = Boolean(getStoredAccessToken());

      clearAccessToken();

      if (hadToken) {
        window.dispatchEvent(
          new Event(AUTH_UNAUTHORIZED_EVENT),
        );
      }
    }

    return Promise.reject(error);
  },
);


export async function registerUser(payload) {
  const response = await api.post(
    "/auth/register",
    payload,
  );

  return response.data;
}


export async function loginUser(payload) {
  const response = await api.post(
    "/auth/login",
    payload,
  );

  storeAccessToken(response.data.access_token);

  return response.data;
}


export async function getCurrentUser() {
  const response = await api.get(
    "/auth/me",
  );

  return response.data;
}


export function logoutUser() {
  clearAccessToken();
}

export async function getPropertyManagers(
  skip = 0,
  limit = 200,
) {
  const response = await api.get(
    "/api/property-managers",
    {
      params: {
        skip,
        limit,
      },
    },
  );

  return response.data;
}

export async function getListings(pageSize = 50) {
  const response = await api.get(
    "/api/listings",
    {
      params: {
        page_size: pageSize,
      },
    },
  );

  return response.data;
}


export async function getListingById(listingId) {
  const response = await api.get(
    `/api/listings/${listingId}`,
  );

  return response.data;
}


export async function createListing(payload) {
  const response = await api.post(
    "/api/listings",
    payload,
  );

  return response.data;
}


export async function updateListing(listingId, payload) {
  const response = await api.put(
    `/api/listings/${listingId}`,
    payload,
  );

  return response.data;
}


export async function deleteListing(listingId) {
  const response = await api.delete(
    `/api/listings/${listingId}`,
  );

  return response.data;
}


export async function getNaiveListings(pageSize = 10) {
  const response = await api.get(
    "/api/listings/naive",
    {
      params: {
        page_size: pageSize,
      },
    },
  );

  return response.data;
}


export async function getFixedListings(pageSize = 10) {
  const response = await api.get(
    "/api/listings/fixed",
    {
      params: {
        page_size: pageSize,
      },
    },
  );

  return response.data;
}

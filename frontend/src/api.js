import axios from "axios";


const api = axios.create({
    // Use the same hostname as the frontend.
    baseURL: "http://localhost:8274",
    withCredentials: true,
    headers: {
      "Content-Type": "application/json",
    },
  });


export async function registerUser(payload) {
  const response = await api.post(
    "/api/auth/register",
    payload,
  );

  return response.data;
}


export async function loginUser(payload) {
  const response = await api.post(
    "/api/auth/login",
    payload,
  );

  return response.data;
}


export async function getCurrentUser() {
  const response = await api.get(
    "/api/auth/me",
  );

  return response.data;
}


export async function logoutUser() {
  const response = await api.post(
    "/api/auth/logout",
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
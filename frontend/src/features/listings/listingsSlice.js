import {
    createAsyncThunk,
    createSlice,
  } from "@reduxjs/toolkit";
  
  import {
    createListing as createListingRequest,
    deleteListing as deleteListingRequest,
    getListings,
    updateListing as updateListingRequest,
  } from "../../api";
  
  
  function getErrorMessage(error, fallbackMessage) {
    const detail = error.response?.data?.detail;
  
    if (typeof detail === "string") {
      return detail;
    }
  
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item.msg)
        .join("; ");
    }
  
    return error.message || fallbackMessage;
  }
  
  
  export const fetchListings = createAsyncThunk(
    "listings/fetchListings",
    async (_, thunkAPI) => {
      try {
        return await getListings();
      } catch (error) {
        return thunkAPI.rejectWithValue(
          getErrorMessage(
            error,
            "Unable to load rental listings.",
          ),
        );
      }
    },
  );
  
  
  export const createListing = createAsyncThunk(
    "listings/createListing",
    async (payload, thunkAPI) => {
      try {
        return await createListingRequest(payload);
      } catch (error) {
        return thunkAPI.rejectWithValue(
          getErrorMessage(
            error,
            "Unable to create the rental listing.",
          ),
        );
      }
    },
  );
  
  
  export const updateListing = createAsyncThunk(
    "listings/updateListing",
    async ({ listingId, payload }, thunkAPI) => {
      try {
        return await updateListingRequest(
          listingId,
          payload,
        );
      } catch (error) {
        return thunkAPI.rejectWithValue(
          getErrorMessage(
            error,
            "Unable to update the rental listing.",
          ),
        );
      }
    },
  );
  
  
  export const deleteListing = createAsyncThunk(
    "listings/deleteListing",
    async (listingId, thunkAPI) => {
      try {
        await deleteListingRequest(listingId);
        return Number(listingId);
      } catch (error) {
        return thunkAPI.rejectWithValue(
          getErrorMessage(
            error,
            "Unable to delete the rental listing.",
          ),
        );
      }
    },
  );
  
  
  const listingsSlice = createSlice({
    name: "listings",
  
    initialState: {
      items: [],
      loading: false,
      saving: false,
      initialized: false,
      error: null,
    },
  
    reducers: {
      clearListingError(state) {
        state.error = null;
      },

      resetListings(state) {
        state.items = [];
        state.loading = false;
        state.saving = false;
        state.initialized = false;
        state.error = null;
      },
    },
  
    extraReducers: (builder) => {
      builder
        .addCase(fetchListings.pending, (state) => {
          state.loading = true;
          state.error = null;
        })
        .addCase(fetchListings.fulfilled, (state, action) => {
          state.loading = false;
          state.initialized = true;
          state.items = action.payload;
        })
        .addCase(fetchListings.rejected, (state, action) => {
          state.loading = false;
          state.error = action.payload;
        })
  
        .addCase(createListing.pending, (state) => {
          state.saving = true;
          state.error = null;
        })
        .addCase(createListing.fulfilled, (state, action) => {
          state.saving = false;
          state.items.push(action.payload);
        })
        .addCase(createListing.rejected, (state, action) => {
          state.saving = false;
          state.error = action.payload;
        })
  
        .addCase(updateListing.pending, (state) => {
          state.saving = true;
          state.error = null;
        })
        .addCase(updateListing.fulfilled, (state, action) => {
          state.saving = false;
  
          const listingIndex = state.items.findIndex(
            (listing) => listing.id === action.payload.id,
          );
  
          if (listingIndex !== -1) {
            state.items[listingIndex] = action.payload;
          }
        })
        .addCase(updateListing.rejected, (state, action) => {
          state.saving = false;
          state.error = action.payload;
        })
  
        .addCase(deleteListing.pending, (state) => {
          state.saving = true;
          state.error = null;
        })
        .addCase(deleteListing.fulfilled, (state, action) => {
          state.saving = false;
          state.items = state.items.filter(
            (listing) => listing.id !== action.payload,
          );
        })
        .addCase(deleteListing.rejected, (state, action) => {
          state.saving = false;
          state.error = action.payload;
        });
    },
  });
  
  
  export const {
    clearListingError,
    resetListings,
  } = listingsSlice.actions;
  
  export default listingsSlice.reducer;
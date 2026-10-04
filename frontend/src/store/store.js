import { configureStore } from "@reduxjs/toolkit";

import listingsReducer from "../features/listings/listingsSlice";


export const store = configureStore({
  reducer: {
    listings: listingsReducer,
  },
});
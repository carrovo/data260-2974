"use strict";
const API_URL = "/api/listings";

// Get the rental listing form from the HTML page.
const rentalForm = document.getElementById("rentalForm");
const updateForm = document.getElementById("updateForm");
const deleteHighestButton = document.getElementById("deleteHighestButton");
const listingList = document.getElementById("listingList");
const loadingState = document.getElementById("loadingState");
const emptyState = document.getElementById("emptyState");
const errorState = document.getElementById("errorState");
const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const clearSearchButton = document.getElementById("clearSearchButton");

const hideListStates = () => {
    loadingState.hidden = true;
    emptyState.hidden = true;
    errorState.hidden = true;
    listingList.hidden = true;
};

const showLoadingState = () => {
    hideListStates();
    loadingState.hidden = false;
};

const showEmptyState = () => {
    hideListStates();
    emptyState.hidden = false;
};

const showErrorState = (message) => {
    hideListStates();

    errorState.textContent =
        message ||
        "Unable to load rental listings. Please try again.";

    errorState.hidden = false;
};

const showListingResults = (listings) => {
    hideListStates();

    if (listings.length === 0) {
        showEmptyState();
        return;
    }

    listingList.innerHTML = "";

    listings.forEach((listing) => {
        const item = document.createElement("li");
        item.className = "listing-card";

        const title = document.createElement("h3");
        title.textContent = listing.listingTitle;

        const identifier = document.createElement("p");
        identifier.textContent = `ID: ${listing.id}`;

        const address = document.createElement("p");
        address.textContent = `Address: ${listing.address}`;

        const propertyType = document.createElement("p");
        propertyType.textContent =
            `Property Type: ${listing.propertyType}`;

        item.append(
            title,
            identifier,
            address,
            propertyType
        );

        listingList.appendChild(item);
    });

    listingList.hidden = false;
};


const loadListings = async (query = "") => { // Load the rental listings.
    showLoadingState();

    try {
        const trimmedQuery = query.trim(); // Trim the query.

        const requestUrl = trimmedQuery
            ? `${API_URL}?q=${encodeURIComponent(trimmedQuery)}`
            : API_URL;

        const response = await fetch(requestUrl);// Fetch the rental listings.

        if (!response.ok) {
            throw new Error( // Throw an error if the response is not ok.
                `Request failed with status ${response.status}`
            );
        }

        const listings = await response.json(); // Get the rental listings.
        showListingResults(listings);
    } catch (error) {
        console.error("Unable to load listings:", error); // Log the error.

        showErrorState(
            "Unable to load rental listings. Please try again."
        );
    }
};


// Closure: keeps track of successful form submissions.
const createSubmissionCounter = () => {
    let count = 0;

    return () => {
        count += 1;
        return count;
    };
};

const getNextSubmissionCount = createSubmissionCounter();

// Arrow function: validates the description and terms checkbox.
const validateForm = () => {
    const description = document
        .getElementById("description")
        .value
        .trim();

    const termsAccepted =
        document.getElementById("termsAccepted").checked;

    if (description.length <= 25) {
        alert("The property description must contain more than 25 characters.");
        return false;
    }

    if (!termsAccepted) {
        alert("You must agree to the terms and conditions.");
        return false;
    }

    return true;
};

// Run this function when the form is submitted.
rentalForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!validateForm()) {
        return;
    }

    const formData = {
        listingTitle: document
            .getElementById("listingTitle")
            .value
            .trim(),

        address: document
            .getElementById("address")
            .value
            .trim(),

        submitterEmail: document
            .getElementById("submitterEmail")
            .value
            .trim(),

        description: document
            .getElementById("description")
            .value
            .trim(),

        propertyType:
            document.getElementById("propertyType").value,

        termsAccepted:
            document.getElementById("termsAccepted").checked
    };

    const jsonString = JSON.stringify(formData);

    console.log("Form data as a JSON string:");
    console.log(jsonString);

    const parsedObject = JSON.parse(jsonString);

    const {
        listingTitle,
        submitterEmail
    } = parsedObject;

    console.log(
        "Primary field - Listing Title:",
        listingTitle
    );

    console.log(
        "Submitter Email:",
        submitterEmail
    );

    const updatedObject = {
        ...parsedObject,
        submissionDate: new Date().toISOString()
    };

    console.log("Updated object with submissionDate:");
    console.log(updatedObject);

    try {
        const response = await fetch(API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: jsonString
        });

        if (!response.ok) {
            const errorData = await response.json();

            const errorMessage =
                typeof errorData.detail === "string"
                    ? errorData.detail
                    : JSON.stringify(errorData.detail);

            throw new Error(
                errorMessage || "Unable to create listing"
            );
        }

        const createdListing = await response.json();

        console.log(
            "Created rental listing:",
            createdListing
        );

        const submissionCount =
            getNextSubmissionCount();

        console.log(
            "Successful submission count:",
            submissionCount
        );

        alert(
            `Rental listing "${createdListing.listingTitle}" created successfully.`
        );

        window.location.assign("/");
    } catch (error) {
        console.error(
            "Unable to create rental listing:",
            error
        );

        showErrorState(
            `Unable to create rental listing: ${error.message}`
        );
    }
});

updateForm.addEventListener("submit", async (event) => { // Update the rental listing.
    event.preventDefault();

    const listingTitle = document // Get the new listing title.
        .getElementById("updateListingTitle")
        .value
        .trim();

    const address = document // Get the new address.
        .getElementById("updateAddress")
        .value
        .trim();

    if (!listingTitle || !address) { // Check if the new listing title and address are required.
        alert(
            "Both the new listing title and address are required."
        );
        return;
    }

    try { // Update the rental listing.
        const response = await fetch(`${API_URL}/1`, {
            method: "PUT", // Update the rental listing.
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                listingTitle,
                address
            })
        });

        if (!response.ok) { // Check if the response is ok.
            const errorData = await response.json(); // Get the error data.

            const errorMessage = // Get the error message.
                typeof errorData.detail === "string"
                    ? errorData.detail
                    : JSON.stringify(errorData.detail);

            throw new Error( // Throw an error if the response is not ok.
                errorMessage || "Unable to update listing"
            );
        }

        const updatedListing = await response.json(); // Get the updated listing.

        console.log( // Log the updated listing.
            "Updated rental listing:",
            updatedListing
        );

        alert( // Alert the user that the rental listing has been updated.
            `Listing ID 1 updated to "${updatedListing.listingTitle}".`
        );

        window.location.assign("/"); // Redirect the user to the home page.
    } catch (error) {
        console.error( // Log the error.
            "Unable to update rental listing:",
            error
        );

        showErrorState( // Show the error state.
            `Unable to update rental listing: ${error.message}`
        );
    }
});


deleteHighestButton.addEventListener( // Delete the highest-id rental listing.
    "click",
    async () => {
        const confirmed = confirm( // Confirm the deletion of the highest-id rental listing.
            "Delete the rental listing with the highest ID?"
        );

        if (!confirmed) { // If the user does not confirm the deletion, return.
            return;
        }

        try { // Delete the highest-id rental listing.
            const response = await fetch(
                `${API_URL}/actions/delete-highest`,
                {
                    method: "DELETE"
                }
            );

            if (!response.ok) { // Check if the response is ok.
                const errorData = await response.json();

                const errorMessage = // Get the error message.
                    typeof errorData.detail === "string"
                        ? errorData.detail
                        : JSON.stringify(errorData.detail);

                throw new Error( // Throw an error if the response is not ok.
                    errorMessage ||
                    "Unable to delete highest-ID listing"
                );
            }

            console.log( // Log the deletion of the highest-id rental listing.
                "The highest-ID rental listing was deleted."
            );

            alert( // Alert the user that the highest-id rental listing has been deleted.
                "The highest-ID rental listing was deleted successfully."
            );

            window.location.assign("/"); // Redirect the user to the home page.
        } catch (error) {
            console.error( // Log the error.
                "Unable to delete rental listing:",
                error
            );

            showErrorState( // Show the error state.
                `Unable to delete rental listing: ${error.message}`
            );
        }
    }
);

searchForm.addEventListener( // Search for a rental listing.
    "submit",
    async (event) => {
        event.preventDefault(); // Prevent the default form submission behavior.

        await loadListings(searchInput.value); // Load the rental listings.
    }
);

clearSearchButton.addEventListener( // Clear the search input.
    "click",
    async () => {
        searchInput.value = ""; // Clear the search input.
        await loadListings(); // Load the rental listings.
        searchInput.focus(); // Focus the search input.
    }
);

loadListings();
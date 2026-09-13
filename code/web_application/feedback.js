"use strict";

// Get the rental listing form from the HTML page.
const rentalForm = document.getElementById("rentalForm");
const listingList = document.getElementById("listingList");
const loadingState = document.getElementById("loadingState");
const emptyState = document.getElementById("emptyState");
const errorState = document.getElementById("errorState");


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

        const address = document.createElement("p");
        address.textContent = `Address: ${listing.address}`;

        item.append(title, address); // Add the title and address to the item.
        listingList.appendChild(item); // Add the item to the listing list.
    });

    listingList.hidden = false; // Show the listing list.
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
rentalForm.addEventListener("submit", (event) => {
    // Prevent the browser from reloading the page.
    event.preventDefault();

    if (!validateForm()) {
        return;
    }

    // Collect the form values into a JavaScript object.
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

    // Convert the form object into a JSON string.
    const jsonString = JSON.stringify(formData);
    console.log("Form data as a JSON string:");
    console.log(jsonString);

    // Convert the JSON string back into an object.
    const parsedObject = JSON.parse(jsonString);

    // Object destructuring: extract the primary field and email.
    const { listingTitle, submitterEmail } = parsedObject;

    console.log("Primary field - Listing Title:", listingTitle);
    console.log("Submitter Email:", submitterEmail);

    // Spread operator: copy the object and add submissionDate.
    const updatedObject = {
        ...parsedObject,
        submissionDate: new Date().toISOString()
    };

    console.log("Updated object with submissionDate:");
    console.log(updatedObject);

    // Use the closure to increase the successful submission count.
    const submissionCount = getNextSubmissionCount();

    console.log(
        "Successful submission count:",
        submissionCount
    );

    alert(
        `Rental listing submitted successfully! Submission count: ${submissionCount}`
    );

    // Clear the form and return focus to the primary field.
    rentalForm.reset();
    document.getElementById("listingTitle").focus();
});

showEmptyState();
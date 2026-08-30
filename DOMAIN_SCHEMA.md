# Domain Schema

## Personal Configuration

- SID4: 2974
- PORT_BASE: 8274
- PREFIX: s2974
- SEED: 2974
- VERIFY_SEED: 262974
- DOMAIN_ID: 6
- Assigned Domain: Rental housing listings

## Entity

Entity name: Rental Listing

## Fields

- listingTitle: Required text. The primary field for the rental listing.
- address: Required text. The property address.
- submitterEmail: Required email address.
- description: Required text area. Must contain more than 25 characters.
- propertyType: Required category selected from the dropdown menu.
- termsAccepted: Required boolean indicating acceptance of the terms and conditions.
- submissionDate: Date and time added after successful form validation.

## Property Type Categories

- Apartment
- House
- Studio
- Shared Room


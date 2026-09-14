from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator


PORT_BASE = 8274

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web_application"

app = FastAPI(
    title="Rental Housing Listings API",
    version="2.0.0"
)


class RentalListingBase(BaseModel):
    listingTitle: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)
    submitterEmail: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=26, max_length=2000)
    propertyType: Literal[
        "Apartment",
        "House",
        "Studio",
        "Shared Room"
    ]
    termsAccepted: bool

    @field_validator("listingTitle", "address", "submitterEmail")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value

    @field_validator("termsAccepted")
    @classmethod
    def require_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "Terms and conditions must be accepted"
            )

        return value


class RentalListingCreate(RentalListingBase):
    pass 


class RentalListing(RentalListingBase):
    id: int


class RentalListingUpdate(BaseModel):
    listingTitle: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)


listings: list[RentalListing] = [
    RentalListing(
        id=1,
        listingTitle="Studio Near SJSU",
        address="100 East San Carlos Street",
        submitterEmail="owner1@example.com",
        description=(
            "A furnished studio located within walking "
            "distance of the SJSU campus."
        ),
        propertyType="Studio",
        termsAccepted=True,
    ),
    RentalListing(
        id=2,
        listingTitle="Downtown Apartment",
        address="250 South First Street",
        submitterEmail="owner2@example.com",
        description=(
            "A one-bedroom downtown apartment with convenient "
            "access to public transportation."
        ),
        propertyType="Apartment",
        termsAccepted=True,
    ),
]


@app.get("/")
async def read_home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/listings", response_model=list[RentalListing]) #Get the rental listings.
async def get_listings(
    q: str | None = Query(default=None) # Get the query.
) -> list[RentalListing]:
    if not q or not q.strip():
        return listings # Return the rental listings.

    search_value = q.strip().lower() # Get the search value.

    return [ # Return the rental listings.
        listing
        for listing in listings
        if search_value in listing.listingTitle.lower() # Check if the search value is in the listing title.
        or search_value in listing.address.lower() # Check if the search value is in the listing address.
    ]


@app.post(
    "/api/listings",
    response_model=RentalListing,
    status_code=201
)
async def create_listing(
    listing_data: RentalListingCreate
) -> RentalListing:
    new_id = max(
        (listing.id for listing in listings),
        default=0
    ) + 1

    new_listing = RentalListing(
        id=new_id,
        **listing_data.model_dump()
    )

    listings.append(new_listing)
    return new_listing


@app.put(
    "/api/listings/{listing_id}",
    response_model=RentalListing
)
async def update_listing(
    listing_id: int,
    listing_data: RentalListingUpdate
) -> RentalListing:
    listing = next(
        (
            item
            for item in listings
            if item.id == listing_id
        ),
        None,
    )

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Rental listing not found"
        )

    listing.listingTitle = listing_data.listingTitle.strip()
    listing.address = listing_data.address.strip()

    return listing


@app.delete(
    "/api/listings/actions/delete-highest",
    status_code=204
)
async def delete_highest_listing() -> Response:
    if not listings: # Check if there are any rental listings.
        raise HTTPException(
            status_code=404,
            detail="No rental listings to delete"
        )

    highest_listing = max(
        listings,
        key=lambda listing: listing.id # Get the highest-id rental listing.
    )

    listings.remove(highest_listing) # Remove the highest-id rental listing.
    return Response(status_code=204)


app.mount(
    "/static",
    StaticFiles(directory=WEB_DIR),
    name="static",
)
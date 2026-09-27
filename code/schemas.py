from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ListingEventOut(BaseModel):
    """Response schema for related listing-event records."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    event_type: str
    details: str
    created_at: datetime


class ListingCreate(BaseModel):
    """
    Request schema for creating a rental listing.

    The primary and secondary domain fields are required.
    Other fields have safe defaults so the basic CRUD form
    can start with the required two inputs.
    """

    listingTitle: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

    submitterEmail: EmailStr = Field(
        default="demo@example.com"
    )

    description: str = Field(
        default="A rental listing created through the HW4 application.",
        min_length=26,
        max_length=2000,
    )

    propertyType: Literal[
        "Apartment",
        "House",
        "Studio",
        "Shared Room",
    ] = "Apartment"

    termsAccepted: bool = True

    @field_validator("listingTitle", "address")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class ListingUpdate(BaseModel):
    """Request schema for updating the primary domain fields."""

    listingTitle: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

    @field_validator("listingTitle", "address")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class ListingOut(BaseModel):
    """Response schema for a rental listing and its related events."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    listingTitle: str
    address: str
    submitterEmail: EmailStr
    description: str
    propertyType: str
    termsAccepted: bool
    created_at: datetime
    events: list[ListingEventOut] = Field(
        default_factory=list
    )


class UserCreate(BaseModel):
    """Request schema for creating a user account."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Request schema for email/password login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Public user response without the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr


class LoginResponse(BaseModel):
    """Response returned after successful login."""

    message: str
    user_id: int
    email: EmailStr
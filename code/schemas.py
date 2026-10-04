from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class ListingEventOut(BaseModel):
    """Response schema for listing-event records retained from HW4."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    event_type: str
    details: str
    created_at: datetime


class PropertyManagerCreate(BaseModel):
    """Request schema for creating a property manager."""

    firstName: str = Field(
        min_length=1,
        max_length=100,
    )
    lastName: str = Field(
        min_length=1,
        max_length=100,
    )
    email: EmailStr

    @field_validator("firstName", "lastName")
    @classmethod
    def reject_blank_manager_names(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class PropertyManagerUpdate(BaseModel):
    """Request schema for partially updating a property manager."""

    firstName: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    lastName: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    email: EmailStr | None = None

    @field_validator("firstName", "lastName")
    @classmethod
    def reject_blank_updated_names(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class PropertyManagerOut(BaseModel):
    """Public property-manager response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    firstName: str
    lastName: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class ListingCreate(BaseModel):
    """Request schema for creating a rental listing."""

    listingTitle: str = Field(
        min_length=1,
        max_length=100,
    )

    listingCode: str = Field(
        min_length=3,
        max_length=30,
        pattern=r"^[A-Z0-9-]+$",
    )

    address: str = Field(
        min_length=1,
        max_length=200,
    )

    submitterEmail: EmailStr = Field(
        default="demo@example.com",
    )

    description: str = Field(
        default="A rental listing created through the HW5 application.",
        min_length=26,
        max_length=2000,
    )

    propertyType: Literal[
        "Apartment",
        "House",
        "Studio",
        "Shared Room",
    ] = "Apartment"

    monthlyRent: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )

    availableUnits: int = Field(
        default=1,
        ge=0,
    )

    termsAccepted: bool = True

    propertyManagerId: int = Field(
        gt=0,
    )

    @field_validator("listingCode", mode="before")
    @classmethod
    def normalize_listing_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Listing code must be a string")

        return value.strip().upper()

    @field_validator("listingTitle", "address")
    @classmethod
    def reject_blank_listing_text(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class ListingUpdate(BaseModel):
    """Request schema for partially updating a rental listing."""

    listingTitle: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    listingCode: str | None = Field(
        default=None,
        min_length=3,
        max_length=30,
        pattern=r"^[A-Z0-9-]+$",
    )

    address: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    submitterEmail: EmailStr | None = None

    description: str | None = Field(
        default=None,
        min_length=26,
        max_length=2000,
    )

    propertyType: Literal[
        "Apartment",
        "House",
        "Studio",
        "Shared Room",
    ] | None = None

    monthlyRent: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )

    availableUnits: int | None = Field(
        default=None,
        ge=0,
    )

    termsAccepted: bool | None = None

    propertyManagerId: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator("listingCode", mode="before")
    @classmethod
    def normalize_updated_listing_code(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return value

        if not isinstance(value, str):
            raise ValueError("Listing code must be a string")

        return value.strip().upper()

    @field_validator("listingTitle", "address")
    @classmethod
    def reject_blank_updated_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("This field cannot be blank")

        return cleaned_value


class ListingOut(BaseModel):
    """Response schema for a rental listing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    listingTitle: str
    listingCode: str
    address: str
    submitterEmail: EmailStr
    description: str
    propertyType: str
    monthlyRent: Decimal
    availableUnits: int
    termsAccepted: bool
    propertyManagerId: int
    created_at: datetime
    updated_at: datetime
    events: list[ListingEventOut] = Field(
        default_factory=list,
    )


class UserCreate(BaseModel):
    """Request schema for creating a user account."""

    name: str = Field(
        min_length=1,
        max_length=100,
    )
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )


class UserLogin(BaseModel):
    """Request schema for email/password login."""

    email: EmailStr
    password: str = Field(
        min_length=1,
        max_length=128,
    )


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
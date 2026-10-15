from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DocumentListingStatus(str, Enum):
    active = "active"
    pending = "pending"
    rented = "rented"


class DocumentPropertyType(str, Enum):
    apartment = "Apartment"
    house = "House"
    studio = "Studio"
    shared_room = "Shared Room"


class DocumentListingCreate(BaseModel):
    listingTitle: str = Field(min_length=1, max_length=100)
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    status: DocumentListingStatus = DocumentListingStatus.active
    propertyType: DocumentPropertyType
    availableFrom: datetime

    @field_validator("listingTitle")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("listingTitle cannot be blank")

        return cleaned


class DocumentListingUpdate(BaseModel):
    listingTitle: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    status: DocumentListingStatus | None = None
    propertyType: DocumentPropertyType | None = None
    availableFrom: datetime | None = None

    @field_validator("listingTitle")
    @classmethod
    def reject_blank_updated_title(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value

        cleaned = value.strip()

        if not cleaned:
            raise ValueError("listingTitle cannot be blank")

        return cleaned


class DocumentListingOut(BaseModel):
    id: str
    listingTitle: str
    description: str | None = None
    status: DocumentListingStatus
    propertyType: DocumentPropertyType
    availableFrom: datetime
    createdAt: datetime
    updatedAt: datetime


class MemoryMode(str, Enum):
    mongodb = "mongodb"
    file = "file"
    hybrid = "hybrid"


class MemoryPolicy(str, Enum):
    standard = "standard"
    importance_eviction = "importance_eviction"


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    message: str = Field(min_length=1, max_length=4000)
    memory_mode: MemoryMode = MemoryMode.mongodb
    short_term_n: int | None = Field(
        default=None,
        ge=2,
        le=100,
    )
    policy: MemoryPolicy = MemoryPolicy.standard

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def strip_required_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return value

        cleaned = value.strip()

        if not cleaned:
            raise ValueError("value cannot be blank")

        return cleaned


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    reply: str
    memory_mode: MemoryMode
    used_memory: dict
    metrics: dict

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class PropertyManager(Base):
    """Related entity that manages one or more rental listings."""

    __tablename__ = "property_managers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    firstName: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    lastName: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    listings: Mapped[list["RentalListing"]] = relationship(
        back_populates="property_manager",
        passive_deletes=True,
    )


class RentalListing(Base):
    """Primary rental-listing entity for the domain application."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    listingTitle: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    listingCode: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        index=True,
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    submitterEmail: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    propertyType: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    monthlyRent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    availableUnits: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )

    termsAccepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    propertyManagerId: Mapped[int] = mapped_column(
        ForeignKey(
            "property_managers.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    property_manager: Mapped[PropertyManager] = relationship(
        back_populates="listings",
    )

    events: Mapped[list["ListingEvent"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )


class User(Base):
    """Registered application user with a securely stored password hash."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )


class SessionToken(Base):
    """Server-side login session referenced by an opaque browser cookie."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )


class ListingEvent(Base):
    """Related test entity retained from the HW4 N+1 experiment."""

    __tablename__ = "listing_events"

    __table_args__ = (
        Index(
            "idx_listing_events_event_type",
            "event_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    listing_id: Mapped[int] = mapped_column(
        ForeignKey(
            "listings.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    details: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    listing: Mapped[RentalListing] = relationship(
        back_populates="events",
    )
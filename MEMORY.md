# Durable Memory

<!-- last_consolidated: 2026-10-15T18:00:00+00:00 -->

## Current facts

- project_domain: Rental housing listings
- assigned_city: San Jose
- local_model: qwen3:8b
- api_framework: FastAPI
- relational_database: MySQL
- document_database: MongoDB
- frontend_framework: React
- state_management: Redux Toolkit
- student_sid4: 2974
- port_base: 8274
- prefix: s2974
- seed: 2974
- verify_seed: 262974
- domain_id: 6
- mongo_database: s2974_doc
- primary_entity: listing
- required_title_field: listingTitle
- preferred_property_type: Apartment
- preferred_city: San Jose
- monthly_budget: 2200 USD
- move_in_date: 2026-11-15
- pet: one indoor cat
- must_have: in-unit laundry
- avoid_property_type: Shared Room
- report_folder: reports/hw06

## Explicit contradiction resolutions

- resolution_preferred_city: kept San Jose; superseded Santa Clara; rule=latest explicit value wins
- resolution_monthly_budget: kept 2200 USD; superseded 2400 USD; rule=latest explicit value wins
- resolution_move_in_date: kept 2026-11-15; superseded 2026-11-01; rule=latest explicit value wins
- resolution_pet: kept one indoor cat; superseded no pet; rule=latest explicit value wins

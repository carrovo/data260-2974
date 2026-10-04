# HW5 Part 3 Tool Contracts

All three domain tools return the same response envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

On failure:

```json
{
  "ok": false,
  "data": null,
  "error": "description of the error"
}
```

## search_listings

Expected input schema:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 25,
      "default": 5
    }
  },
  "required": ["query"],
  "additionalProperties": false
}
```

Rejected input captured in Part 2B:

```json
{
  "query": "Seed",
  "limit": 0
}
```

Returned error:

```json
{
  "ok": false,
  "data": null,
  "error": "limit must be an integer between 1 and 25"
}
```

Reason: `limit` must be within the inclusive range 1–25.

## listing_details

Expected input schema:

```json
{
  "type": "object",
  "properties": {
    "listing_id": {
      "type": "integer",
      "minimum": 1
    }
  },
  "required": ["listing_id"],
  "additionalProperties": false
}
```

Rejected input captured in Part 2B:

```json
{
  "listing_id": -1
}
```

Returned error:

```json
{
  "ok": false,
  "data": null,
  "error": "listing_id must be a positive integer"
}
```

Reason: a database primary key must be a positive integer.

## manager_rent_summary

Expected input schema:

```json
{
  "type": "object",
  "properties": {
    "property_manager_id": {
      "type": "integer",
      "minimum": 1
    }
  },
  "required": ["property_manager_id"],
  "additionalProperties": false
}
```

Rejected input captured in Part 2B:

```json
{
  "property_manager_id": -1
}
```

Returned error:

```json
{
  "ok": false,
  "data": null,
  "error": "property_manager_id must be a positive integer"
}
```

Reason: a property-manager primary key must be a positive integer.
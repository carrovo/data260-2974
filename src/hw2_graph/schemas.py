import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
)


class PlannerProposal(BaseModel):
    model_config = ConfigDict( # Set the model config.
        extra="forbid", # Set the extra to forbid.
        strict=True, # Set the strict to true.
    )

    tags: list[StrictStr] = Field(
        min_length=3, # Set the min length to 3.
        max_length=3,
    ) # Set the max length to 3.

    summary: StrictStr

    @field_validator("tags") # Validate the tags.
    @classmethod
    def validate_tags( # Validate the tags.
        cls,
        tags: list[str], # Set the tags to the list of strings.
    ) -> list[str]:
        cleaned_tags = [ # Set the cleaned tags to the list of strings.
            tag.strip()
            for tag in tags # Iterate over the tags.
        ]

        for tag in cleaned_tags: # Iterate over the cleaned tags.
            if not 3 <= len(tag) <= 30: # Check if the length of the tag is between 3 and 30.
                raise ValueError(
                    "Each tag must contain "
                    "3 to 30 characters." # Set the error message to the following message.
                )

        normalized_tags = { # Set the normalized tags to the set of strings.
            tag.lower()
            for tag in cleaned_tags # Iterate over the cleaned tags.
        }

        if len(normalized_tags) != 3: # Check if the length of the normalized tags is not 3.
            raise ValueError(
                "The three tags must be distinct." # Set the error message to the following message.
            )

        return cleaned_tags # Return the cleaned tags.

    @field_validator("summary") # Validate the summary.
    @classmethod
    def validate_summary( # Validate the summary.
        cls,
        summary: str, # Set the summary to the string.
    ) -> str:
        cleaned_summary = summary.strip() # Strip the summary.

        if not cleaned_summary: # Check if the cleaned summary is empty.
            raise ValueError(
                "The summary cannot be empty."
            )

        words = re.findall( # Find the words in the cleaned summary.
            r"\b[\w'-]+\b",
            cleaned_summary, # Set the cleaned summary to the string.
        ) # Return the words.

        if len(words) > 25: # Check if the length of the words is greater than 25.
            raise ValueError(
                "The summary must contain "
                "no more than 25 words."
            )

        return cleaned_summary
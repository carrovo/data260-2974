"""Reviewer process for the HW8 Kafka agent pipeline."""

import asyncio

from hw8_agent_common import run_agent
from hw8_agent_logic import reviewer_message, reviewer_prompt
from hw8_config import DRAFTS_TOPIC, FINAL_TOPIC, REVIEWER_GROUP_ID

SYSTEM_PROMPT = (
    "You are the Reviewer for a rental-housing assistant. Correct the draft "
    "and return a concise final answer without unsupported claims."
)


async def main() -> None:
    """Run the Reviewer as an independent Kafka consumer and producer."""

    await run_agent(
        agent_name="REVIEWER",
        input_topic=DRAFTS_TOPIC,
        output_topic=FINAL_TOPIC,
        group_id=REVIEWER_GROUP_ID,
        system_prompt=SYSTEM_PROMPT,
        prompt_builder=reviewer_prompt,
        message_builder=reviewer_message,
    )


if __name__ == "__main__":
    asyncio.run(main())

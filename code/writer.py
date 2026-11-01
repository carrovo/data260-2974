"""Writer process for the HW8 Kafka agent pipeline."""

import asyncio

from hw8_agent_common import run_agent
from hw8_agent_logic import writer_message, writer_prompt
from hw8_config import DRAFTS_TOPIC, TASKS_TOPIC, WRITER_GROUP_ID

SYSTEM_PROMPT = (
    "You are the Writer for a rental-housing assistant. Produce a useful, "
    "plain-language answer from the Planner's steps."
)


async def main() -> None:
    """Run the Writer as an independent Kafka consumer and producer."""

    await run_agent(
        agent_name="WRITER",
        input_topic=TASKS_TOPIC,
        output_topic=DRAFTS_TOPIC,
        group_id=WRITER_GROUP_ID,
        system_prompt=SYSTEM_PROMPT,
        prompt_builder=writer_prompt,
        message_builder=writer_message,
    )


if __name__ == "__main__":
    asyncio.run(main())

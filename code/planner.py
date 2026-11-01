"""Planner process for the HW8 Kafka agent pipeline."""

import asyncio

from hw8_agent_common import run_agent
from hw8_agent_logic import planner_message, planner_prompt
from hw8_config import INBOX_TOPIC, PLANNER_GROUP_ID, TASKS_TOPIC

SYSTEM_PROMPT = (
    "You are the Planner for a rental-housing assistant. Create a concise "
    "answer plan grounded only in the question."
)


async def main() -> None:
    """Run the Planner as an independent Kafka consumer and producer."""

    await run_agent(
        agent_name="PLANNER",
        input_topic=INBOX_TOPIC,
        output_topic=TASKS_TOPIC,
        group_id=PLANNER_GROUP_ID,
        system_prompt=SYSTEM_PROMPT,
        prompt_builder=planner_prompt,
        message_builder=planner_message,
    )


if __name__ == "__main__":
    asyncio.run(main())

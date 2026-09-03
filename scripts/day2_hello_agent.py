"""Day 2 proof: a hello-world ADK agent runs locally and calls Gemini 3.8 Flash.

Run: python scripts/day2_hello_agent.py
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "src")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from boxes.agent import root_agent  # noqa: E402


async def main() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="boxes")
    session = await runner.session_service.create_session(app_name="boxes", user_id="dev")
    msg = types.Content(
        role="user",
        parts=[types.Part(text="In one sentence, what will you do when I give you a film premise?")],
    )
    async for event in runner.run_async(user_id="dev", session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    print(f"[{event.author}] {p.text.strip()}")
                if p.function_call:
                    print(f"[{event.author}] tool_call {p.function_call.name}({dict(p.function_call.args)})")


if __name__ == "__main__":
    asyncio.run(main())

"""ADK workflow agent used by the production API.

The research loop remains explicit Python because its fan-out, evidence ledger,
and stopping rule are deterministic. Wrapping it as a BaseAgent puts the same
workflow on ADK's runtime surface without asking an LLM to improvise control
flow. The FastAPI service calls this object directly and ADK can also invoke it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Callable

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types

from . import research_loop


class ResearchWorkflowAgent(BaseAgent):
    def execute(
        self, premise: str, *, depth: str = "scout",
        on_event: Callable[[dict], None] | None = None,
    ) -> research_loop.ResearchProject:
        return research_loop.run(premise, depth=depth, on_event=on_event or (lambda _: None))

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        parts = (ctx.user_content.parts if ctx.user_content else []) or []
        premise = " ".join(p.text or "" for p in parts if getattr(p, "text", None)).strip()
        if not premise:
            yield Event(author=self.name, content=types.Content(
                role="model", parts=[types.Part(text="Give me a film premise to research.")]
            ))
            return
        project = await asyncio.to_thread(self.execute, premise)
        report = project.reports[-1]
        payload = {
            "research_completeness": report.confidence,
            "coverage": report.overall_coverage,
            "boxes": len(project.objectives),
            "evidence": len(project.evidence),
            "stop_reason": project.ledger.rounds[-1].next_action if project.ledger.rounds else "",
        }
        yield Event(author=self.name, content=types.Content(
            role="model", parts=[types.Part(text=json.dumps(payload))]
        ))


workflow_agent = ResearchWorkflowAgent(
    name="boxes_research_workflow",
    description="Deterministic autonomous research workflow for film production.",
)

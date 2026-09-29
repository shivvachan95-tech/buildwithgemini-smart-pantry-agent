# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types


from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from app.a2ui_utils import a2ui_callback
from app.tools import (
    add_pantry_item,
    find_nearby_places,
    generate_pantry_item_image,
    generate_pantry_item_video,
    generate_recipe_image,
    geocode_address,
    get_pantry_items,
    search_online_recipes,
    update_pantry_item_quantity,
)

DEPLOYMENT_METADATA_PATH = Path(__file__).parent.parent / "deployment_metadata.json"

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="You are the Smart Pantry Recipe Concierge. You help users manage their kitchen pantry inventory, suggest recipes, and locate nearby grocery stores and supermarkets.",
    workflow_description=(
        "Analyze the request and return structured UI when appropriate. You remember facts, "
        "preferences, and explicitly stated user dietary restrictions, food allergies (e.g., peanuts, "
        "gluten, dairy, shellfish), and health preferences across conversations. ALWAYS check and "
        "strictly respect any remembered user allergies or dietary restrictions when suggesting recipes, "
        "recommending pantry items, or answering meal planning queries. You have access to tools to "
        "read/update Firestore pantry items, search recipes via TheMealDB API, locate places via Google "
        "Maps Places API, generate images, and execute Python code. Always check pantry inventory when "
        "asked what ingredients are available or when suggesting recipes based on available items."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


def _get_code_executor() -> AgentEngineSandboxCodeExecutor:
    sandbox_id = None
    agent_engine_id = None
    if DEPLOYMENT_METADATA_PATH.exists():
        try:
            with open(DEPLOYMENT_METADATA_PATH) as f:
                meta = json.load(f)
            sandbox_id = meta.get("sandbox_resource_name")
            agent_engine_id = meta.get("remote_agent_runtime_id")
        except Exception:
            pass

    if sandbox_id:
        return AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_id)
    elif agent_engine_id:
        return AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_id)
    return AgentEngineSandboxCodeExecutor()


async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        import logging
        logging.warning("Memory extraction skipped: %s", e)
    return None


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=_get_code_executor(),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_pantry_items,
        add_pantry_item,
        update_pantry_item_quantity,
        search_online_recipes,
        generate_recipe_image,
        generate_pantry_item_image,
        generate_pantry_item_video,
        geocode_address,
        find_nearby_places,
        get_weather,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)


def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project="qwiklabs-gcp-03-4967875f7575",
        location="us-east1",
        agent_engine_id="6625021551257321472",
    )


app = App(
    root_agent=root_agent,
    name="app",
)

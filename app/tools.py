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

import base64
import inspect
import json
import os
import urllib.parse
import urllib.request
import uuid
from dotenv import load_dotenv
from google import genai
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-03-4967875f7575"
BUCKET_NAME = "smart-pantry-media-qwiklabs-gcp-03-4967875f7575"

def _get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)

def get_pantry_items() -> str:
    """Retrieves all items currently stored in the smart pantry from Firestore.

    Returns:
        JSON string containing the list of pantry items with their name, quantity, unit, category, and expiration date.
    """
    db = _get_firestore_client()
    docs = db.collection("pantry_items").stream()
    items = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        items.append(data)
    return json.dumps(items, indent=2)

def add_pantry_item(item_id: str, name: str, quantity: int, unit: str, category: str, expiration_date: str = "") -> str:
    """Adds a new item or updates an existing item in the smart pantry.

    Args:
        item_id: Unique string key for the item (e.g., 'pasta', 'milk', 'eggs').
        name: Display name of the item (e.g., 'Spaghetti Pasta').
        quantity: Numerical amount of the item.
        unit: Unit of measurement (e.g., 'g', 'ml', 'pcs', 'cloves').
        category: Food category (e.g., 'Grains', 'Dairy', 'Produce', 'Pantry').
        expiration_date: Optional expiration date in YYYY-MM-DD format.

    Returns:
        Confirmation message string.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("pantry_items").document(item_id.strip().lower())
    item_data = {
        "name": name,
        "quantity": quantity,
        "unit": unit,
        "category": category,
        "expiration_date": expiration_date,
    }
    doc_ref.set(item_data)
    return f"Successfully added/updated pantry item '{name}' ({quantity} {unit}) in category '{category}'."

def update_pantry_item_quantity(item_id: str, quantity: int) -> str:
    """Updates the quantity of an existing item in the smart pantry.

    Args:
        item_id: Unique string key for the item (e.g., 'pasta', 'garlic').
        quantity: The new integer quantity for the item.

    Returns:
        Confirmation message string.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("pantry_items").document(item_id.strip().lower())
    doc = doc_ref.get()
    if not doc.exists:
        return f"Error: Item '{item_id}' not found in the pantry."
    doc_ref.update({"quantity": quantity})
    return f"Successfully updated quantity for '{item_id}' to {quantity}."

def generate_recipe_image(prompt: str) -> str:
    """Generates a photo of a recipe or dish, uploads it to public Cloud Storage, and returns the image URL.

    Args:
        prompt: Description of the dish or meal image to generate (e.g., 'Garlic tomato pasta topped with fresh parmesan').

    Returns:
        Public HTTP URL string pointing to the generated image in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")
    res = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=f"Generate a realistic food photo of: {prompt}"
    )

    image_bytes = None
    mime_type = "image/png"
    if res.candidates and res.candidates[0].content and res.candidates[0].content.parts:
        for part in res.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/png"
                break

    if not image_bytes:
        return "Failed to generate recipe image."

    ext = "png" if "png" in mime_type else "jpg"
    filename = f"recipe_{uuid.uuid4().hex[:8]}.{ext}"

    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return f"Successfully generated recipe image: {url}"

def generate_pantry_item_image(item_name: str, tool_context: ToolContext) -> str:
    """Generates an image for a food item in the pantry domain using gemini-3.1-flash-lite-image in the global region.

    Saves the image with tool_context.save_artifact for the Playground's Artifacts panel,
    and uploads the image bytes directly to public Cloud Storage, returning its public https URL.

    Args:
        item_name: Name or description of the pantry item (e.g., 'Fresh Organic Tomatoes', 'Artisanal Sourdough Bread').
        tool_context: Injected ADK ToolContext instance.

    Returns:
        Public https URL string pointing to the uploaded image in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    res = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=f"Generate a studio food photograph of: {item_name}"
    )

    image_bytes = None
    mime_type = "image/png"
    if res.candidates and res.candidates[0].content and res.candidates[0].content.parts:
        for part in res.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/png"
                break

    if not image_bytes:
        return f"Failed to generate image for '{item_name}'."

    ext = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
    filename = f"item_{uuid.uuid4().hex[:8]}.{ext}"

    # 1. Save as ADK artifact so it appears in Playground's Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    res_art = tool_context.save_artifact(filename=filename, artifact=artifact_part)
    if inspect.isawaitable(res_art):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(res_art)
        except RuntimeError:
            asyncio.run(res_art)

    # 2. Upload image bytes directly to public GCS bucket (without writing to a local file)
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket("smart-pantry-media-qwiklabs-gcp-03-4967875f7575")
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    url = f"https://storage.googleapis.com/smart-pantry-media-qwiklabs-gcp-03-4967875f7575/{filename}"
    return url

def generate_pantry_item_video(item_name: str, tool_context: ToolContext) -> str:
    """Generates a short video for an item in the smart pantry domain using gemini-omni-flash-preview in the global region.

    Saves the video with tool_context.save_artifact for the Playground's Artifacts panel,
    and uploads the video bytes directly to public Cloud Storage, returning its public https URL.

    Args:
        item_name: Name or description of the pantry item (e.g., 'Fresh Tomatoes', 'Artisanal Sourdough Bread').
        tool_context: Injected ADK ToolContext instance.

    Returns:
        Public https URL string pointing to the uploaded video in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project="qwiklabs-gcp-03-4967875f7575", location="global")
    try:
        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short video of: {item_name}"
        )
    except Exception as e:
        return f"Failed to generate video for '{item_name}': {e}"

    video_bytes = None
    mime_type = "video/mp4"

    if hasattr(response, "output_video") and response.output_video:
        data = response.output_video.data
        if isinstance(data, str):
            video_bytes = base64.b64decode(data)
        else:
            video_bytes = data
        if getattr(response.output_video, "mime_type", None):
            mime_type = response.output_video.mime_type

    if not video_bytes:
        return f"Failed to generate or extract video bytes for '{item_name}'."

    filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

    # 1. Save as ADK artifact so it appears in Playground's Artifacts panel
    artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
    res_art = tool_context.save_artifact(filename=filename, artifact=artifact_part)
    if inspect.isawaitable(res_art):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(res_art)
        except RuntimeError:
            asyncio.run(res_art)

    # 2. Upload video bytes directly to public GCS bucket (without writing to a local file)
    storage_client = storage.Client(project="qwiklabs-gcp-03-4967875f7575")
    bucket = storage_client.bucket("smart-pantry-media-qwiklabs-gcp-03-4967875f7575")
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    url = f"https://storage.googleapis.com/smart-pantry-media-qwiklabs-gcp-03-4967875f7575/{filename}"
    return url

def search_online_recipes(query: str) -> str:
    """Searches TheMealDB public API for real recipe details, ingredients, and instructions.

    Args:
        query: Name of the dish or ingredient to search for (e.g., 'pasta', 'arrabiata', 'omelette').

    Returns:
        JSON string containing matching recipe details, category, cuisine origin, ingredients list, and instructions.
    """
    api_key = os.getenv("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            meals = data.get("meals")
            if not meals:
                return f"No recipes found on TheMealDB for query '{query}'."
            results = []
            for meal in meals[:3]:
                ingredients = []
                for i in range(1, 21):
                    ing = meal.get(f"strIngredient{i}")
                    meas = meal.get(f"strMeasure{i}")
                    if ing and ing.strip():
                        ingredients.append(f"{meas.strip() if meas else ''} {ing.strip()}".strip())
                results.append({
                    "name": meal.get("strMeal"),
                    "category": meal.get("strCategory"),
                    "area": meal.get("strArea"),
                    "instructions": meal.get("strInstructions"),
                    "ingredients": ingredients,
                })
            return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error fetching online recipes: {str(e)}"

def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographic coordinates using the Google Maps Geocoding API.

    Args:
        address: Street address or city name (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        JSON string containing the formatted address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable not set."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") != "OK" or not data.get("results"):
                return f"Geocoding failed for address '{address}': {data.get('status')}"
            first = data["results"][0]
            loc = first["geometry"]["location"]
            res = {
                "address": first.get("formatted_address"),
                "location": {
                    "latitude": loc["lat"],
                    "longitude": loc["lng"]
                }
            }
            return json.dumps(res, indent=2)
    except Exception as e:
        return f"Error executing Geocoding request: {str(e)}"

def find_nearby_places(latitude: float, longitude: float, place_type: str = "supermarket", radius_meters: float = 5000.0) -> str:
    """Finds nearby places of a given type around coordinates using the Places API (New) searchNearby REST endpoint.

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g., 'supermarket', 'grocery_store', 'bakery', 'restaurant').
        radius_meters: Search radius in meters (default: 5000).

    Returns:
        JSON string containing a list of nearby places with name, address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
    }
    body = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": float(radius_meters)
            }
        }
    }

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            places = data.get("places", [])
            results = []
            for p in places:
                results.append({
                    "name": p.get("displayName", {}).get("text"),
                    "address": p.get("formattedAddress"),
                    "location": p.get("location")
                })
            return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error executing Places searchNearby request: {str(e)}"

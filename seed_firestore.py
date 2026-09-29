from google.cloud import firestore

# Hardcoded project ID as required (do NOT use GOOGLE_CLOUD_PROJECT or google.auth.default())
FIRESTORE_PROJECT = "qwiklabs-gcp-03-4967875f7575"

db = firestore.Client(project=FIRESTORE_PROJECT)

pantry_items = [
    {
        "id": "pasta",
        "name": "Pasta",
        "category": "Grains",
        "quantity": 500,
        "unit": "g",
        "expiration_date": "2026-12-31",
    },
    {
        "id": "canned_tomatoes",
        "name": "Canned Tomatoes",
        "category": "Vegetables",
        "quantity": 2,
        "unit": "cans",
        "expiration_date": "2026-10-15",
    },
    {
        "id": "olive_oil",
        "name": "Olive Oil",
        "category": "Oils",
        "quantity": 1,
        "unit": "bottle",
        "expiration_date": "2027-01-01",
    },
    {
        "id": "garlic",
        "name": "Garlic",
        "category": "Produce",
        "quantity": 3,
        "unit": "cloves",
        "expiration_date": "2026-10-05",
    },
    {
        "id": "parmesan",
        "name": "Parmesan Cheese",
        "category": "Dairy",
        "quantity": 150,
        "unit": "g",
        "expiration_date": "2026-10-20",
    },
]

print(f"Seeding pantry items into Firestore project '{FIRESTORE_PROJECT}'...")
for item in pantry_items:
    item_data = item.copy()
    doc_id = item_data.pop("id")
    db.collection("pantry_items").document(doc_id).set(item_data)
    print(f"  ✓ Seeded item: {doc_id} -> {item_data['name']}")

print("Successfully seeded Firestore pantry_items collection!")

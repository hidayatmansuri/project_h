"""
Pure-Python helpers for reading the ORIGINAL Flask app's SQLite database.

Nothing in this module imports Django, so it can be unit-tested on its own and
reused by the ``import_recipes`` management command.
"""
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

# Image files that were only ever README screenshots / test uploads in the Flask app.
# They live in static/img next to real recipe photos, so they are skipped on import.
SKIP_IMAGE_NAMES = {
    "newcategory&cuisine.jpg", "newrecipes.jpg", "recipeview.jpg", "loggedin.jpg",
    "createnewuser.jpg", "editrecipe.jpg", "editcatagory.jpg", "editcuisine.jpg",
    "loginpage.jpg", "roll_down.jpg", "stackable_design.jpg",
}
SKIP_IMAGE_PREFIXES = ("test_",)

# Display metadata that used to be hard-coded in index.html / recipes.html.
CATEGORY_META = {
    "Chicken": ("fa-drumstick-bite", "chick", "Tender roasts, aromatic curries & grills"),
    "Beef": ("fa-bacon", "beef", "Rich stir-fries, crispy bites & hearty mains"),
    "Lamb": ("fa-drumstick-bite", "lamb", "Slow-simmered tagines & fragrant roasts"),
    "Pork": ("fa-bone", "pork", "Italian meatballs, glazed ribs & steaks"),
    "Sea Food": ("fa-fish", "seafood", "Succulent prawns, fresh fish & pasta pairings"),
    "Healthy": ("fa-heartbeat", "healthy", "Nutrient-dense bowls, salads & clean eating"),
    "Vegan": ("fa-seedling", "vegan", "100% plant-based curries, bowls & treats"),
    "Vegetable": ("fa-carrot", "veg", "Farm-fresh veggies, one-pots & spiced roasts"),
    # Added later in the Flask admin, so it had no hard-coded card. Sensible defaults:
    "Dessert": ("fa-birthday-cake", "pork", "Sweet bakes, puddings & treats"),
}

# name -> (short label, accent colour, tagline)
CUISINE_META = {
    "American Cuisine": ("American", "red", "Classic barbecue, hearty burgers & comfort food"),
    "Australian Cuisine": ("Australian", "purple", "Fresh coastal flavours, grills & modern cafe eats"),
    "Canadian Cuisine": ("Canadian", "blue", "Rustic warmth, poutine & maple-inspired savouries"),
    "Chinese Cuisine": ("Chinese", "green", "Crisp wok stir-fries, fragrant noodles & dim sum"),
    "European Cuisine": ("European", "red", "Bistro favourites, rustic stews & pastry dishes"),
    "Far Eastern Cuisine": ("Far Eastern", "purple", "Thai basil aromatics, Japanese broths & sushi"),
    "Mediterranean Cuisine": ("Mediterranean", "blue", "Golden olive oils, fresh seafood & sunlit herbs"),
    "Middle Eastern Cuisine": ("Mdl Eastern", "green", "Fragrant za'atar, saffron grains & mezze platters"),
    "North African Cuisine": ("N. African", "red", "Moroccan tagines, harissa spice & couscous"),
    "South African Cuisine": ("S. African", "purple", "Cape Malay curries, bobotie & braai marinades"),
    "South American Cuisine": ("S. American", "blue", "Chimichurri grills, ceviche & Andean quinoa"),
    "South Asian Cuisine": ("S. Asian", "green", "Royal biryanis, batata poha & spicy tandoori"),
    # Added later in the Flask admin:
    "French Cuisine": ("French", "purple", "Buttery pastries, rustic stews & classic sauces"),
}

DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y")


def parse_minutes(value):
    """'15 mins' -> 15, '90' -> 90, '' / None / 'n/a' -> 0."""
    digits = re.sub(r"\D", "", str(value or ""))
    return min(int(digits), 32767) if digits else 0


def parse_legacy_date(value):
    """
    Flask stored free text such as 'Jul 26, 2020' or '11/02/2020'.
    Numeric dates are read day-first (UK), matching a London-based project.
    Returns a ``date`` or ``None`` when the text cannot be understood.
    """
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _json_list(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if x and str(x).strip()]


def _numbered(row, prefix):
    out = []
    for i in range(1, 10):
        val = row.get(f"{prefix}_{i}")
        if val and str(val).strip():
            out.append(str(val).strip())
    return out


def image_filename(path):
    """'static/img/Chicken Biryani.jpg' -> 'Chicken Biryani.jpg'."""
    return Path(str(path or "").replace("\\", "/")).name


def is_recipe_photo(filename):
    low = filename.lower()
    if low in SKIP_IMAGE_NAMES or low.startswith(SKIP_IMAGE_PREFIXES):
        return False
    return low.endswith((".jpg", ".jpeg", ".png", ".webp"))


def read_legacy_database(sqlite_path):
    """
    Read categories, cuisines, library images and recipes from the Flask SQLite file.
    The ``users`` table is deliberately NOT read (see INTEGRATION_GUIDE.md).
    """
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        categories = [r["category_name"] for r in conn.execute("SELECT category_name FROM categories ORDER BY id")]
        cuisines = [r["cuisine_name"] for r in conn.execute("SELECT cuisine_name FROM cuisines ORDER BY id")]
        library = [image_filename(r["recipe_image"]) for r in conn.execute("SELECT recipe_image FROM images ORDER BY id")]
        recipes = []
        for row in conn.execute("SELECT * FROM recipes ORDER BY id"):
            r = dict(row)
            ingredients = _json_list(r.get("ingredients_json")) or _numbered(r, "ingredient")
            methods = _json_list(r.get("methods_json")) or _numbered(r, "method")
            recipes.append({
                "legacy_id": r["id"],
                "name": (r.get("recipe_name") or "").strip(),
                "category": (r.get("recipe_type") or "").strip(),
                "cuisine": (r.get("recipe_cuisine") or "").strip(),
                "image": image_filename(r.get("recipe_image")),
                "ingredients": ingredients,
                "methods": methods,
                "prep_time": parse_minutes(r.get("prep_time")),
                "cook_time": parse_minutes(r.get("cook_time")),
                "created_on": parse_legacy_date(r.get("create_on")),
                "created_on_raw": r.get("create_on") or "",
                "slug": (r.get("url") or "").strip(),
            })
    finally:
        conn.close()
    return {"categories": categories, "cuisines": cuisines, "library": library, "recipes": recipes}

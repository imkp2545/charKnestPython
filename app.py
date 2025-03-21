import os
import openai
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS  # Added CORS import
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GOOGLE_MAPS_API_KEY = "AIzaSyDv_nWmu_CWJ5TfiWHGueuuA3FFZMtKXkE"

# Validate API Keys
if not OPENAI_API_KEY or not SERPAPI_KEY:
    raise ValueError("❌ ERROR: API Keys are missing from .env file!")

# Initialize Flask app with CORS
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ✅ Function to extract price from text using regex
def extract_price(text):
    if not text:
        return "N/A"
    price_match = re.search(r'₹[\d,.]+(?:\s*(Lac|Crore))?', text)
    return price_match.group() if price_match else "N/A"

# ✅ Function to fetch property listings from SerpAPI
def fetch_real_property_listings(user_input):
    try:
        print(f"🔍 Searching for properties in: {user_input}")
        search_query = f"site:99acres.com {user_input}"
        url = "https://serpapi.com/search"
        params = {
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": 5
        }
        response = requests.get(url, params=params)
        data = response.json()

        if "organic_results" not in data:
            return "No results found."

        properties = []
        for result in data["organic_results"][:5]:
            prop_link = result.get("link", "N/A")
            prop_image = result.get("thumbnail", "N/A")
            prop_snippet = result.get("snippet", "N/A")
            prop_price = extract_price(prop_snippet)

            if prop_price == "N/A":
                if "rich_snippet" in result:
                    prop_price = extract_price(str(result["rich_snippet"]))
                elif "inline_snippet" in result:
                    prop_price = extract_price(str(result["inline_snippet"]))

            properties.append({
                "title": result.get("title", "N/A"),
                "price": prop_price,
                "link": prop_link,
                "image": prop_image,
                "description": prop_snippet
            })
        return properties
    except Exception as e:
        print(f"❌ SerpAPI ERROR: {e}")
        return f"Error: {str(e)}"

# ✅ Function to analyze and structure property details using OpenAI API
def analyze_property_details(property_list):
    try:
        formatted_properties = "\n".join([
            f"- **Sub-Title**: {prop['title']}\n"
            f"- **Price**: {prop['price']}\n"
            f"- **Description**: {prop['description']}\n"
            f"- **Website Link**: {prop['link']}\n"
            f"- **Image URL**: {prop['image']}\n"
            for prop in property_list
        ])

        prompt = f"""
        Please structure the following property listings with accurate details:
        {formatted_properties}
        **Return output in this structured format:**
        - **Sub-Title**: 
        - **Price**: 
        - **Size**: 
        - **Title**: 
        - **Location**: 
        - **Website Link**: 
        - **Image URL**: 
        Ensure that the details match correctly.
        """
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        gpt_response = response.json()
        
        if "choices" in gpt_response and len(gpt_response["choices"]) > 0:
            return gpt_response["choices"][0]["message"]["content"]
        return "❌ Failed to analyze property details."
    except Exception as e:
        print(f"❌ OpenAI ERROR: {e}")
        return f"Error: {str(e)}"

# ✅ API Route to Get Property Recommendations
@app.route("/recommend", methods=["POST"])
def recommend():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid request format. Expected JSON."}), 400
        data = request.get_json()
        if "userInput" not in data:
            return jsonify({"error": "User input is required"}), 400
        user_input = data["userInput"]
        listings = fetch_real_property_listings(user_input)
        if isinstance(listings, str):
            return jsonify({"error": listings}), 500
        structured_data = analyze_property_details(listings)
        return jsonify({"recommendations": structured_data})
    except Exception as e:
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

# ✅ Function to get latitude and longitude from a location
def get_location_coordinates(location):
    try:
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": location, "key": GOOGLE_MAPS_API_KEY}
        response = requests.get(base_url, params=params)
        data = response.json()
        if data["status"] == "ZERO_RESULTS":
            return {"error": "❌ No location found. Try a more specific query."}
        elif data["status"] != "OK":
            return {"error": f"❌ Geocoding failed: {data['status']}"}
        result = data["results"][0]
        return {
            "latitude": result["geometry"]["location"]["lat"],
            "longitude": result["geometry"]["location"]["lng"]
        }
    except Exception as e:
        return {"error": f"❌ Error fetching location: {str(e)}"}

# ✅ Function to fetch unique nearby amenity names and calculate average proximity score
def get_nearby_amenity_analysis(lat, lng, radius=2000):
    try:
        base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        place_types = [
            "hospital", "school", "restaurant", "shopping_mall", "gym",
            "park", "bank", "pharmacy", "supermarket", "bus_station"
        ]
        amenities = {}
        total_score = 0
        count_types = 0

        for place_type in place_types:
            params = {
                "location": f"{lat},{lng}",
                "radius": radius,
                "type": place_type,
                "key": GOOGLE_MAPS_API_KEY
            }
            response = requests.get(base_url, params=params)
            data = response.json()
            if "results" in data:
                unique_amenities = set()
                for place in data["results"]:
                    unique_amenities.add(place["name"])
                amenities[place_type] = list(unique_amenities)[:5]
                count = len(unique_amenities)
                total_score += min(10, count)
                count_types += 1

        avg_proximity_score = round(total_score / count_types, 1) if count_types > 0 else 0
        proximity_analysis = get_proximity_analysis_chatgpt(amenities, avg_proximity_score)
        return {
            "amenities": amenities,
            "average_proximity_score": avg_proximity_score,
            "proximity_analysis": proximity_analysis.strip()
        }
    except Exception as e:
        return {"error": f"❌ Error fetching amenities: {str(e)}"}

# ✅ Function to get a dynamic proximity analysis from ChatGPT
def get_proximity_analysis_chatgpt(amenities, avg_score):
    try:
        prompt = f"""
        Based on the following amenities data, generate a structured and well-explained proximity analysis:
        - **Key Amenities Present:** {list(amenities.keys())}
        - **Average Accessibility Score:** {avg_score}/10
        Please ensure the response is well-structured and easy to read. Highlight the strengths of the area and mention any missing amenities that might impact livability.
        """
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        gpt_response = response.json()
        if "choices" in gpt_response and len(gpt_response["choices"]) > 0:
            return gpt_response["choices"][0]["message"]["content"]
        return "❌ No proximity analysis available."
    except Exception as e:
        return f"❌ Error generating proximity analysis: {str(e)}"

# ✅ Function to fetch real estate market insights using ChatGPT API
def get_market_insights(location):
    try:
        prompt = f"""
        Provide **detailed** real estate market insights for **{location}**, covering:
        - **Current Property Prices** (Buying & Rental)
        - **Rental Yield Trends** (Expected % returns)
        - **Investment Potential** (Growth prospects & demand)
        - **Upcoming Infrastructure Projects** (Metro, Roads, Commercial hubs)
        - **Risks & Concerns** (Volatility, regulation changes)
        - **Safety & Livability** (Community, crime rates, green spaces)
        Ensure the response is clear, concise, and formatted for easy reading.
        """
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        gpt_response = response.json()
        if "choices" in gpt_response and len(gpt_response["choices"]) > 0:
            return gpt_response["choices"][0]["message"]["content"]
        return "❌ No market insights available."
    except Exception as e:
        return {"error": f"❌ Error fetching market insights: {str(e)}"}

# ✅ API Route for Location, Proximity, and Market Analysis with Ratings
@app.route("/analyze-location", methods=["GET"])
def analyze_location():
    try:
        location = request.args.get("location")
        radius = int(request.args.get("radius", 2000))
        if not location:
            return jsonify({"error": "❌ Location parameter is required"}), 400
        location_data = get_location_coordinates(location)
        if "error" in location_data:
            return jsonify(location_data), 400
        lat, lng = location_data["latitude"], location_data["longitude"]
        proximity_data = get_nearby_amenity_analysis(lat, lng, radius)
        market_insights = get_market_insights(location)
        return jsonify({
            "location": location,
            "latitude": lat,
            "longitude": lng,
            "average_proximity_score": proximity_data["average_proximity_score"],
            "proximity_analysis": proximity_data["proximity_analysis"],
            "amenities": proximity_data["amenities"],
            "market_insights": market_insights
        })
    except Exception as e:
        return jsonify({"error": f"❌ Failed to process request: {str(e)}"}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "CharkNest is working "}), 200



# ✅ Run the Flask App
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

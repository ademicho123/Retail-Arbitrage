import openai
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load API keys
APIFY_API_KEY = os.getenv("APIFY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the OpenAI client 
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Function to interpret user
def interpret_query(user_query):
    """
    Uses OpenAI API to extract the product name or search intent from a natural language query.
    """
    try:
        # Updated to use the current OpenAI API format
        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",  
            prompt=f"Extract the product name or relevant search term from this query: '{user_query}'",
            max_tokens=20,
            temperature=0.7
        )

        interpreted_text = response.choices[0].text.strip()
        print(f"Interpreted query: {interpreted_text}") 
        return interpreted_text

    except Exception as e:
        print(f"OpenAI API error: {e}")  
        return None

# Function to scrape prices using Apify
def scrape_prices(product):
    """
    Calls Apify's Amazon scraper to fetch product prices based on the interpreted product name.
    Incorporates details from the provided OpenAPI YAML file.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APIFY_API_KEY}"
    }
    
    actor_name = "junglee~amazon-bestsellers"
    search_url = f"https://api.apify.com/v2/acts/{actor_name}/runs?token={APIFY_API_KEY}"
    
    payload = {
        "search": product,
        "maxResults": 10,
        "categoryUrls": [
            "https://www.amazon.com/Best-Sellers-Electronics-Headphones/zgbs/electronics/172541",  
            "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics"  
        ]
    }
    
    try:
        print(f"Sending request to Apify: URL={search_url}, Payload={payload}") 
        response = requests.post(search_url, headers=headers, json=payload)
        
        # Debug response
        print(f"Apify response status: {response.status_code}")
        print(f"Apify response headers: {response.headers}")
        
        # Print a sample of the response text for debugging
        response_preview = response.text[:500] + "..." if len(response.text) > 500 else response.text
        print(f"Apify response preview: {response_preview}")
        
        response.raise_for_status()
        data = response.json()

        run_id = data.get("data", {}).get("id")
        if not run_id:
            print("No run ID found in the response")
            return {"error": "No run ID found in the Apify response", "prices": [], "base_price": 0}
        
        print(f"Got Apify run ID: {run_id}")
        
        # Wait for the run to finish and get results
        max_attempts = 10
        attempts = 0
        dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?token={APIFY_API_KEY}"
        
        while attempts < max_attempts:
            attempts += 1
            print(f"Checking run status, attempt {attempts}/{max_attempts}")
            
            # First check if the run is finished
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_API_KEY}"
            status_response = requests.get(status_url, headers=headers)
            status_data = status_response.json()
            
            run_status = status_data.get("data", {}).get("status")
            print(f"Run status: {run_status}")
            
            if run_status == "SUCCEEDED":
                # Run finished, get the results
                results_response = requests.get(dataset_url, headers=headers)
                results_response.raise_for_status()
                items = results_response.json()
                print(f"Got {len(items)} items from dataset")
                break
            elif run_status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                error_msg = f"Apify run failed with status {run_status}"
                print(error_msg)
                return {"error": error_msg, "prices": [], "base_price": 0}
            else:
                # Still running, wait and try again
                print(f"Run still in progress ({run_status}), waiting 5 seconds...")
                import time
                time.sleep(5)
        
        if attempts >= max_attempts:
            return {"error": "Timed out waiting for Apify results", "prices": [], "base_price": 0}
        
        prices = []
        for item in items:
            # Debug each item to understand structure
            print(f"Processing item: {item}")
            
            # Check if we can extract a price
            price_value = None
            price_field = None
            
            # Try different possible price field names
            for field in ["price", "Price", "cost", "amount", "value"]:
                if field in item and item.get(field) is not None:
                    price_field = field
                    break
            
            if price_field:
                try:
                    # Handle different price formats
                    price_raw = item.get(price_field)
                    if isinstance(price_raw, (int, float)):
                        price_value = float(price_raw)
                    elif isinstance(price_raw, str):
                        # Clean price format, handle different currency symbols
                        price_str = price_raw.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                        price_value = float(price_str)
                
                    if price_value is not None:
                        prices.append({
                            "title": item.get("title", item.get("name", "Unknown product")),
                            "price": price_value,
                            "link": item.get("url", item.get("link", "#")),
                            "site": "Amazon",
                            "rating": item.get("rating", "No rating"),
                            "reviews": item.get("reviews", "0 reviews")
                        })
                except (ValueError, TypeError) as e:
                    print(f"Error processing price {price_raw}: {e}")
                    continue

        if not prices:
            return {"error": "No pricing data found for this product", "prices": [], "base_price": 0}

        # Base price (Amazon or lowest found)
        base_price = min(prices, key=lambda x: x["price"])["price"]

        # Calculate profit margins
        for item in prices:
            item["profit"] = round(base_price - item["price"], 2)
            item["profit_margin"] = round(((base_price - item["price"]) / item["price"]) * 100, 2)
            item["recommend"] = item["profit_margin"] >= 20

        return {"prices": prices, "base_price": base_price}

    except requests.exceptions.RequestException as e:
        error_details = str(e)
        
        # Add response details if available
        if hasattr(e, 'response') and e.response is not None:
            error_details += f"\nStatus Code: {e.response.status_code}"
            try:
                error_details += f"\nResponse: {e.response.text}"
            except:
                pass
                
        print(f"API request failed: {error_details}")
        
        return {
            "error": f"API request failed: {str(e)}",
            "details": error_details,
            "prices": [],
            "base_price": 0
        }

    except (ValueError, KeyError, TypeError) as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Data processing error: {str(e)}\n{error_trace}")
        
        return {
            "error": f"Data processing error: {str(e)}", 
            "details": error_trace,
            "prices": [], 
            "base_price": 0
        }
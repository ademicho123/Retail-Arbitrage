from flask import Flask, render_template, request, jsonify
from ai_scraper import scrape_prices, interpret_query
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search_product():
    data = request.get_json()
    user_query = data.get('query')

    if not user_query:
        return jsonify({"error": "Query is required"}), 400

    # Interpret the natural language query
    interpreted_product = interpret_query(user_query)
    if not interpreted_product:
        return jsonify({"error": "Failed to interpret the query"}), 500

    # Scrape product prices based on the interpreted query
    result_data = scrape_prices(interpreted_product)

    return jsonify(result_data)


if __name__ == '__main__':
    app.run(debug=True)

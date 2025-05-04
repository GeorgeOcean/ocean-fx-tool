from flask import Flask, request, jsonify, render_template
import requests
import json
import os

app = Flask(__name__)
TOKENS_FILE = 'tokens.json'

# Load and save token functions
def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    with open(TOKENS_FILE, 'r') as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)

# Home route
@app.route('/')
def home():
    token = request.args.get('token')
    tokens = load_tokens()

    if token not in tokens:
        return "Invalid or missing token.", 403
    if tokens[token]:
        return "This link has already been used.", 403

    return render_template('index.html', token=token)

# Compare route
@app.route('/compare', methods=['POST'])
def compare():
    data = request.json
    token = data.get("token")
    tokens = load_tokens()

    if not token or token not in tokens or tokens[token]:
        return jsonify({"error": "Invalid or used token"}), 403

    from_currency = data["from"]
    to_currency = data["to"]
    amount = float(data["amount"])
    bank_rate = float(data["bankRate"])
    date = data["date"]
    time = data["time"]
    annual_volume = float(data.get("annualVolume", 0))

    url = f"https://api.exchangerate.host/{date}?base={from_currency}&symbols={to_currency}"
    response = requests.get(url)
    print("API URL:", url)
    print("API response:", response.json())
    json_data = response.json()

    if "rates" not in json_data or to_currency not in json_data["rates"]:
        return jsonify({"error": "Could not find a rate for this date or currency."}), 400

    rate = json_data["rates"][to_currency]

    market_value = amount * rate
    bank_value = amount * bank_rate
    difference = round(market_value - bank_value, 2)
    spread_pct = round(((rate - bank_rate) / rate) * 100, 2)
    annual_savings = round((difference / amount) * annual_volume, 2) if amount > 0 else 0

    tokens[token] = True
    save_tokens(tokens)

    return jsonify({
        "company_rate": round(rate, 4),
        "bank_value": round(bank_value, 2),
        "company_value": round(market_value, 2),
        "difference": difference,
        "spread_percent": spread_pct,
        "annual_savings": annual_savings
    })

# Run the app using Render-compatible settings
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

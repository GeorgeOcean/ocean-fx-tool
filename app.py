from flask import Flask, request, jsonify, render_template
import requests
import json

app = Flask(__name__)
TOKENS_FILE = 'tokens.json'

def load_tokens():
    with open(TOKENS_FILE, 'r') as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)

@app.route('/')
def home():
    token = request.args.get('token')
    tokens = load_tokens()

    if token not in tokens:
        return "Invalid or missing token.", 403
    if tokens[token]:
        return "This link has already been used.", 403

    return render_template('index.html', token=token)

@app.route('/compare', methods=['POST'])
def compare():
    data = request.json
    token = data.get("token")
    tokens = load_tokens()

    if not token or token not in tokens or tokens[token]:
        return jsonify({"error": "Invalid or used token"}), 403

    from_currency = data["from"].upper()
    to_currency = data["to"].upper()
    amount = float(data["amount"])
    bank_rate = float(data["bankRate"])
    date = data["date"]
    annual_volume = float(data.get("annualVolume", 0))

    # API URL (EUR is fixed base for free plan)
    url = f"https://api.exchangeratesapi.io/v1/{date}?access_key=422b1b69ad8a1363ecec5ce73492f23e&symbols={from_currency},{to_currency}"
    response = requests.get(url)
    print("API URL:", url)
    print("API response:", response.json())

    json_data = response.json()

    if not json_data.get("success") or "rates" not in json_data:
        return jsonify({"error": "API error: " + str(json_data.get('error'))}), 400

    rates = json_data["rates"]

    if from_currency not in rates or to_currency not in rates:
        return jsonify({"error": "Could not find one or more currency rates."}), 400

    # Calculate derived rate using EUR as base
    from_rate = rates[from_currency]
    to_rate = rates[to_currency]
    derived_rate = to_rate / from_rate

    market_value = amount * derived_rate
    bank_value = amount * bank_rate
    difference = round(market_value - bank_value, 2)
    spread_pct = round(((derived_rate - bank_rate) / derived_rate) * 100, 2)

    # Projected annual savings
    if amount > 0 and annual_volume > 0:
        annual_savings = round((difference / amount) * annual_volume, 2)
    else:
        annual_savings = 0

    # Mark token as used
    tokens[token] = True
    save_tokens(tokens)

    return jsonify({
        "company_rate": round(derived_rate, 6),
        "bank_value": round(bank_value, 2),
        "company_value": round(market_value, 2),
        "difference": difference,
        "spread_percent": spread_pct,
        "annual_savings": annual_savings
    })

if __name__ == "__main__":
    app.run(debug=True)

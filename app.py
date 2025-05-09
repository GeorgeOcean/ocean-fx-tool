from flask import Flask, request, jsonify, render_template
import requests
import json
import os
import random
import string
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# --- Constants ---
API_KEY = '422b1b69ad8a1363ecec5ce73492f23e'
ADMIN_SECRET = 'oceankey'
SHEET_NAME = 'FX Submissions'
LOG_SHEET_TAB = 'Sheet1'
TOKENS_TAB = 'Tokens'

# --- Google Sheets Helpers ---
def get_sheet(tab_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(os.environ["GOOGLE_CREDS_JSON"]),
        scope
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(tab_name)

# --- Token Handling ---
def load_tokens():
    sheet = get_sheet(TOKENS_TAB)
    tokens = {}
    for row in sheet.get_all_records():
        tokens[row['token']] = row['used'] == 'TRUE'
    return tokens

def save_tokens(tokens):
    sheet = get_sheet(TOKENS_TAB)
    sheet.clear()
    sheet.append_row(["token", "used"])
    for token, used in tokens.items():
        sheet.append_row([token, str(used).upper()])

# --- Logging Submissions ---
def log_to_google_sheet(data):
    sheet = get_sheet(LOG_SHEET_TAB)

    mode = data.get("mode", "sell")
    if mode == "buy":
        amount_bought = data["amount"]
        amount_sold = round(data["amount"] / data["company_rate"], 2)
    else:
        amount_sold = data["amount"]
        amount_bought = round(data["amount"] * data["company_rate"], 2)

    sheet.append_row([
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data["token"],
        data["from"],
        data["to"],
        amount_sold,
        amount_bought,
        data["bankRate"],
        data["company_rate"],
        data["difference"],
        data["annual_savings"]
    ])

# --- Routes ---
@app.route('/')
def home():
    token = request.args.get('token')
    tokens = load_tokens()

    if not token:
        return "Missing token.", 403
    if token not in tokens:
        return "Invalid token.", 403
    if tokens[token]:
        return "This token has already been used.", 403

    return render_template('index.html', token=token)

@app.route('/compare', methods=['POST'])
def compare():
    data = request.json
    token = data.get("token")
    tokens = load_tokens()

    if not token or token not in tokens or tokens[token]:
        return jsonify({"error": "Invalid or used token"}), 403

    tokens[token] = True
    save_tokens(tokens)

    from_currency = data["from"]
    to_currency = data["to"]
    amount = float(data["amount"])
    bank_rate = float(data["bankRate"])
    date = data["date"]
    annual_volume = float(data.get("annualVolume", 0))
    mode = data.get("mode", "sell")

    url = f"https://api.exchangeratesapi.io/v1/{date}?access_key={API_KEY}&symbols={from_currency},{to_currency}"
    response = requests.get(url)
    json_data = response.json()

    if "rates" not in json_data or from_currency not in json_data["rates"] or to_currency not in json_data["rates"]:
        return jsonify({"error": "Could not find a rate for this date or currency."}), 400

    eur_to_from = json_data["rates"][from_currency]
    eur_to_to = json_data["rates"][to_currency]
    actual_rate = eur_to_to / eur_to_from

    if mode == "buy":
        # Buying amount in target currency
        company_value = amount / actual_rate
        bank_value = amount / bank_rate
    else:
        # Selling amount in base currency
        company_value = amount * actual_rate
        bank_value = amount * bank_rate

    savings = round(bank_value - company_value, 2) if mode == "buy" else round(company_value - bank_value, 2)
    spread_pct = round(((actual_rate - bank_rate) / actual_rate) * 100, 2)
    annual_savings = round((savings / amount) * annual_volume, 2) if amount > 0 else 0

    result = {
        "token": token,
        "from": from_currency,
        "to": to_currency,
        "amount": amount,
        "bankRate": bank_rate,
        "company_rate": round(actual_rate, 4),
        "bank_value": round(bank_value, 2),
        "company_value": round(company_value, 2),
        "difference": savings,
        "spread_percent": spread_pct,
        "annual_savings": annual_savings,
        "mode": mode
    }

    log_to_google_sheet(result)
    return jsonify(result)

@app.route('/generate-tokens')
def generate_tokens():
    admin = request.args.get("admin")
    if admin != ADMIN_SECRET:
        return "Unauthorized", 403

    tokens = load_tokens()
    new_links = []

    for _ in range(10):
        while True:
            token = 'prospect' + ''.join(random.choices(string.digits, k=5))
            if token not in tokens:
                break
        tokens[token] = False
        new_links.append(f"https://ocean-fx-tool.onrender.com/?token={token}")

    save_tokens(tokens)

    return "<h3>✅ 10 new tokens generated:</h3><ul>" + ''.join(f"<li>{link}</li>" for link in new_links) + "</ul>"

# --- Run Server ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


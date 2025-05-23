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

# --- Token Management ---
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

# --- Logging ---
def log_to_google_sheet(data):
    sheet = get_sheet(LOG_SHEET_TAB)
    sheet.append_row([
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data["token"],
        data["from"],
        data["to"],
        data["mode"],
        data["amount"],
        data["bankRate"],
        data["company_rate"],
        data["bank_value"],
        data["company_value"],
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

    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('index.html', token=token, max_date=today)

@app.route('/compare', methods=['POST'])
def compare():
    data = request.json
    token = data.get("token")
    tokens = load_tokens()

    if not token or token not in tokens or tokens[token]:
        return jsonify({"error": "Invalid or used token"}), 403

    mode = data.get("mode", "sell")
    from_currency = data["from"].upper()
    to_currency = data["to"].upper()
    amount = float(data["amount"])
    bank_rate = float(data["bankRate"])
    date = data["date"]
    annual_volume = float(data.get("annualVolume", 0))

    # First attempt: rate on the selected date
    url = f"https://api.exchangerate.host/{date}?base={from_currency}&symbols={to_currency}"
    response = requests.get(url)
    json_data = response.json()

    # If no rate found, fallback to latest available rate
    if "rates" not in json_data or to_currency not in json_data["rates"]:
        fallback_url = f"https://api.exchangerate.host/latest?base={from_currency}&symbols={to_currency}"
        response = requests.get(fallback_url)
        json_data = response.json()
        used_fallback = True
    else:
        used_fallback = False

    if "rates" not in json_data or to_currency not in json_data["rates"]:
        return jsonify({
            "error": f"Could not find any available rate for {from_currency} to {to_currency}."
        }), 400

    ocean_rate = json_data["rates"][to_currency]

    # Normalize direction if needed
    if (bank_rate > 5 and ocean_rate < 1) or (bank_rate > 1.3 and ocean_rate < 1):
        bank_rate = 1 / bank_rate

    # Value calculations
    bank_value = amount * bank_rate
    company_value = amount * ocean_rate
    difference = round(company_value - bank_value, 2)
    spread_pct = round(((ocean_rate - bank_rate) / bank_rate) * 100, 2)
    annual_savings = round((difference / amount) * annual_volume, 2) if amount > 0 else 0

    tokens[token] = True
    save_tokens(tokens)

    result = {
        "token": token,
        "from": from_currency,
        "to": to_currency,
        "mode": mode,
        "amount": amount,
        "bankRate": round(bank_rate, 6),
        "company_rate": round(ocean_rate, 6),
        "bank_value": round(bank_value, 2),
        "company_value": round(company_value, 2),
        "difference": difference,
        "spread_percent": spread_pct,
        "annual_savings": annual_savings,
        "used_fallback": used_fallback
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



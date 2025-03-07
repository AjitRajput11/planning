import dash
from dash import dcc, html, Input, Output, State, ALL
import dash_bootstrap_components as dbc
import datetime
import gspread
from google.oauth2 import service_account
import uuid

# Google Sheets API Setup
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = service_account.Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
gc = gspread.authorize(credentials)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1uQ6waQDZqJSpk5fX7VWYrDWTCtKQKqg9dvUbU0VE0iU/edit?gid=548500901#gid=548500901"
spreadsheet = gc.open_by_url(SHEET_URL)

# Fetch Retailers
retailers_sheet = spreadsheet.worksheet("Retailers")
retailers_data = retailers_sheet.get_all_records()
retailers_options = [{"label": r["Retailer Name"], "value": r["Retailer Name"]} for r in retailers_data]

# Fetch Product Categories
categories_sheet = spreadsheet.worksheet("Categories")
categories_data = categories_sheet.get_all_records()
category_options = [{"label": c["Category Name"], "value": c["Category Name"]} for c in categories_data]

# Fetch Products
products_sheet = spreadsheet.worksheet("Products")
products_data = products_sheet.get_all_records()

# Dash App Setup
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# App Layout
app.layout = dbc.Container([
    html.H2("🛒 Product Planning App"),
    
    # Retailer Dropdown
    dcc.Dropdown(id="retailer-dropdown", options=retailers_options, placeholder="Select a Retailer"),
    
    # Salesperson Info
    html.Div(id="salesperson-info", className="mt-3"),
    
    # Category Dropdown and Submission Section
    dcc.Dropdown(id="category-dropdown", options=category_options, placeholder="Select Product Category", className="mt-3"),
    html.Div(id="product-inputs", className="mt-3"),
    
    # Total Category Value Display
    html.H4(id="total-category-value", className="mt-3", style={"color": "green"}),
    
    dbc.Button("Submit", id="submit-btn", color="primary", className="mt-3"),
    html.Div(id="submission-status", className="mt-3"),
    
    # Confirmation Dialog
    dcc.ConfirmDialog(
        id="confirm-dialog",
        message="Data submitted successfully!"
    ),
    
    # Geolocation
    dcc.Store(id="geolocation", storage_type="session"),
    html.Div(id="hidden-div", style={"display": "none"})
])

# JavaScript to get geolocation
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks) {
            navigator.geolocation.getCurrentPosition(function(position) {
                var latitude = position.coords.latitude;
                var longitude = position.coords.longitude;
                var coords = latitude + "," + longitude;
                window.localStorage.setItem("geolocation", coords);
                return coords;
            }, function(error) {
                console.error(error);
                return "0,0";
            });
        }
        return "0,0";
    }
    """,
    Output("geolocation", "data"),
    Input("submit-btn", "n_clicks")
)

# Update Salesperson Info Based on Retailer Selection
@app.callback(
    Output("salesperson-info", "children"),
    Input("retailer-dropdown", "value")
)
def update_salesperson_info(selected_retailer):
    if not selected_retailer:
        return "Please select a retailer."
    
    salesperson_info = next((r for r in retailers_data if r["Retailer Name"] == selected_retailer), None)
    if not salesperson_info:
        return "Retailer not found."

    return [
        html.P(f"👤 Salesperson: {salesperson_info['Salesperson']}"),
        html.P(f"📢 Team: {salesperson_info['Team']}"),
        html.P(f"📧 Email: {salesperson_info['Email']}")
    ]

# Update Products List Based on Selected Category
@app.callback(
    Output("product-inputs", "children"),
    Input("category-dropdown", "value")
)
def update_product_inputs(selected_category):
    if not selected_category:
        return html.P("⚠️ Please select a category to enter product quantities.")

    try:
        filtered_products = [p for p in products_data if p.get("Category") == selected_category]

        if not filtered_products:
            return html.P(f"⚠️ No products found under the '{selected_category}' category.")

        inputs = []
        for product in filtered_products:
            product_name = product["Product name"]

            inputs.append(
                dbc.Row([
                    dbc.Col(html.Label(product_name), width=4),
                    dbc.Col(dcc.Input(id={"type": "input", "index": product_name}, type="number", min=0, placeholder="Enter quantity"), width=4),
                    dbc.Col(html.Div("₹0.00", id={"type": "total", "index": product_name}, style={"font-weight": "bold"}), width=4),
                ], className="mb-2")
            )

        return inputs

    except Exception as e:
        print(f"❌ Error fetching product data: {e}")
        return html.P("❌ An error occurred while loading products. Please try again.")

# Update Total Amount for Each Product & Category
@app.callback(
    [Output({"type": "total", "index": ALL}, "children"),
     Output("total-category-value", "children")],
    Input({"type": "input", "index": ALL}, "value"),
    State({"type": "input", "index": ALL}, "id"),
    prevent_initial_call=True
)
def update_total_amount(quantities, ids):
    if not quantities:
        return ["₹0.00"] * len(ids), "Total Value: ₹0.00"

    total_values = []
    category_total = 0

    for idx, quantity in enumerate(quantities):
        if quantity is None:
            quantity = 0

        product_id = ids[idx]["index"]
        product_info = next((p for p in products_data if p["Product name"] == product_id), None)
        price = float(product_info.get("Price", 0)) if product_info else 0
        total_amount = price * quantity
        total_values.append(f"₹{total_amount:.2f}")

        category_total += total_amount

    return total_values, f"Total Value: ₹{category_total:.2f}"

# Submit Data to Google Sheets
@app.callback(
    [Output("submission-status", "children"),
     Output("confirm-dialog", "displayed")],
    Input("submit-btn", "n_clicks"),
    State("retailer-dropdown", "value"),
    State("category-dropdown", "value"),
    State("salesperson-info", "children"),
    State({"type": "input", "index": ALL}, "value"),
    State("geolocation", "data"),
    prevent_initial_call=True
)
def submit_data(n_clicks, selected_retailer, selected_category, salesperson_info, input_values, geolocation):
    if not n_clicks or not selected_retailer or not selected_category:
        return "⚠️ Please complete all fields before submitting.", False

    try:
        salesperson = salesperson_info[0]["props"]["children"].split(": ")[1]
        team = salesperson_info[1]["props"]["children"].split(": ")[1]
        email = salesperson_info[2]["props"]["children"].split(": ")[1]

        submission_data = []
        filtered_products = [p for p in products_data if p.get("Category") == selected_category]

        # Extract latitude and longitude from geolocation data
        if geolocation:
            latitude, longitude = geolocation.split(",")
        else:
            latitude, longitude = "0", "0"

        print(f"Latitude: {latitude}, Longitude: {longitude}")

        for idx, product in enumerate(filtered_products):
            product_name = product["Product name"]
            quantity = input_values[idx] if idx < len(input_values) and input_values[idx] is not None else 0
            price = product.get("Price", 0) if product.get("Price") is not None else 0
            amount = price * quantity
            unique_id = str(uuid.uuid4())

            submission_data.append({
                "Unique ID": unique_id,
                "Retailer": selected_retailer,
                "Salesperson": salesperson,
                "Team": team,
                "Email": email,
                "Category": selected_category,
                "Product": product_name,
                "Quantity": quantity,
                "Amount": amount,
                "Latitude": latitude,
                "Longitude": longitude,
                "Timestamp": datetime.datetime.now().isoformat()
            })

        worksheet = spreadsheet.worksheet("Submissions")
        for data in submission_data:
            worksheet.append_row(list(data.values()))

        return f"✅ Data submitted successfully for {selected_category} in {selected_retailer}.", True

    except Exception as e:
        print(f"❌ Error processing submission: {e}")
        return "❌ An error occurred while submitting. Please try again.", False

if __name__ == "__main__":
    app.run_server(debug=True)

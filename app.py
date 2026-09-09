import os
import shutil
from pathlib import Path

import pandas as pd

from flask import Flask, redirect, render_template, request, url_for

from backend.analytics.inventory import (
    INVENTORY_COLUMNS,
    PRODUCT_COLUMNS,
    calculate_inventory_analytics,
    normalize_columns,
)
from backend.analytics.sales import calculate_sales_analytics
from backend.analytics.forecasting import forecast_sales
from backend.analytics.customers import calculate_customer_segments
from backend.analytics.profitability import calculate_profitability


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
IS_VERCEL = os.environ.get("VERCEL") == "1"

if IS_VERCEL:
    UPLOAD_FOLDER = Path("/tmp/bizpulse/uploads")
else:
    UPLOAD_FOLDER = BASE_DIR / "data" / "uploads"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

CURRENT_DATASET = UPLOAD_FOLDER / "transactions.csv"
PRODUCTS_DATASET = UPLOAD_FOLDER / "current_products.csv"
INVENTORY_DATASET = UPLOAD_FOLDER / "current_inventory.csv"

REQUIRED_COLUMNS = {
    "transaction_id",
    "date",
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "quantity",
    "unit_price",
}

LOCATION_COLUMNS = {
    "region",
    "store_id",
}

PRODUCT_COLUMNS = {
    "product_id",
    "product_name",
}

INVENTORY_COLUMNS = {
    "product_id",
    "date",
    "stock_quantity",
    "reorder_level",
}

SAMPLE_FOLDER = BASE_DIR / "data" / "sample"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard_page():
    transactions = load_current_transactions()
    products = load_current_products()
    inventory = load_current_inventory()

    if transactions is None:
        return render_template(
            "dashboard.html",
            filename="No uploaded data",
            analytics=empty_sales_analytics(),
            forecast=None,
            inventory_analytics=None,
            segmentation={
                "customers": [],
                "summary": [],
                "total_customers": 0,
            },
            profitability={
                "available": False,
                "total_revenue": 0,
                "total_cost": 0,
                "gross_profit": 0,
                "profit_margin": 0,
                "products": [],
            },
        )

    transactions = normalize_columns(transactions)

    segmentation = {
        "customers": [],
        "summary": [],
        "total_customers": 0,
    }

    if "customer_id" in transactions.columns:
        segmentation = calculate_customer_segments(transactions)

    inventory_analytics = None

    if products is not None and inventory is not None:
        inventory_analytics = calculate_inventory_analytics(
            normalize_columns(products),
            normalize_columns(inventory),
            transactions,
        )

    profitability = calculate_profitability(transactions)

    return render_template(
        "dashboard.html",
        filename="Current uploaded data",
        analytics=calculate_sales_analytics(transactions),
        forecast=forecast_sales(transactions),
        inventory_analytics=inventory_analytics,
        segmentation=segmentation,
        profitability=profitability,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_dataset():
    if request.method == "POST":
        transactions, error = read_optional_csv(
            request.files.get("dataset"),
            REQUIRED_COLUMNS,
            "transactions.csv",
        )

        if error:
            return render_template("upload.html", error=error)

        if transactions is not None:
            transaction_errors = validate_transaction_columns(transactions)

            if transaction_errors:
                return render_template(
                    "upload.html",
                    error=(
                        "transactions.csv is missing required columns: "
                        + ", ".join(transaction_errors)
                    ),
                )

        products, error = read_optional_csv(
            request.files.get("products"),
            PRODUCT_COLUMNS,
            "products.csv",
        )

        if error:
            return render_template("upload.html", error=error)

        inventory, error = read_optional_csv(
            request.files.get("inventory"),
            INVENTORY_COLUMNS,
            "inventory.csv",
        )

        if error:
            return render_template("upload.html", error=error)

        if transactions is None and products is None and inventory is None:
            return render_template(
                "upload.html",
                error="Upload at least one CSV file.",
            )

        if transactions is not None:
            transactions.to_csv(CURRENT_DATASET, index=False)
            sales_analytics = calculate_sales_analytics(transactions)
            forecast = forecast_sales(transactions)
        else:
            sales_analytics = empty_sales_analytics()

        inventory_analytics = None

        if products is not None:
            products.to_csv(PRODUCTS_DATASET, index=False)

        if inventory is not None:
            inventory.to_csv(INVENTORY_DATASET, index=False)

        if products is not None and inventory is not None:
            transaction_data = transactions

            if transaction_data is None:
                transaction_data = pd.DataFrame(
                    columns=["product_id", "date", "quantity"]
                )

            inventory_analytics = calculate_inventory_analytics(
                products,
                inventory,
                transaction_data,
            )

        uploaded_files = [
            name for name, dataframe in (
                ("transactions.csv", transactions),
                ("products.csv", products),
                ("inventory.csv", inventory),
            )
            if dataframe is not None
        ]

        return redirect(url_for("dashboard_page"))

    return render_template("upload.html")


def validate_csv_file(file, required_columns, label):
    if not file or not file.filename:
        return None, f"Please select the {label} file."

    if not file.filename.lower().endswith(".csv"):
        return None, f"{label} must be a CSV file."

    try:
        dataframe = pd.read_csv(file)
    except Exception:
        return None, f"The {label} file could not be read."

    dataframe = normalize_columns(dataframe)

    missing_columns = sorted(
        set(required_columns) - set(dataframe.columns)
    )

    if missing_columns:
        return None, (
            f"{label} is missing required columns: "
            + ", ".join(missing_columns)
        )

    return dataframe, None


def read_optional_csv(file, required_columns, label):
    if not file or not file.filename:
        return None, None

    if not file.filename.lower().endswith(".csv"):
        return None, f"{label} must be a CSV file."

    try:
        dataframe = pd.read_csv(file)
    except Exception:
        return None, f"{label} could not be read."

    dataframe = normalize_columns(dataframe)

    missing_columns = sorted(
        set(required_columns) - set(dataframe.columns)
    )

    if missing_columns:
        return None, (
            f"{label} is missing required columns: "
            + ", ".join(missing_columns)
        )

    return dataframe, None


def empty_sales_analytics():
    return {
        "total_revenue": 0,
        "total_orders": 0,
        "total_units": 0,
        "average_order_value": 0,
        "products": [],
        "daily_revenue": [],
        "categories": [],
        "regions": [],
    }


def validate_transaction_columns(dataframe):
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if not (LOCATION_COLUMNS & set(dataframe.columns)):
        missing_columns.add("region or store_id")

    return sorted(missing_columns)


@app.route("/analytics")
def analytics_page():
    transactions = load_csv(CURRENT_DATASET)

    if transactions is None:
        return redirect(url_for("upload_dataset"))

    return render_template(
        "analytics.html",
        analytics=calculate_sales_analytics(transactions),
    )


@app.route("/inventory")
def inventory_page():
    products = load_csv(PRODUCTS_DATASET)
    inventory = load_csv(INVENTORY_DATASET)
    transactions = load_csv(CURRENT_DATASET)

    if products is None or inventory is None:
        return redirect(url_for("upload_dataset"))

    if transactions is None:
        transactions = pd.DataFrame(
            columns=["product_id", "date", "quantity"]
        )

    inventory_data = calculate_inventory_analytics(
        normalize_columns(products),
        normalize_columns(inventory),
        normalize_columns(transactions),
    )

    return render_template(
        "inventory.html",
        inventory_analytics=inventory_data,
    )


@app.route("/forecast")
def forecast_page():
    transactions = load_csv(CURRENT_DATASET)

    if transactions is None:
        return redirect(url_for("upload_dataset"))

    return render_template(
        "forecast.html",
        forecast=forecast_sales(normalize_columns(transactions)),
    )


@app.route("/customers")
def customers_page():
    transactions = load_current_transactions()

    if transactions is None:
        return redirect(url_for("upload_dataset"))

    transactions = normalize_columns(transactions)

    if "customer_id" not in transactions.columns:
        return render_template(
            "customers.html",
            error=(
                "Customer segmentation requires the "
                "customer_id column."
            ),
            segmentation={
                "customers": [],
                "summary": [],
                "total_customers": 0,
            },
        )

    return render_template(
        "customers.html",
        segmentation=calculate_customer_segments(transactions),
        error=None,
    )


@app.route("/profitability")
def profitability_page():
    transactions = load_current_transactions()

    if transactions is None:
        return redirect(url_for("upload_dataset"))

    transactions = normalize_columns(transactions)

    return render_template(
        "profitability.html",
        profitability=calculate_profitability(transactions),
    )


@app.route("/use-sample-data", methods=["POST"])
def use_sample_data():
    sample_files = {
        "transactions.csv": CURRENT_DATASET,
        "current_products.csv": PRODUCTS_DATASET,
        "current_inventory.csv": INVENTORY_DATASET,
    }

    for filename, destination in sample_files.items():
        source = SAMPLE_FOLDER / filename

        if source.exists():
            shutil.copyfile(source, destination)

    return redirect(url_for("dashboard_page"))


def load_csv(path):
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_current_transactions():
    return pd.read_csv(CURRENT_DATASET) if CURRENT_DATASET.exists() else None


def load_current_products():
    return pd.read_csv(PRODUCTS_DATASET) if PRODUCTS_DATASET.exists() else None


def load_current_inventory():
    return pd.read_csv(INVENTORY_DATASET) if INVENTORY_DATASET.exists() else None

if __name__ == "__main__":
    app.run(debug=True)

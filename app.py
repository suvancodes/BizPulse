from pathlib import Path

import pandas as pd
from flask import Flask, render_template, request

from backend.analytics.inventory import (
    INVENTORY_COLUMNS,
    PRODUCT_COLUMNS,
    calculate_inventory_analytics,
    normalize_columns,
)
from backend.analytics.sales import calculate_sales_analytics


app = Flask(__name__)

UPLOAD_FOLDER = Path("data/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

CURRENT_DATASET = UPLOAD_FOLDER / "transactions.csv"
PRODUCTS_DATASET = UPLOAD_FOLDER / "current_products.csv"
INVENTORY_DATASET = UPLOAD_FOLDER / "current_inventory.csv"

REQUIRED_COLUMNS = {
    "transaction_id",
    "date",
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


@app.route("/")
def index():
    return render_template("index.html")


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

        return render_template(
            "dashboard.html",
            filename="Current uploaded data",
            analytics=sales_analytics,
            inventory_analytics=inventory_analytics,
        )

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


if __name__ == "__main__":
    app.run(debug=True)

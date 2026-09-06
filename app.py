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
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "quantity",
    "unit_price",
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

        if not any(
            dataframe is not None
            for dataframe in (transactions, products, inventory)
        ):
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
            filename=", ".join(uploaded_files),
            analytics=sales_analytics,
            inventory_analytics=inventory_analytics,
        )

    return render_template("upload.html")


@app.route("/inventory-upload", methods=["GET", "POST"])
def upload_inventory_files():
    if request.method == "POST":
        products, products_error = validate_csv_file(
            request.files.get("products"),
            PRODUCT_COLUMNS,
            "products.csv",
        )

        if products_error:
            return render_template("inventory_upload.html", error=products_error)

        inventory, inventory_error = validate_csv_file(
            request.files.get("inventory"),
            INVENTORY_COLUMNS,
            "inventory.csv",
        )

        if inventory_error:
            return render_template("inventory_upload.html", error=inventory_error)

        if not Path(CURRENT_DATASET).exists():
            return render_template(
                "inventory_upload.html",
                error="Upload transactions.csv before inventory files.",
            )

        transactions = pd.read_csv(CURRENT_DATASET)

        products.to_csv(PRODUCTS_DATASET, index=False)
        inventory.to_csv(INVENTORY_DATASET, index=False)

        inventory_analytics = calculate_inventory_analytics(
            products,
            inventory,
            transactions,
        )

        return render_template(
            "dashboard.html",
            filename="current_transactions.csv",
            analytics=calculate_sales_analytics(transactions),
            inventory_analytics=inventory_analytics,
        )

    return render_template("inventory_upload.html")


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
    missing_columns = sorted(required_columns - set(dataframe.columns))

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
    except Exception as error:
        return None, f"{label} could not be read: {error}"

    dataframe = normalize_columns(dataframe)
    missing_columns = sorted(
        required_columns - set(dataframe.columns)
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


if __name__ == "__main__":
    app.run(debug=True)

from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from backend.auth import (
    login_required,
    validate_csrf_request,
    validate_csrf_token,
)
from backend.analytics.customers import calculate_customer_segments
from backend.analytics.forecasting import forecast_sales
from backend.analytics.inventory import (
    calculate_inventory_analytics,
    normalize_columns,
)
from backend.analytics.profitability import calculate_profitability
from backend.analytics.sales import calculate_sales_analytics
from backend.data_store import (
    DataStoreError,
    append_transactions as store_append_transactions,
    load_inventory,
    load_products,
    load_transactions,
    delete_record,
    delete_inventory,
    replace_inventory,
    replace_products,
    replace_transactions,
    save_inventory,
    save_product,
    save_transaction,
)


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_FOLDER = BASE_DIR / "data" / "sample"

REQUIRED_COLUMNS = {
    "transaction_id",
    "date",
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "quantity",
    "unit_price",
    "cost_price",
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


def register_routes(app: Flask):
    @app.errorhandler(DataStoreError)
    def handle_data_store_error(error):
        return render_template(
            "error.html",
            error=str(error),
        ), 503

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/dashboard")
    @login_required
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
    @login_required
    def upload_dataset():
        if request.method == "POST":
            csrf_error = validate_csrf_token()
            if csrf_error:
                return render_template("upload.html", error=csrf_error), 400

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

                transaction_errors = validate_transaction_rows(transactions)
                if transaction_errors:
                    return render_template(
                        "upload.html",
                        error="Transactions import errors: "
                        + " ".join(transaction_errors),
                    )

            products, error = read_optional_csv(
                request.files.get("products"),
                PRODUCT_COLUMNS,
                "products.csv",
            )

            if error:
                return render_template("upload.html", error=error)

            if products is not None:
                product_errors = validate_product_rows(products)
                if product_errors:
                    return render_template(
                        "upload.html",
                        error="Products import errors: "
                        + " ".join(product_errors),
                    )

            inventory, error = read_optional_csv(
                request.files.get("inventory"),
                INVENTORY_COLUMNS,
                "inventory.csv",
            )

            if error:
                return render_template("upload.html", error=error)

            if inventory is not None:
                inventory_errors = validate_inventory_rows(inventory)
                if inventory_errors:
                    return render_template(
                        "upload.html",
                        error="Inventory import errors: "
                        + " ".join(inventory_errors),
                    )

            if transactions is None and products is None and inventory is None:
                return render_template(
                    "upload.html",
                    error="Upload at least one CSV file.",
                )

            try:
                if transactions is not None:
                    replace_transactions(transactions)
                    calculate_sales_analytics(transactions)
                    forecast_sales(transactions)

                if products is not None:
                    replace_products(products)

                if inventory is not None:
                    replace_inventory(inventory)

                if products is not None and inventory is not None:
                    transaction_data = transactions

                    if transaction_data is None:
                        transaction_data = pd.DataFrame(
                            columns=["product_id", "date", "quantity"]
                        )

                    calculate_inventory_analytics(
                        products,
                        inventory,
                        transaction_data,
                    )
            except DataStoreError as exc:
                return render_template("upload.html", error=str(exc)), 503

            flash(
                "Import complete: "
                f"{len(transactions) if transactions is not None else 0} "
                "transactions, "
                f"{len(products) if products is not None else 0} products, "
                f"{len(inventory) if inventory is not None else 0} "
                "inventory records saved.",
                "success",
            )
            return redirect(url_for("dashboard_page"))

        return render_template("upload.html")

    @app.route("/create-data", methods=["GET", "POST"])
    @login_required
    def create_data():
        if request.method == "POST":
            csrf_error = validate_csrf_token()
            if csrf_error:
                return render_template(
                    "create_data.html",
                    error=csrf_error,
                    rows=transaction_rows_from_form(request.form),
                ), 400

            transactions, error = build_transactions_from_form(request.form)

            if error:
                return render_template(
                    "create_data.html",
                    error=error,
                    rows=transaction_rows_from_form(request.form),
                )

            try:
                replace_transactions_dataset(transactions)
            except ValueError as exc:
                return render_template(
                    "create_data.html",
                    error=str(exc),
                    rows=transaction_rows_from_form(request.form),
                )
            except OSError:
                return render_template(
                    "create_data.html",
                    error=(
                        "The transactions could not be saved. "
                        "Please try again."
                    ),
                    rows=transaction_rows_from_form(request.form),
                )

            return redirect(url_for("dashboard_page"))

        return render_template("create_data.html", rows=[{}])

    @app.route("/analytics")
    @login_required
    def analytics_page():
        transactions = load_current_transactions()

        if transactions is None:
            return redirect(url_for("upload_dataset"))

        return render_template(
            "analytics.html",
            analytics=calculate_sales_analytics(transactions),
        )

    @app.route("/inventory")
    @login_required
    def inventory_page():
        products = load_current_products()
        inventory = load_current_inventory()
        transactions = load_current_transactions()

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
    @login_required
    def forecast_page():
        transactions = load_current_transactions()

        if transactions is None:
            return redirect(url_for("upload_dataset"))

        return render_template(
            "forecast.html",
            forecast=forecast_sales(normalize_columns(transactions)),
        )

    @app.route("/customers")
    @login_required
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
    @login_required
    def profitability_page():
        transactions = load_current_transactions()

        if transactions is None:
            return redirect(url_for("upload_dataset"))

        transactions = normalize_columns(transactions)

        return render_template(
            "profitability.html",
            profitability=calculate_profitability(transactions),
        )

    @app.route("/api/transactions", methods=["POST"])
    @login_required
    def create_transaction_api():
        return save_transaction_api()

    @app.route("/api/transactions/<transaction_id>", methods=["PUT", "DELETE"])
    @login_required
    def update_or_delete_transaction_api(transaction_id):
        if request.method == "DELETE":
            error = validate_csrf_request()
            if error:
                return jsonify({"error": error}), 400
            try:
                delete_record("transactions", "transaction_id", transaction_id)
            except DataStoreError as exc:
                return jsonify({"error": str(exc)}), 503
            return "", 204

        payload = request.get_json(silent=True) or {}
        payload["transaction_id"] = transaction_id
        return save_transaction_api(payload)

    @app.route("/api/products", methods=["POST"])
    @login_required
    def create_product_api():
        return save_product_api()

    @app.route("/api/products/<product_id>", methods=["PUT", "DELETE"])
    @login_required
    def update_or_delete_product_api(product_id):
        if request.method == "DELETE":
            error = validate_csrf_request()
            if error:
                return jsonify({"error": error}), 400
            try:
                delete_record("products", "product_id", product_id)
            except DataStoreError as exc:
                return jsonify({"error": str(exc)}), 503
            return "", 204

        payload = request.get_json(silent=True) or {}
        payload["product_id"] = product_id
        return save_product_api(payload)

    @app.route("/api/inventory", methods=["POST"])
    @login_required
    def create_inventory_api():
        return save_inventory_api()

    @app.route(
        "/api/inventory/<product_id>/<inventory_date>",
        methods=["PUT", "DELETE"],
    )
    @login_required
    def update_or_delete_inventory_api(product_id, inventory_date):
        if request.method == "DELETE":
            error = validate_csrf_request()
            if error:
                return jsonify({"error": error}), 400
            try:
                delete_inventory(product_id, inventory_date)
            except DataStoreError as exc:
                return jsonify({"error": str(exc)}), 503
            return "", 204

        payload = request.get_json(silent=True) or {}
        payload["product_id"] = product_id
        payload["date"] = inventory_date
        return save_inventory_api(payload)

    @app.route("/use-sample-data", methods=["POST"])
    @login_required
    def use_sample_data():
        error = validate_csrf_token()
        if error:
            return render_template("upload.html", error=error), 400

        try:
            transactions = pd.read_csv(SAMPLE_FOLDER / "transactions.csv")
            products = pd.read_csv(SAMPLE_FOLDER / "current_products.csv")
            inventory = pd.read_csv(SAMPLE_FOLDER / "current_inventory.csv")
            transaction_errors = validate_transaction_columns(
                normalize_columns(transactions)
            )
            if transaction_errors:
                return render_template(
                    "upload.html",
                    error=(
                        "The sample transactions file is missing required "
                        "columns: " + ", ".join(transaction_errors)
                    ),
                ), 400
            transaction_errors = validate_transaction_rows(transactions)
            if transaction_errors:
                return render_template(
                    "upload.html",
                    error=(
                        "The sample transactions file contains invalid "
                        "rows: " + " ".join(transaction_errors[:3])
                    ),
                ), 400
            replace_transactions(transactions)
            replace_products(products)
            replace_inventory(inventory)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            return render_template(
                "upload.html",
                error="The sample data could not be read.",
            ), 400
        except DataStoreError as exc:
            return render_template("upload.html", error=str(exc)), 503

        flash("Sample transactions, products, and inventory were saved.", "success")
        return redirect(url_for("dashboard_page"))


def save_transaction_api(payload=None):
    error = validate_csrf_request()
    if error:
        return jsonify({"error": error}), 400

    payload = payload if payload is not None else request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    values = {
        key: str(value) if value is not None else ""
        for key, value in payload.items()
    }
    transaction, validation_error = build_transaction_from_values(values)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    try:
        saved = save_transaction(transaction)
    except (DataStoreError, ValueError, TypeError) as exc:
        message = str(exc) if isinstance(exc, DataStoreError) else (
            "The transaction contains an invalid value."
        )
        return jsonify({"error": message}), 503
    return jsonify({"data": saved}), 200


def save_product_api(payload=None):
    error = validate_csrf_request()
    if error:
        return jsonify({"error": error}), 400

    payload = payload if payload is not None else request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    product_id = str(payload.get("product_id", "")).strip()
    product_name = str(payload.get("product_name", "")).strip()
    if not product_id or not product_name:
        return jsonify({
            "error": "Product ID and product name are required.",
        }), 400

    record = {
        "product_id": product_id,
        "product_name": product_name,
        "category": payload.get("category"),
        "size": payload.get("size"),
        "unit_price": payload.get("unit_price"),
        "cost_price": payload.get("cost_price"),
        "brand": payload.get("brand"),
        "description": payload.get("description"),
    }
    try:
        saved = save_product(record)
    except (DataStoreError, ValueError, TypeError) as exc:
        message = str(exc) if isinstance(exc, DataStoreError) else (
            "The product contains an invalid value."
        )
        return jsonify({"error": message}), 503
    return jsonify({"data": saved}), 200


def save_inventory_api(payload=None):
    error = validate_csrf_request()
    if error:
        return jsonify({"error": error}), 400

    payload = payload if payload is not None else request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    product_id = str(payload.get("product_id", "")).strip()
    inventory_date = str(payload.get("date", "")).strip()
    if not product_id or not inventory_date:
        return jsonify({
            "error": "Product ID and inventory date are required.",
        }), 400
    if pd.isna(pd.to_datetime(inventory_date, errors="coerce")):
        return jsonify({"error": "Inventory date must be valid."}), 400

    record = {
        "product_id": product_id,
        "date": inventory_date,
        "stock_quantity": payload.get("stock_quantity"),
        "reorder_level": payload.get("reorder_level"),
    }
    try:
        saved = save_inventory(record)
    except (DataStoreError, ValueError, TypeError) as exc:
        message = str(exc) if isinstance(exc, DataStoreError) else (
            "The inventory record contains an invalid value."
        )
        return jsonify({"error": message}), 503
    return jsonify({"data": saved}), 200


def validate_csv_file(file, required_columns, label):
    if not file or not file.filename:
        return None, f"Please select the {label} file."

    if not file.filename.lower().endswith(".csv"):
        return None, f"{label} must be a CSV file."

    try:
        dataframe = pd.read_csv(file)
    except (
        OSError,
        ValueError,
        pd.errors.ParserError,
        UnicodeDecodeError,
    ):
        return None, f"The {label} file could not be read."

    dataframe = normalize_columns(dataframe)
    missing_columns = sorted(set(required_columns) - set(dataframe.columns))

    if missing_columns:
        return None, (
            f"{label} is missing required columns: "
            + ", ".join(missing_columns)
        )

    return dataframe, None


def build_transaction_from_form(form):
    transactions, error = build_transactions_from_form(form)
    if error:
        return None, error
    return transactions[0], None


def build_transactions_from_form(form):
    rows = transaction_rows_from_form(form)
    if not rows:
        return [], "Add at least one transaction row."

    transactions = []
    for row_number, row in enumerate(rows, start=1):
        transaction, error = build_transaction_from_values(row)
        if error:
            return [], f"Row {row_number}: {error}"
        transactions.append(transaction)

    transaction_ids = [row["transaction_id"] for row in transactions]
    duplicate_ids = sorted(
        {
            transaction_id
            for transaction_id in transaction_ids
            if transaction_ids.count(transaction_id) > 1
        }
    )
    if duplicate_ids:
        return [], (
            "Transaction IDs must be unique. Duplicate ID(s): "
            + ", ".join(duplicate_ids)
            + "."
        )

    return transactions, None


def transaction_rows_from_form(form):
    fields = (
        "transaction_id",
        "date",
        "customer_id",
        "product_id",
        "product_name",
        "category",
        "quantity",
        "unit_price",
        "cost_price",
        "region",
        "discount",
    )
    def values_for(field):
        key = f"{field}[]"
        if hasattr(form, "getlist"):
            return form.getlist(key)
        if key not in form and field in form:
            value = form.get(field, "")
            return value if isinstance(value, list) else [value]
        value = form.get(key, [])
        return value if isinstance(value, list) else [value]

    row_count = len(values_for("transaction_id"))
    return [
        {
            field: values_for(field)[index].strip()
            if index < len(values_for(field))
            else ""
            for field in fields
        }
        for index in range(row_count)
    ]


def build_transaction_from_values(values):
    raw_values = values
    field_labels = {
        "transaction_id": "Transaction ID",
        "date": "Date",
        "customer_id": "Customer ID",
        "product_id": "Product ID",
        "product_name": "Product name",
        "category": "Category",
        "quantity": "Quantity",
        "unit_price": "Unit price",
        "cost_price": "Cost price",
        "region": "Region or store ID",
    }
    values = {
        field: raw_values.get(field, "").strip()
        for field in field_labels
    }
    values["discount"] = raw_values.get("discount", "").strip()

    missing = [
        label
        for field, label in field_labels.items()
        if not values[field]
    ]
    if missing:
        return None, "Please complete: " + ", ".join(missing) + "."

    try:
        transaction_date = datetime.strptime(
            values["date"],
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None, "Date must be a valid date in YYYY-MM-DD format."

    numeric_values = {}
    for field, label in (
        ("quantity", "Quantity"),
        ("unit_price", "Unit price"),
        ("cost_price", "Cost price"),
    ):
        try:
            numeric_values[field] = float(values[field])
        except ValueError:
            return None, f"{label} must be a valid number."

    if numeric_values["quantity"] <= 0:
        return None, "Quantity must be greater than zero."

    for field, label in (
        ("unit_price", "Unit price"),
        ("cost_price", "Cost price"),
    ):
        if numeric_values[field] < 0:
            return None, f"{label} cannot be negative."

    discount = values.get("discount", "").strip()
    if discount:
        try:
            numeric_values["discount"] = float(discount)
        except ValueError:
            return None, "Discount must be a valid number."
        if numeric_values["discount"] < 0:
            return None, "Discount cannot be negative."

    transaction = {
        "transaction_id": values["transaction_id"],
        "date": transaction_date.isoformat(),
        "customer_id": values["customer_id"],
        "product_id": values["product_id"],
        "product_name": values["product_name"],
        "category": values["category"],
        "quantity": numeric_values["quantity"],
        "unit_price": numeric_values["unit_price"],
        "cost_price": numeric_values["cost_price"],
        "region": values["region"],
    }
    if "discount" in numeric_values:
        transaction["discount"] = numeric_values["discount"]

    return transaction, None


def append_transaction(transaction):
    append_transactions([transaction])


def replace_transactions_dataset(new_transactions):
    if not new_transactions:
        raise ValueError("Add at least one transaction row.")

    transaction_ids = [
        transaction["transaction_id"] for transaction in new_transactions
    ]
    duplicate_ids = sorted(
        {
            transaction_id
            for transaction_id in transaction_ids
            if transaction_ids.count(transaction_id) > 1
        }
    )
    if duplicate_ids:
        raise ValueError(
            "Transaction IDs must be unique. Duplicate ID(s): "
            + ", ".join(duplicate_ids)
            + "."
        )

    rows = []
    for transaction in new_transactions:
        row = transaction.copy()
        if "region" not in row and "store_id" in row:
            row["region"] = row.pop("store_id")
        rows.append(row)

    dataset = pd.DataFrame(rows)
    dataset = dataset.loc[:, list(dict.fromkeys(dataset.columns))]
    try:
        replace_transactions(dataset)
    except DataStoreError as exc:
        raise OSError("The transactions could not be saved.") from exc


def append_transactions(new_transactions):
    if not new_transactions:
        raise ValueError("Add at least one transaction row.")

    transactions = load_current_transactions()

    if transactions is None:
        transactions = pd.DataFrame(
            columns=sorted(REQUIRED_COLUMNS) + ["region"]
        )
    else:
        transactions = normalize_columns(transactions)

    missing_columns = validate_transaction_columns(transactions)
    if missing_columns:
        raise ValueError(
            "The current transaction data is missing required columns: "
            + ", ".join(missing_columns)
        )

    existing_ids = transactions["transaction_id"].astype(str).str.strip()
    existing_ids = set(existing_ids)
    new_ids = [transaction["transaction_id"] for transaction in new_transactions]
    duplicate_ids = sorted(
        {transaction_id for transaction_id in new_ids if transaction_id in existing_ids}
    )
    if duplicate_ids:
        raise ValueError(
            "Transaction ID(s) already exist: "
            + ", ".join(duplicate_ids)
            + "."
        )

    normalized_new_transactions = []
    for transaction in new_transactions:
        transaction = transaction.copy()
        if "region" not in transaction and "store_id" in transaction:
            transaction["region"] = transaction.pop("store_id")
        normalized_new_transactions.append(transaction)

    try:
        store_append_transactions(normalized_new_transactions)
    except DataStoreError as exc:
        raise ValueError(str(exc)) from exc


def read_optional_csv(file, required_columns, label):
    if not file or not file.filename:
        return None, None

    if not file.filename.lower().endswith(".csv"):
        return None, f"{label} must be a CSV file."

    try:
        dataframe = pd.read_csv(file)
    except (
        OSError,
        ValueError,
        pd.errors.ParserError,
        UnicodeDecodeError,
    ):
        return None, f"{label} could not be read."

    dataframe = normalize_columns(dataframe)
    missing_columns = sorted(set(required_columns) - set(dataframe.columns))

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


def validate_transaction_rows(dataframe):
    normalized = normalize_columns(dataframe)
    errors = []
    transaction_ids = normalized["transaction_id"].fillna("").astype(str).str.strip()
    if (transaction_ids == "").any():
        errors.append("Transaction IDs cannot be empty.")

    duplicate_ids = sorted(
        transaction_ids[transaction_ids.duplicated(keep=False)].unique()
    )
    if any(duplicate_ids):
        errors.append(
            "Duplicate transaction IDs: "
            + ", ".join(item for item in duplicate_ids if item)
            + "."
        )

    for index, row in normalized.iterrows():
        row_number = index + 2
        if pd.isna(pd.to_datetime(row.get("date"), errors="coerce")):
            errors.append(f"Row {row_number} has an invalid date.")
        for field in ("quantity", "unit_price", "cost_price", "discount"):
            if field not in row:
                continue
            value = pd.to_numeric(row.get(field), errors="coerce")
            if pd.isna(value):
                if field != "discount" or str(row.get(field, "")).strip():
                    errors.append(
                        f"Row {row_number} has an invalid {field}."
                    )
            elif value < 0 or (field == "quantity" and value <= 0):
                errors.append(
                    f"Row {row_number} has an invalid {field} value."
                )
        if len(errors) >= 20:
            break

    return errors[:20]


def validate_product_rows(dataframe):
    normalized = normalize_columns(dataframe)
    product_ids = normalized["product_id"].fillna("").astype(str).str.strip()
    errors = []

    duplicate_ids = sorted(
        product_ids[product_ids.duplicated(keep=False)].unique()
    )
    duplicate_ids = [item for item in duplicate_ids if item]
    if duplicate_ids:
        errors.append(
            "Duplicate product IDs: " + ", ".join(duplicate_ids) + "."
        )

    if (product_ids == "").any():
        errors.append("Product IDs cannot be empty.")
    if (
        normalized["product_name"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .any()
    ):
        errors.append("Product names cannot be empty.")
    return errors[:20]


def validate_inventory_rows(dataframe):
    normalized = normalize_columns(dataframe)
    errors = []
    keys = (
        normalized["product_id"].fillna("").astype(str).str.strip()
        + "|"
        + normalized["date"].fillna("").astype(str).str.strip()
    )
    duplicate_keys = sorted(keys[keys.duplicated(keep=False)].unique())
    if duplicate_keys:
        errors.append("Duplicate inventory product/date records found.")

    invalid_dates = pd.to_datetime(normalized["date"], errors="coerce").isna()
    if invalid_dates.any():
        errors.append("Inventory contains invalid dates.")

    for field in ("stock_quantity", "reorder_level"):
        values = pd.to_numeric(normalized[field], errors="coerce")
        if values.isna().any() or (values < 0).any():
            errors.append(
                f"Inventory contains invalid {field} values."
            )
    return errors[:20]


def load_current_transactions():
    return load_transactions()


def load_current_products():
    return load_products()


def load_current_inventory():
    return load_inventory()

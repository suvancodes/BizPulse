from __future__ import annotations

from typing import Any

import pandas as pd
from flask import g
from postgrest.exceptions import APIError

from backend.auth import get_supabase_client
from backend.analytics.inventory import normalize_columns


class DataStoreError(RuntimeError):
    """Raised when a user's Supabase data cannot be read or written."""


TRANSACTION_COLUMNS = [
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
]

PRODUCT_COLUMNS = [
    "product_id",
    "product_name",
    "category",
    "size",
    "unit_price",
    "cost_price",
    "brand",
    "description",
]

INVENTORY_COLUMNS = [
    "product_id",
    "date",
    "stock_quantity",
    "reorder_level",
]


def load_transactions() -> pd.DataFrame | None:
    rows = _select_rows(
        "transactions",
        [
            "transaction_id",
            "transaction_date",
            "customer_id",
            "product_id",
            "product_name",
            "category",
            "quantity",
            "unit_price",
            "cost_price",
            "region",
            "discount",
        ],
    )
    if not rows:
        return None

    dataframe = pd.DataFrame(rows).rename(
        columns={"transaction_date": "date"}
    )
    return normalize_columns(dataframe)


def load_products() -> pd.DataFrame | None:
    rows = _select_rows("products", PRODUCT_COLUMNS)
    if not rows:
        return None
    return normalize_columns(pd.DataFrame(rows))


def load_inventory() -> pd.DataFrame | None:
    rows = _select_rows(
        "inventory",
        [
            "product_id",
            "inventory_date",
            "stock_quantity",
            "reorder_level",
        ],
    )
    if not rows:
        return None

    dataframe = pd.DataFrame(rows).rename(
        columns={"inventory_date": "date"}
    )
    return normalize_columns(dataframe)


def replace_transactions(dataframe: pd.DataFrame) -> None:
    normalized = normalize_columns(dataframe)
    records = [
        _transaction_record(row)
        for row in normalized.to_dict("records")
    ]
    _replace_rows("transactions", records)


def replace_products(dataframe: pd.DataFrame) -> None:
    normalized = normalize_columns(dataframe)
    records = [
        _product_record(row)
        for row in normalized.to_dict("records")
    ]
    _replace_rows("products", records)


def replace_inventory(dataframe: pd.DataFrame) -> None:
    normalized = normalize_columns(dataframe)
    records = [
        _inventory_record(row)
        for row in normalized.to_dict("records")
    ]
    _replace_rows("inventory", records)


def append_transactions(records: list[dict[str, Any]]) -> None:
    if not records:
        raise DataStoreError("Add at least one transaction row.")

    _insert_rows(
        "transactions",
        [_transaction_record(record) for record in records],
    )


def save_transaction(record: dict[str, Any]) -> dict[str, Any]:
    return _upsert_row(
        "transactions",
        _transaction_record(record),
        "user_id,transaction_id",
    )


def save_product(record: dict[str, Any]) -> dict[str, Any]:
    return _upsert_row(
        "products",
        _product_record(record),
        "user_id,product_id",
    )


def save_inventory(record: dict[str, Any]) -> dict[str, Any]:
    return _upsert_row(
        "inventory",
        _inventory_record(record),
        "user_id,product_id,inventory_date",
    )


def delete_record(table: str, column: str, value: str) -> None:
    try:
        (
            get_supabase_client()
            .table(table)
            .delete()
            .eq("user_id", _user_id())
            .eq(column, value)
            .execute()
        )
    except APIError as exc:
        raise DataStoreError(
            f"Could not delete the {table} record."
        ) from exc


def delete_inventory(product_id: str, inventory_date: str) -> None:
    try:
        (
            get_supabase_client()
            .table("inventory")
            .delete()
            .eq("user_id", _user_id())
            .eq("product_id", product_id)
            .eq("inventory_date", inventory_date)
            .execute()
        )
    except APIError as exc:
        raise DataStoreError(
            "Could not delete the inventory record."
        ) from exc


def _select_rows(table: str, columns: list[str]) -> list[dict[str, Any]]:
    try:
        response = (
            get_supabase_client()
            .table(table)
            .select(",".join(columns))
            .eq("user_id", _user_id())
            .execute()
        )
    except APIError as exc:
        if getattr(exc, "code", None) == "PGRST205":
            raise DataStoreError(
                "Supabase tables are not configured yet. Run the SQL "
                "migration in database_migrations/20261026170000_initial_schema.sql "
                "from the Supabase SQL Editor, then try again."
            ) from exc
        raise DataStoreError(
            f"Could not load {table} data from Supabase."
        ) from exc
    return response.data or []


def _upsert_row(
    table: str,
    record: dict[str, Any],
    conflict_columns: str,
) -> dict[str, Any]:
    try:
        response = (
            get_supabase_client()
            .table(table)
            .upsert([record], on_conflict=conflict_columns)
            .execute()
        )
    except APIError as exc:
        raise DataStoreError(
            f"Could not save the {table} record."
        ) from exc

    return (response.data or [record])[0]


def _replace_rows(table: str, records: list[dict[str, Any]]) -> None:
    client = get_supabase_client()
    user_id = _user_id()
    try:
        client.table(table).delete().eq("user_id", user_id).execute()
        if records:
            _insert_in_batches(client, table, records)
    except APIError as exc:
        raise _data_store_api_error(
            f"Could not save {table} data to Supabase.", exc
        ) from exc


def _insert_rows(table: str, records: list[dict[str, Any]]) -> None:
    try:
        client = get_supabase_client()
        _insert_in_batches(client, table, records)
    except APIError as exc:
        raise _data_store_api_error(
            f"Could not save {table} data to Supabase.", exc
        ) from exc


def _insert_in_batches(
    client: Any,
    table: str,
    records: list[dict[str, Any]],
    batch_size: int = 500,
) -> None:
    for start in range(0, len(records), batch_size):
        client.table(table).insert(
            records[start:start + batch_size]
        ).execute()


def _data_store_api_error(message: str, error: APIError) -> DataStoreError:
    code = getattr(error, "code", None)
    detail = getattr(error, "message", None) or str(error).strip()
    if code and detail and code not in detail:
        detail = f"{code}: {detail}"
    if detail:
        return DataStoreError(f"{message} ({detail})")
    return DataStoreError(message)


def _transaction_record(row: dict[str, Any]) -> dict[str, Any]:
    region = row.get("region", row.get("store_id", ""))
    return {
        "user_id": _user_id(),
        "transaction_id": _required_text(row, "transaction_id"),
        "transaction_date": _required_text(row, "date"),
        "customer_id": _required_text(row, "customer_id"),
        "product_id": _required_text(row, "product_id"),
        "product_name": _required_text(row, "product_name"),
        "category": _required_text(row, "category"),
        "quantity": _number(row, "quantity"),
        "unit_price": _number(row, "unit_price"),
        "cost_price": _number(row, "cost_price"),
        "region": _required_text({"region": region}, "region"),
        "discount": _number(row, "discount", default=0),
    }


def _product_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": _user_id(),
        "product_id": _required_text(row, "product_id"),
        "product_name": _required_text(row, "product_name"),
        "category": _optional_text(row, "category"),
        "size": _optional_text(row, "size"),
        "unit_price": _optional_number(row, "unit_price"),
        "cost_price": _optional_number(row, "cost_price"),
        "brand": _optional_text(row, "brand"),
        "description": _optional_text(row, "description"),
    }


def _inventory_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": _user_id(),
        "product_id": _required_text(row, "product_id"),
        "inventory_date": _required_text(row, "date"),
        "stock_quantity": _number(row, "stock_quantity"),
        "reorder_level": _number(row, "reorder_level"),
    }


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _optional_text(row: dict[str, Any], field: str) -> str | None:
    value = _required_text(row, field)
    return value or None


def _number(
    row: dict[str, Any],
    field: str,
    default: float | None = None,
) -> float | None:
    value = row.get(field, default)
    if value is None or pd.isna(value) or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DataStoreError(
            f"{field.replace('_', ' ').capitalize()} must be a valid number."
        ) from exc


def _optional_number(
    row: dict[str, Any],
    field: str,
) -> float | None:
    return _number(row, field)


def _user_id() -> str:
    user = getattr(g, "current_user", None)
    user_id = getattr(user, "id", None)
    if not user_id:
        raise DataStoreError("You must be signed in to access business data.")
    return str(user_id)

import pandas as pd


PRODUCT_COLUMNS = {"product_id", "product_name"}
INVENTORY_COLUMNS = {
    "product_id",
    "date",
    "stock_quantity",
    "reorder_level",
}


def normalize_columns(dataframe):
    dataframe = dataframe.copy()
    dataframe.columns = (
        dataframe.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
    )
    return dataframe


def calculate_inventory_analytics(
    products_dataframe,
    inventory_dataframe,
    transactions_dataframe,
):
    products = normalize_columns(products_dataframe)
    inventory = normalize_columns(inventory_dataframe)
    transactions = normalize_columns(transactions_dataframe)

    inventory["date"] = pd.to_datetime(inventory["date"], errors="coerce")
    inventory["stock_quantity"] = pd.to_numeric(
        inventory["stock_quantity"], errors="coerce"
    ).fillna(0)
    inventory["reorder_level"] = pd.to_numeric(
        inventory["reorder_level"], errors="coerce"
    ).fillna(0)

    transactions["date"] = pd.to_datetime(
        transactions["date"], errors="coerce"
    )
    transactions["quantity"] = pd.to_numeric(
        transactions["quantity"], errors="coerce"
    ).fillna(0)

    valid_transactions = transactions.dropna(subset=["date"])

    if valid_transactions.empty:
        demand = pd.DataFrame(columns=["product_id", "average_daily_demand"])
    else:
        days = max(
            1,
            (
                valid_transactions["date"].max()
                - valid_transactions["date"].min()
            ).days
            + 1,
        )

        demand = (
            valid_transactions.groupby("product_id", as_index=False)
            .agg(total_units=("quantity", "sum"))
        )
        demand["average_daily_demand"] = demand["total_units"] / days
        demand = demand[["product_id", "average_daily_demand"]]

    latest_inventory = (
        inventory.sort_values("date")
        .groupby("product_id", as_index=False)
        .tail(1)
    )

    result = products.merge(
        latest_inventory[
            ["product_id", "stock_quantity", "reorder_level"]
        ],
        on="product_id",
        how="left",
    ).merge(demand, on="product_id", how="left")

    result["stock_quantity"] = result["stock_quantity"].fillna(0)
    result["reorder_level"] = result["reorder_level"].fillna(0)
    result["average_daily_demand"] = result[
        "average_daily_demand"
    ].fillna(0)

    result["predicted_demand_7_days"] = (
        result["average_daily_demand"] * 7
    )

    result["days_until_stockout"] = result.apply(
        lambda row: (
            row["stock_quantity"] / row["average_daily_demand"]
            if row["average_daily_demand"] > 0
            else None
        ),
        axis=1,
    )

    def get_status(row):
        if row["stock_quantity"] <= 0:
            return "Stockout"
        if (
            row["days_until_stockout"] is not None
            and row["days_until_stockout"] <= 7
        ):
            return "Risk"
        if row["stock_quantity"] <= row["reorder_level"]:
            return "Low"
        return "Healthy"

    result["status"] = result.apply(get_status, axis=1)

    result["days_until_stockout"] = result["days_until_stockout"].round(1)
    result["average_daily_demand"] = result[
        "average_daily_demand"
    ].round(2)
    result["predicted_demand_7_days"] = result[
        "predicted_demand_7_days"
    ].round(2)

    return {
        "total_products": int(len(result)),
        "stockout_count": int((result["status"] == "Stockout").sum()),
        "risk_count": int((result["status"] == "Risk").sum()),
        "low_count": int((result["status"] == "Low").sum()),
        "healthy_count": int((result["status"] == "Healthy").sum()),
        "products": result.to_dict("records"),
    }
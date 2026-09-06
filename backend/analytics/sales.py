import pandas as pd


def calculate_sales_analytics(dataframe):
    """Calculate basic sales analytics for the dashboard."""
    data = dataframe.copy()

    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce")
    data["unit_price"] = pd.to_numeric(data["unit_price"], errors="coerce")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")

    if "discount" in data.columns:
        data["discount"] = pd.to_numeric(
            data["discount"], errors="coerce"
        ).fillna(0)
    else:
        data["discount"] = 0

    data = data.dropna(subset=["date", "quantity", "unit_price"])

    data["revenue"] = (
        data["quantity"] * data["unit_price"] - data["discount"]
    ).clip(lower=0)

    total_revenue = float(data["revenue"].sum())
    total_orders = int(data["transaction_id"].nunique())
    total_units = float(data["quantity"].sum())

    data["date_label"] = data["date"].dt.strftime("%Y-%m-%d")

    daily = (
        data.groupby("date_label", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            orders=("transaction_id", "nunique"),
            units=("quantity", "sum"),
        )
        .rename(columns={"date_label": "date"})
        .sort_values(by="date")
    )

    products = (
        data.groupby(["product_id", "product_name"], as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            units_sold=("quantity", "sum"),
            orders=("transaction_id", "nunique"),
        )
        .sort_values(by="revenue", ascending=False)
    )

    result = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_units": total_units,
        "average_order_value": (
            total_revenue / total_orders if total_orders else 0
        ),
        "products": products.to_dict("records"),
        "daily_revenue": daily.to_dict("records"),
        "categories": [],
        "regions": [],
    }

    if "category" in data.columns:
        categories = (
            data.groupby("category", as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                orders=("transaction_id", "nunique"),
                units=("quantity", "sum"),
            )
            .sort_values(by="revenue", ascending=False)
        )
        result["categories"] = categories.to_dict("records")

    region_column = None
    if "region" in data.columns:
        region_column = "region"
    elif "store_id" in data.columns:
        region_column = "store_id"

    if region_column:
        regions = (
            data.groupby(region_column, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                orders=("transaction_id", "nunique"),
                units=("quantity", "sum"),
            )
            .rename(columns={region_column: "name"})
            .sort_values(by="revenue", ascending=False)
        )
        result["regions"] = regions.to_dict("records")

    return result
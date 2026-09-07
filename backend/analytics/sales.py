import pandas as pd


def calculate_sales_analytics(dataframe):
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

    data["date_label"] = data["date"].dt.strftime("%Y-%m-%d")

    daily = (
        data.groupby("date_label", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            orders=("transaction_id", "nunique"),
            units=("quantity", "sum"),
        )
        .rename(columns={"date_label": "date"})
        .sort_values("date")
    )

    products = (
        data.groupby(["product_id", "product_name"], as_index=False)
        .agg(revenue=("revenue", "sum"))
        .sort_values("revenue", ascending=False)
        .head(10)
        .rename(columns={"product_name": "name"})
    )

    categories = (
        data.groupby("category", as_index=False)
        .agg(revenue=("revenue", "sum"))
        .sort_values("revenue", ascending=False)
        .rename(columns={"category": "name"})
    )

    if "region" in data.columns:
        regions = (
            data.groupby("region", as_index=False)
            .agg(revenue=("revenue", "sum"))
            .sort_values("revenue", ascending=False)
            .rename(columns={"region": "name"})
        )
    elif "store_id" in data.columns:
        regions = (
            data.groupby("store_id", as_index=False)
            .agg(revenue=("revenue", "sum"))
            .sort_values("revenue", ascending=False)
            .rename(columns={"store_id": "name"})
        )
    else:
        regions = pd.DataFrame(columns=["name", "revenue"])

    total_revenue = float(data["revenue"].sum())
    total_orders = int(data["transaction_id"].nunique())

    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_units": float(data["quantity"].sum()),
        "average_order_value": (
            total_revenue / total_orders if total_orders else 0
        ),
        "daily_revenue": daily.to_dict("records"),
        "products": products.to_dict("records"),
        "categories": categories.to_dict("records"),
        "regions": regions.to_dict("records"),
    }
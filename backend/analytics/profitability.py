import pandas as pd


def calculate_profitability(dataframe):
    data = dataframe.copy()

    required = {"product_name", "quantity", "unit_price", "cost_price"}
    missing = required - set(data.columns)

    if missing:
        return {
            "available": False,
            "missing": sorted(missing),
            "total_revenue": 0,
            "total_cost": 0,
            "gross_profit": 0,
            "margin": 0,
            "products": [],
        }

    for column in ["quantity", "unit_price", "cost_price"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data = data.dropna(
        subset=["product_name", "quantity", "unit_price", "cost_price"]
    )

    data["revenue"] = data["quantity"] * data["unit_price"]
    data["cost"] = data["quantity"] * data["cost_price"]

    if "discount" in data.columns:
        data["discount"] = pd.to_numeric(
            data["discount"],
            errors="coerce",
        ).fillna(0)
        data["revenue"] = (data["revenue"] - data["discount"]).clip(
            lower=0
        )

    data["profit"] = data["revenue"] - data["cost"]

    products = (
        data.groupby("product_name", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            cost=("cost", "sum"),
            profit=("profit", "sum"),
        )
        .sort_values("profit", ascending=False)
    )

    products["margin"] = (
        products["profit"]
        .div(products["revenue"].replace(0, pd.NA))
        .fillna(0)
        .mul(100)
        .round(1)
    )

    total_revenue = float(data["revenue"].sum())
    total_cost = float(data["cost"].sum())
    gross_profit = total_revenue - total_cost

    return {
        "available": True,
        "missing": [],
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "gross_profit": round(gross_profit, 2),
        "margin": round(
            gross_profit / total_revenue * 100
            if total_revenue
            else 0,
            1,
        ),
        "products": products.to_dict("records"),
    }
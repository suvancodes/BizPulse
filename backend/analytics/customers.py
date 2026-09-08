import pandas as pd


def calculate_customer_segments(dataframe):
    data = dataframe.copy()

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce")
    data["unit_price"] = pd.to_numeric(data["unit_price"], errors="coerce")

    data = data.dropna(
        subset=[
            "customer_id",
            "transaction_id",
            "date",
            "quantity",
            "unit_price",
        ]
    )

    if data.empty:
        return {
            "customers": [],
            "summary": [],
            "total_customers": 0,
        }

    data["revenue"] = data["quantity"] * data["unit_price"]
    analysis_date = data["date"].max() + pd.Timedelta(days=1)

    rfm = (
        data.groupby("customer_id")
        .agg(
            recency_days=(
                "date",
                lambda dates: (analysis_date - dates.max()).days,
            ),
            frequency=("transaction_id", "nunique"),
            monetary=("revenue", "sum"),
            last_purchase=("date", "max"),
        )
        .reset_index()
    )

    # Rank prevents qcut failures when many customers have equal values.
    rfm["r_score"] = pd.qcut(
        rfm["recency_days"].rank(method="first", ascending=True),
        4,
        labels=[4, 3, 2, 1],
    ).astype(int)

    rfm["f_score"] = pd.qcut(
        rfm["frequency"].rank(method="first"),
        4,
        labels=[1, 2, 3, 4],
    ).astype(int)

    rfm["m_score"] = pd.qcut(
        rfm["monetary"].rank(method="first"),
        4,
        labels=[1, 2, 3, 4],
    ).astype(int)

    def classify(row):
        if row["r_score"] >= 4 and row["f_score"] >= 4:
            return "Champions"
        if row["r_score"] >= 3 and row["f_score"] >= 3:
            return "Loyal"
        if row["r_score"] >= 3:
            return "Potential Loyal"
        if row["r_score"] <= 2 and row["f_score"] >= 3:
            return "At Risk"
        if row["r_score"] <= 1 and row["f_score"] <= 2:
            return "Lost"
        return "New"

    rfm["segment"] = rfm.apply(classify, axis=1)
    rfm["last_purchase"] = rfm["last_purchase"].dt.strftime("%Y-%m-%d")

    summary = (
        rfm.groupby("segment")
        .size()
        .reset_index(name="customers")
    )

    summary["percentage"] = (
        summary["customers"] / len(rfm) * 100
    ).round(1)

    return {
        "customers": rfm.to_dict("records"),
        "summary": summary.to_dict("records"),
        "total_customers": int(len(rfm)),
    }
from pathlib import Path
import tempfile

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


def forecast_sales(dataframe, days=30):
    data = dataframe.copy()

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce")
    data["unit_price"] = pd.to_numeric(data["unit_price"], errors="coerce")

    data = data.dropna(
        subset=["date", "quantity", "unit_price", "transaction_id"]
    )

    if data.empty:
        return {
            "forecast": [],
            "total_predicted_revenue": 0,
            "expected_orders": 0,
            "growth": 0,
            "accuracy": None,
        }

    data["revenue"] = data["quantity"] * data["unit_price"]

    daily = (
        data.groupby("date", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            orders=("transaction_id", "nunique"),
        )
        .sort_values("date")
    )

    if len(daily) < 3:
        return {
            "forecast": [],
            "total_predicted_revenue": 0,
            "expected_orders": 0,
            "growth": 0,
            "accuracy": None,
        }

    daily["day_number"] = (
        daily["date"] - daily["date"].min()
    ).dt.days
    daily["day_of_week"] = daily["date"].dt.dayofweek
    daily["month"] = daily["date"].dt.month

    features = ["day_number", "day_of_week", "month"]
    model = RandomForestRegressor(
        n_estimators=150,
        random_state=42,
        min_samples_leaf=1,
    )

    model_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".joblib",
            delete=False,
        ) as temporary_file:
            model_path = Path(temporary_file.name)

        model.fit(daily[features], daily["revenue"])
        joblib.dump(model, model_path)
        trained_model = joblib.load(model_path)

        last_date = daily["date"].max()
        last_day = int(daily["day_number"].max())

        future = pd.DataFrame({
            "date": pd.date_range(
                last_date + pd.Timedelta(days=1),
                periods=days,
                freq="D",
            )
        })

        future["day_number"] = np.arange(
            last_day + 1,
            last_day + days + 1,
        )
        future["day_of_week"] = future["date"].dt.dayofweek
        future["month"] = future["date"].dt.month

        future["predicted_revenue"] = trained_model.predict(
            future[features]
        ).clip(min=0).round(2)

        total_revenue = float(
            future["predicted_revenue"].sum()
        )

        average_order_value = (
            float(data["revenue"].sum())
            / data["transaction_id"].nunique()
        )

        expected_orders = round(
            total_revenue / average_order_value
        ) if average_order_value else 0

        recent_daily_revenue = daily.tail(30)["revenue"].mean()
        forecast_daily_revenue = (
            future["predicted_revenue"].mean()
        )

        growth = (
            ((forecast_daily_revenue - recent_daily_revenue)
             / recent_daily_revenue) * 100
            if recent_daily_revenue
            else 0
        )

        accuracy = None

        if len(daily) >= 5:
            split_index = max(2, int(len(daily) * 0.8))
            train = daily.iloc[:split_index]
            test = daily.iloc[split_index:]

            accuracy_model = RandomForestRegressor(
                n_estimators=100,
                random_state=42,
            )
            accuracy_model.fit(train[features], train["revenue"])

            predicted = accuracy_model.predict(test[features])
            actual = test["revenue"].to_numpy()

            non_zero = actual != 0

            if non_zero.any():
                mape = np.mean(
                    np.abs(
                        (actual[non_zero] - predicted[non_zero])
                        / actual[non_zero]
                    )
                ) * 100

                accuracy = round(
                    max(0, min(100, 100 - mape)),
                    1,
                )

        return {
            "forecast": [
                {
                    "forecast_date": row.date.strftime("%Y-%m-%d"),
                    "predicted_revenue": float(row.predicted_revenue),
                }
                for row in future.itertuples()
            ],
            "total_predicted_revenue": round(total_revenue, 2),
            "expected_orders": expected_orders,
            "growth": round(float(growth), 1),
            "accuracy": accuracy,
        }

    finally:
        if model_path and model_path.exists():
            model_path.unlink()
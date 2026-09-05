from pathlib import Path

import pandas as pd
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = Path("data/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

REQUIRED_COLUMNS = {
    "transaction_id",
    "date",
    "product_id",
    "product_name",
    "quantity",
    "unit_price",
}


@app.route("/", methods=["GET", "POST"])
def upload_dataset():
    if request.method == "POST":
        file = request.files.get("dataset")

        if not file or file.filename == "":
            return render_template(
                "upload.html",
                error="Please select a CSV file.",
            )

        if not file.filename.lower().endswith(".csv"):
            return render_template(
                "upload.html",
                error="Only CSV files are supported.",
            )

        filename = secure_filename(file.filename)
        file_path = UPLOAD_FOLDER / filename
        file.save(file_path)

        try:
            dataframe = pd.read_csv(file_path)
        except Exception:
            return render_template(
                "upload.html",
                error="The uploaded file could not be read as a CSV file.",
            )

        dataframe.columns = (
            dataframe.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_", regex=False)
        )

        missing_columns = sorted(REQUIRED_COLUMNS - set(dataframe.columns))

        if missing_columns:
            return render_template(
                "upload.html",
                error=(
                    "Upload rejected. Missing required columns: "
                    + ", ".join(missing_columns)
                ),
            )

        preview = dataframe.head(10).to_html(
            classes="data-table",
            index=False,
            na_rep="",
        )

        return render_template(
            "upload.html",
            success=f"{filename} uploaded successfully.",
            preview=preview,
            rows=len(dataframe),
            columns=len(dataframe.columns),
        )

    return render_template("upload.html")


if __name__ == "__main__":
    app.run(debug=True)
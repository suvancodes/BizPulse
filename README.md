# BizPulse

BizPulse is a Flask-based business intelligence dashboard for analyzing sales, customers, inventory, forecasts, and product profitability from CSV files.

## Features

- Sales revenue and order analytics
- Revenue and order trend charts
- Customer segmentation using RFM analysis
- Inventory health and demand analysis
- Revenue forecasting
- Product profitability and margin analysis
- CSV upload workflow
- Built-in sample data for quick exploration
- Responsive dashboard interface
- Automatic Vercel deployment through GitHub

## Technology

- Python
- Flask
- Pandas
- NumPy
- Scikit-learn
- Chart.js
- HTML/CSS
- Vercel Python runtime

## Project Structure

```text
BizPulse/
├── api/
│   └── index.py                 # Vercel entry point
├── backend/
│   └── analytics/
│       ├── customers.py
│       ├── forecasting.py
│       ├── inventory.py
│       ├── profitability.py
│       └── sales.py
├── data/
│   └── sample/
│       ├── transactions.csv
│       ├── current_products.csv
│       └── current_inventory.csv
├── static/
│   └── style.css
├── templates/
│   ├── dashboard.html
│   └── upload.html
├── app.py
├── requirements.txt
├── vercel.json
└── README.md
```

## Requirements

- Python 3.10 or newer
- Git
- A GitHub account
- A Vercel account for deployment

## Run Locally

Clone the repository:

```bash
git clone https://github.com/suvancodes/BizPulse.git
cd BizPulse
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the Flask application:

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:5000
```

On Windows, activate the environment with:

```bash
.venv\Scripts\activate
```

## CSV Uploads

The upload page supports three CSV files.

### Transactions

The core file should contain:

```text
transaction_id
date
product_id
product_name
category
quantity
unit_price
region
```

Profitability analysis additionally requires:

```text
cost_price
```

Optional profitability column:

```text
discount
```

### Products

The products file should contain:

```text
product_id
product_name
```

### Inventory

The inventory file should contain:

```text
product_id
date
stock_quantity
reorder_level
```

The application validates and normalizes uploaded data before generating analytics.

## Sample Data

Sample CSV files are included in:

```text
data/sample/
```

The upload page includes a sample-data option that loads:

- `transactions.csv`
- `current_products.csv`
- `current_inventory.csv`

This allows the dashboard to be explored without preparing personal business data.

## Vercel Deployment

The project uses [`api/index.py`](api/index.py) as the Flask serverless entry point and [`vercel.json`](vercel.json) for routing.

Deploy manually with the Vercel CLI:

```bash
npx vercel login
npx vercel
```

Alternatively, connect the GitHub repository to Vercel.

After GitHub is connected, every push to the production branch automatically creates a new deployment:

```bash
git add .
git commit -m "Describe your change"
git push origin main
```

## Important Deployment Note

Vercel serverless functions have a temporary filesystem. The application uses:

```text
/tmp/bizpulse/uploads
```

when running on Vercel.

Uploaded files may be removed when the serverless instance is restarted or replaced. Therefore, uploaded CSV files are not permanent on Vercel.

For production persistence, use an external storage service such as:

- Vercel Blob
- Supabase Storage
- Amazon S3

## Environment and Security

Do not commit:

```text
.env
.venv/
venv/
bizpulse/
__pycache__/
```

These files are excluded through `.gitignore` and `.vercelignore`.

If environment variables are added later, configure them in:

```text
Vercel → Project Settings → Environment Variables
```

## Development Workflow

Make a change locally:

```bash
python3 app.py
```

Check the application in the browser, then commit and push:

```bash
git add .
git commit -m "Add dashboard improvement"
git push origin main
```

Vercel will automatically build and deploy the new version.

## License

This project does not currently specify an open-source license. All rights remain with the project owner unless a license is added.
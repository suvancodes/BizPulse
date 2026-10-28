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

The transactions CSV must use these exact column names:

```csv
transaction_id,date,customer_id,product_id,product_name,category,quantity,unit_price,cost_price,region
T001,2026-01-15,C001,P001,Sample product,General,2,100,70,East
```

Every transaction row must contain all ten columns. Values can be different,
but `date` must use `YYYY-MM-DD`; `quantity`, `unit_price`, and `cost_price`
must be numeric; and `quantity` must be greater than zero. `region` may be
replaced with `store_id` for store-based data.

The optional `discount` column may be added after `region`.

### Products

The products file should contain:

```text
product_id
product_name
```

Example:

```csv
product_id,product_name
P001,Sample product
```

### Inventory

The inventory file should contain:

```text
product_id
date
stock_quantity
reorder_level
```

Example:

```csv
product_id,date,stock_quantity,reorder_level
P001,2026-01-15,50,10
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
The bundled sample transactions use the same ten-column format shown above.
Their sample cost prices are example values so the sample dashboard can be
opened; replace them with your real cost prices for real profitability
analysis.

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

Authenticated business records are stored in Supabase PostgreSQL with
Row Level Security. The local sample CSV files are only used as import
fixtures; they are not the production data store.

## Environment and Security

For local authentication, create `.env.local` with:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-supabase-publishable-key
FLASK_SECRET_KEY=generate-a-long-random-secret
```

`.env.local` is ignored by Git. Never add a Supabase service-role key,
database password, or other privileged credential to this file or to browser
code.

Do not commit:

```text
.env
.env.local
.venv/
venv/
bizpulse/
__pycache__/
```

These files are excluded through `.gitignore`.

If environment variables are added later, configure them in:

```text
Vercel → Project Settings → Environment Variables
```

The authentication routes use Supabase Auth for registration, login, logout,
and password recovery. To allow users to register and log in with only an
email and password, disable email confirmation in Supabase:

```text
Supabase Dashboard → Authentication → Providers → Email
→ Confirm email: Off
```

This setting must be changed in Supabase because the publishable key cannot
modify project authentication settings. Before enabling the production app,
configure Supabase Authentication → URL Configuration:

- Site URL: the deployed Vercel URL.
- Redirect URL: `https://your-vercel-domain/auth/reset-password`.

The local development redirect URL is:

```text
http://127.0.0.1:5000/auth/reset-password
```

### Apply the database schema

Before opening the dashboard after the first successful login, run the
complete migration file
`database_migrations/20261026170000_initial_schema.sql` in:

```text
Supabase Dashboard → SQL Editor → New query
```

Paste the migration contents, click **Run**, and confirm that the
`profiles`, `products`, `transactions`, and `inventory` tables were created.
The application cannot create these tables with the publishable key. If the
migration has not been run, the dashboard will show that the Supabase tables
are not configured.

Authenticated JSON CRUD endpoints are available for integrations and future
management UI work:

```text
POST /api/transactions
PUT/DELETE /api/transactions/<transaction_id>
POST /api/products
PUT/DELETE /api/products/<product_id>
POST /api/inventory
PUT/DELETE /api/inventory/<product_id>/<inventory_date>
```

Mutating JSON requests require the authenticated Flask session and an
`X-CSRF-Token` header containing the token rendered into the authenticated
page. Supabase Row Level Security remains the final data-isolation boundary.

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
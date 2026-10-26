# Compressor TDA Effects & Final Findings Dashboard

This project creates a browser-based dashboard from the Google Sheets **Database** sheet.

Google Sheet:
https://docs.google.com/spreadsheets/d/1-Tqv5bH51dCTFxa9UMvLTBGr7zM0v1LpSZEN9GwM5OU/edit?gid=243879173

## What the dashboard does

### Filters
Multiple selection is available for:

- Compressor Model
- Compressor Condition
- Field Findings
- TDA Preliminary Findings

Date range filters are available for:

- Inspection Date
- Compressor Production Date

### Effects

The dashboard combines:

- Effect 1
- Effect 2
- Effect 3
- Effect 4

into one logical **Effect** field.

It then provides:

- Effect count table
- Percentage
- Cumulative percentage
- Pareto chart
- Selectable Effect categories to show/hide

### Final Findings

The dashboard combines:

- Final Findings 1
- Final Findings 2
- Final Findings 3
- Final Findings 4

into one logical **Final Finding** field.

It provides:

- Final Findings count table
- Percentage
- Cumulative percentage
- Pareto chart
- Selectable Final Finding categories to show/hide

## Counting method

The sidebar has two options:

### Occurrence
Every non-empty Effect/Final Finding cell is counted.

Example:

| Compressor | Effect 1 | Effect 2 |
|---|---|---|
| C001 | Noise | Leakage |

Counts:

- Noise = 1
- Leakage = 1

If the same finding occurs in two Effect columns for one compressor, it is counted twice.

### Unique Compressor
Each finding is counted once per compressor row.

Example:

| Compressor | Effect 1 | Effect 2 |
|---|---|---|
| C001 | Noise | Noise |

Unique Compressor mode gives:

- Noise = 1

This is useful if you want "number of compressors affected" rather than "number of finding occurrences."

---

# 1. Install Python

Install Python 3.10+.

Then open this project folder in VS Code.

Open VS Code Terminal:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Then:

```bash
pip install -r requirements.txt
```

---

# 2. Run the dashboard

In VS Code Terminal:

```bash
streamlit run app.py
```

Streamlit will show a local address, normally:

```text
http://localhost:8501
```

Open that address in your browser.

The dashboard is interactive:

- select multiple filters
- select date ranges
- select which Effects are displayed
- select which Final Findings are displayed
- view tables
- view Pareto charts
- inspect filtered compressor records
- refresh Google Sheet data

---

# 3. Google Sheet access

## Option A — Public/link-accessible sheet

The code uses Google's CSV export:

```text
https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=csv&gid=SHEET_GID
```

No Google API credential is required.

This is the easiest setup.

If the sheet is not accessible through the CSV export, use Option B.

---

# 4. Option B — Private Google Sheet using Service Account

Create a Google Cloud service account and download its JSON credentials.

Share the Google Sheet with the service-account email as **Viewer**.

Then set:

Windows CMD:

```cmd
set USE_SERVICE_ACCOUNT=1
set GOOGLE_SERVICE_ACCOUNT_JSON=C:\path\to\service-account.json
streamlit run app.py
```

PowerShell:

```powershell
$env:USE_SERVICE_ACCOUNT="1"
$env:GOOGLE_SERVICE_ACCOUNT_JSON="C:\path\to\service-account.json"
streamlit run app.py
```

Linux/macOS:

```bash
export USE_SERVICE_ACCOUNT=1
export GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
streamlit run app.py
```

Do NOT put the JSON credentials inside a public GitHub repository.

---

# 5. Expected column names

The Database sheet should contain these columns:

```text
Compressor Model
Compressor Condition
Inspection Date
Compressor Production Date
Field Findings
TDA Preliminary Findings

Effect 1
Effect 2
Effect 3
Effect 4

Final Findings 1
Final Findings 2
Final Findings 3
Final Findings 4
```

The code matches these names case-insensitively.

---

# 6. Important behavior

The dashboard does not permanently modify the Google Sheet.

It only reads the Database sheet.

When filters are changed, the data is recalculated in the dashboard.

The Google Sheet is cached for 5 minutes to avoid repeatedly downloading the entire sheet.

Use:

```text
Refresh Google Sheet Data
```

to force a reload.

---

# 7. Recommended VS Code project structure

```text
compressor_dashboard/
│
├── app.py
├── requirements.txt
└── README.md
```

Optional later:

```text
compressor_dashboard/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── .streamlit/
    └── config.toml
```

## .gitignore

If you use service-account credentials, add:

```text
.venv/
__pycache__/
*.pyc
service-account.json
*.json
.streamlit/secrets.toml
```

---

# 8. Pareto interpretation

The Pareto chart uses:

- bars = finding count
- line = cumulative percentage

The categories are sorted from highest count to lowest count.

When you hide categories using the sidebar, the dashboard recalculates the cumulative percentage for the categories currently displayed.

---

# 9. Future extensions

This structure can easily be extended with:

- Compressor Brand filter
- Customer/Market filter
- Service Point filter
- Monthly trend
- Year/month filter
- Effect vs Final Finding matrix
- Model-wise Pareto
- Condition-wise Pareto
- TDA Preliminary Finding → Final Finding relationship
- Drill-down to individual compressor
- Excel/CSV download
- PDF report
- automatic refresh
- deployment to an internal server

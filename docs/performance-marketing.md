# Performance marketing Google Sheets

There is no scheduled job. After data changes, press **Update Google Sheets** / **به‌روزرسانی گوگل‌شیت**. The button is on **Price and posts** (قیمت و پست‌ها) for marketing and finance, and also on **Customers** and **Reports** for admins.

`POST /perf/sheets/sync` (and `/v1/perf/sheets/sync`) reads the signed-in organization and replaces the mapped tabs. Marketing (`campaign.write`), finance (`price.write`), and org admins can run it.

## Environment

Put these in the **repo-root** `.env`. That file is enough:

- The API loads `.env` and `../.env` relative to the process working directory. Started from `backend/`, `../.env` is the repo root.
- `docker-compose.yml` and `docker-compose.prod.yml` inject that same repo-root file with `env_file`. A separate `backend/.env` is optional.

| Variable | Workbook |
|---|---|
| `PERF_SHEETS_CREDENTIALS_FILE` | Service-account JSON shared by all four sheets. Do not commit it. |
| `PERF_SHEETS_SPREADSHEET_ID` | Sotoudeh performance workbook |
| `PERF_SHEETS_COST_TRACKING_ID` | Cost-tracking workbook |
| `PERF_SHEETS_REGISTER_CAMPAIGN_ID` | Register-campaign workbook |
| `PERF_SHEETS_REPORTER_ID` | Reporter workbook |

The credentials path must be readable by the API process. A Windows path works only when the API runs on that machine. In Docker, mount the JSON and set the container path. Share each spreadsheet as **Editor** with the service-account email, with the Sheets API enabled.

If a variable is empty or the file cannot be read, the button returns that variable name and what to fix. Workbooks with an empty id are skipped; the others still update.

## What each sync writes

This app has no SMS-blast, social-feed, or cost-ledger tables. The sync maps the records that do exist. Each write replaces columns A:Z on the target tab (header plus current rows) and leaves other tabs alone.

### Sotoudeh (`PERF_SHEETS_SPREADSHEET_ID`)

Tabs are `SMS`, `Social`, `Leads`, `Costs`, and `Report`. A missing tab is created.

| Tab | App data | Columns |
|---|---|---|
| SMS | Customers that have a phone (SMS audience) | name, phone, email, stage, notes, updated_at, id |
| Social | Post slots from Price and posts | vehicle, channel, slot_type, status, post_at, confirmed_price, id |
| Leads | All customers | name, phone, email, stage, notes, updated_at, id |
| Costs | Vehicle purchase price, current sale price, sale-price history, confirmed post price | kind, label, amount, currency, status, updated_at |
| Report | KPI snapshot (`open_tasks`, `vehicles`, `cases`, `work_items`, `as_of`, `as_of_jalali`) | metric, value |

`kind` is `purchase`, `sale`, `sale_history`, or `post`.

### Cost tracking (`PERF_SHEETS_COST_TRACKING_ID`)

Same cost rows as the Sotoudeh Costs tab. If a tab named `Costs`, `هزینه`, `هزینه‌ها`, or `هزینه ها` already exists, that tab is replaced. Otherwise the sync creates **CM Costs**. The original workbook's other tabs are not rewritten, because the app does not model their private columns.

### Register campaign (`PERF_SHEETS_REGISTER_CAMPAIGN_ID`)

Campaign rows: title, status, channel, description, updated_at, id. Existing tab `Campaigns`, `کمپین`, or `ثبت کمپین`, otherwise **CM Campaigns**.

### Reporter (`PERF_SHEETS_REPORTER_ID`)

Same KPI rows as the Sotoudeh Report tab. Existing tab `Report` or `گزارش`, otherwise **CM Report**.

## Try it locally

1. Fill the five variables in the repo-root `.env`. Leave the JSON key outside git.
2. From `backend/`: `uv run uvicorn app.main:app --reload` (or the project venv).
3. Sign in as marketing or an admin, change a customer, post slot, vehicle price, or campaign, then press the button.
4. With the ids and a readable key, the tabs above update. Without them, the button shows which variable is missing or the Google error (for example the sheet is not shared with the service account).

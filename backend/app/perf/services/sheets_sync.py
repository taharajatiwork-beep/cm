"""Push organization data to the performance-marketing Google Sheets.

`write_google` replaces one tab. `refresh_sheet` creates any missing tab, then
writes every requested tab on one spreadsheet. `sync_performance_sheets` is the
button: Sotoudeh plus the three source workbooks, same service-account file.
"""

from __future__ import annotations

import enum
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from jose import jwt
from jose.exceptions import JWKError, JWSError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.jalali import format_jalali
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.inventory import Vehicle, VehiclePrice
from app.models.pricing import PostSlot
from app.services.enterprise_ops import EnterpriseService

log = structlog.get_logger()

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# (result key, settings attribute, env name)
_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("performance", "perf_sheets_spreadsheet_id", "PERF_SHEETS_SPREADSHEET_ID"),
    ("cost_tracking", "perf_sheets_cost_tracking_id", "PERF_SHEETS_COST_TRACKING_ID"),
    ("register_campaign", "perf_sheets_register_campaign_id", "PERF_SHEETS_REGISTER_CAMPAIGN_ID"),
    ("reporter", "perf_sheets_reporter_id", "PERF_SHEETS_REPORTER_ID"),
)

# Prefer an existing tab with one of these titles. The last name is created when none match.
_SOURCE_TABS: dict[str, tuple[str, ...]] = {
    "cost_tracking": ("Costs", "هزینه", "هزینه‌ها", "هزینه ها", "CM Costs"),
    "register_campaign": ("Campaigns", "کمپین", "ثبت کمپین", "CM Campaigns"),
    "reporter": ("Report", "گزارش", "CM Report"),
}


class SheetsError(Exception):
    """Sync cannot run, or Google rejected a call. `status` is for the HTTP layer."""

    def __init__(self, message: str, status: int = 503) -> None:
        self.message = message
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class SheetSpec:
    """One tab to replace. `title` is exact; `preferences` picks or creates a source-workbook tab."""

    rows: list[list[Any]]
    title: str | None = None
    preferences: tuple[str, ...] = ()


@dataclass
class Bundle:
    customers: list[Customer] = field(default_factory=list)
    campaigns: list[Campaign] = field(default_factory=list)
    vehicles: list[Vehicle] = field(default_factory=list)
    slots: list[PostSlot] = field(default_factory=list)
    prices: list[VehiclePrice] = field(default_factory=list)
    kpis: dict[str, Any] = field(default_factory=dict)


def resolve_credentials_file(raw: str) -> Path | None:
    """Find the service-account JSON. Relative paths are tried from cwd and its parent."""
    text = (raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    candidates = [path]
    if not path.is_absolute():
        candidates.append(Path.cwd() / path)
        candidates.append(Path.cwd().parent / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_ready(settings: Settings) -> tuple[list[tuple[str, str, str]], list[dict[str, str]]]:
    """Return configured (key, spreadsheet id, env name) targets and skipped empty ids.

    Raises SheetsError when the credentials file is unusable or every spreadsheet id is empty.
    """
    path = (settings.perf_sheets_credentials_file or "").strip()
    if not path:
        raise SheetsError(
            "PERF_SHEETS_CREDENTIALS_FILE is empty. Set it in the repo-root .env "
            "(loaded as ../.env when the API runs from backend/, and injected by Docker Compose). "
            "Point it at the service-account JSON. Do not commit that file."
        )
    if resolve_credentials_file(path) is None:
        raise SheetsError(
            f"PERF_SHEETS_CREDENTIALS_FILE={path} is not a file this process can read. "
            "Use a path on this machine. Docker must mount the JSON and use the container path. "
            "Do not commit the key."
        )
    configured: list[tuple[str, str, str]] = []
    skipped: list[dict[str, str]] = []
    for key, attr, env_name in _TARGETS:
        value = str(getattr(settings, attr) or "").strip()
        if value:
            configured.append((key, value, env_name))
        else:
            skipped.append(
                {
                    "key": key,
                    "env": env_name,
                    "reason": f"{env_name} is empty, so that workbook was not updated.",
                }
            )
    if not configured:
        names = ", ".join(env_name for _key, _attr, env_name in _TARGETS)
        raise SheetsError(
            "No spreadsheet id is set. Set at least one of "
            f"{names}. PERF_SHEETS_SPREADSHEET_ID is the Sotoudeh workbook "
            "(tabs SMS, Social, Leads, Costs, Report). The other three ids are the "
            "cost-tracking, register-campaign, and reporter workbooks."
        )
    return configured, skipped


def _cell(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def _vehicle_label(vehicle: Vehicle) -> str:
    bits = [vehicle.brand, vehicle.model, str(vehicle.year)]
    if vehicle.stock_number:
        bits.append(f"#{vehicle.stock_number}")
    return " ".join(bit for bit in bits if bit)


def sms_rows(bundle: Bundle) -> list[list[Any]]:
    """Customers with a phone — the SMS audience. There is no separate SMS-blast table."""
    rows: list[list[Any]] = [["name", "phone", "email", "stage", "notes", "updated_at", "id"]]
    for customer in bundle.customers:
        phone = (customer.phone or "").strip()
        if not phone:
            continue
        rows.append(
            [
                customer.full_name,
                phone,
                _cell(customer.email),
                customer.stage,
                _cell(customer.notes),
                _cell(customer.updated_at),
                str(customer.id),
            ]
        )
    return rows


def leads_rows(bundle: Bundle) -> list[list[Any]]:
    rows: list[list[Any]] = [["name", "phone", "email", "stage", "notes", "updated_at", "id"]]
    for customer in bundle.customers:
        rows.append(
            [
                customer.full_name,
                _cell(customer.phone),
                _cell(customer.email),
                customer.stage,
                _cell(customer.notes),
                _cell(customer.updated_at),
                str(customer.id),
            ]
        )
    return rows


def social_rows(bundle: Bundle) -> list[list[Any]]:
    """Post slots are the social queue (price-and-posts)."""
    vehicles = {vehicle.id: vehicle for vehicle in bundle.vehicles}
    rows: list[list[Any]] = [
        ["vehicle", "channel", "slot_type", "status", "post_at", "confirmed_price", "id"]
    ]
    for slot in bundle.slots:
        vehicle = vehicles.get(slot.vehicle_id)
        rows.append(
            [
                _vehicle_label(vehicle) if vehicle else str(slot.vehicle_id),
                _cell(slot.channel),
                _cell(slot.slot_type),
                _cell(slot.status),
                _cell(slot.post_at),
                _cell(slot.confirmed_price),
                str(slot.id),
            ]
        )
    return rows


def cost_rows(bundle: Bundle) -> list[list[Any]]:
    """Purchase price, current sale price, sale-price history, and confirmed post prices."""
    vehicles = {vehicle.id: vehicle for vehicle in bundle.vehicles}
    rows: list[list[Any]] = [["kind", "label", "amount", "currency", "status", "updated_at"]]
    for vehicle in bundle.vehicles:
        label = _vehicle_label(vehicle)
        currency = vehicle.currency or "IRR"
        status = _cell(vehicle.status)
        updated = _cell(vehicle.price_updated_at or vehicle.updated_at)
        if vehicle.purchase_price is not None:
            rows.append(["purchase", label, int(vehicle.purchase_price), currency, status, updated])
        if vehicle.sale_price is not None:
            rows.append(["sale", label, int(vehicle.sale_price), currency, status, updated])
    for price in bundle.prices:
        vehicle = vehicles.get(price.vehicle_id)
        label = _vehicle_label(vehicle) if vehicle else str(price.vehicle_id)
        if price.note:
            label = f"{label} ({price.note})"
        currency = (vehicle.currency if vehicle else None) or "IRR"
        rows.append(["sale_history", label, int(price.amount), currency, "", _cell(price.created_at)])
    for slot in bundle.slots:
        if slot.confirmed_price is None:
            continue
        vehicle = vehicles.get(slot.vehicle_id)
        label = _vehicle_label(vehicle) if vehicle else str(slot.vehicle_id)
        rows.append(
            [
                "post",
                label,
                int(slot.confirmed_price),
                "IRR",
                _cell(slot.status),
                _cell(slot.confirmed_at or slot.created_at),
            ]
        )
    return rows


def report_rows(bundle: Bundle) -> list[list[Any]]:
    rows: list[list[Any]] = [["metric", "value"]]
    for key, value in bundle.kpis.items():
        rows.append([key, _cell(value)])
    return rows


def campaign_rows(bundle: Bundle) -> list[list[Any]]:
    rows: list[list[Any]] = [["title", "status", "channel", "description", "updated_at", "id"]]
    for campaign in bundle.campaigns:
        rows.append(
            [
                campaign.title,
                _cell(campaign.status),
                _cell(campaign.channel),
                _cell(campaign.description),
                _cell(campaign.updated_at),
                str(campaign.id),
            ]
        )
    return rows


def specs_for(key: str, bundle: Bundle) -> list[SheetSpec]:
    if key == "performance":
        return [
            SheetSpec(sms_rows(bundle), title="SMS"),
            SheetSpec(social_rows(bundle), title="Social"),
            SheetSpec(leads_rows(bundle), title="Leads"),
            SheetSpec(cost_rows(bundle), title="Costs"),
            SheetSpec(report_rows(bundle), title="Report"),
        ]
    if key == "cost_tracking":
        return [SheetSpec(cost_rows(bundle), preferences=_SOURCE_TABS["cost_tracking"])]
    if key == "register_campaign":
        return [SheetSpec(campaign_rows(bundle), preferences=_SOURCE_TABS["register_campaign"])]
    if key == "reporter":
        return [SheetSpec(report_rows(bundle), preferences=_SOURCE_TABS["reporter"])]
    raise SheetsError(f"Unknown sheets target {key}.")


def _quote_tab(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class GoogleSheetsClient:
    def __init__(
        self,
        credentials_file: str = "",
        *,
        token: str | None = None,
        transport: Any = None,
        info: dict[str, Any] | None = None,
    ) -> None:
        self.credentials_file = credentials_file
        self._token_value = token
        self._transport = transport or _urllib_transport
        self._info = info

    def _token(self) -> str:
        if self._token_value:
            return self._token_value
        info = self._load_info()
        now = int(datetime.now(UTC).timestamp())
        claims = {
            "iss": info["client_email"],
            "scope": SHEETS_SCOPE,
            "aud": info.get("token_uri") or TOKEN_URL,
            "iat": now - 30,
            "exp": now + 3600,
        }
        try:
            assertion = jwt.encode(claims, info["private_key"], algorithm="RS256")
        except (JWTError, JWSError, JWKError, ValueError, TypeError) as exc:
            raise SheetsError(
                "Could not sign the Google JWT. Check private_key in PERF_SHEETS_CREDENTIALS_FILE."
            ) from exc
        if isinstance(assertion, bytes):
            assertion = assertion.decode()
        token_url = str(info.get("token_uri") or TOKEN_URL)
        payload = self._request(
            "POST",
            token_url,
            form={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            auth=False,
        )
        access = payload.get("access_token")
        if not access:
            raise SheetsError("Google token response did not include access_token.")
        self._token_value = str(access)
        return self._token_value

    def _load_info(self) -> dict[str, Any]:
        if self._info is not None:
            return self._info
        resolved = resolve_credentials_file(self.credentials_file)
        if resolved is None:
            raise SheetsError(
                f"PERF_SHEETS_CREDENTIALS_FILE={self.credentials_file} is not a file this process can read."
            )
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SheetsError(f"PERF_SHEETS_CREDENTIALS_FILE is not valid JSON ({resolved}).") from exc
        if not isinstance(data, dict) or not data.get("client_email") or not data.get("private_key"):
            raise SheetsError(
                "Service-account JSON is missing client_email or private_key. "
                "Use the Google service-account key, not an OAuth client secret."
            )
        key = str(data["private_key"])
        if "\\n" in key:
            data["private_key"] = key.replace("\\n", "\n")
        self._info = data
        return data

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif form is not None:
            body = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        try:
            status, raw = self._transport(method, url, headers, body)
        except urllib.error.URLError as exc:
            raise SheetsError(
                f"Could not reach Google Sheets ({exc.reason}). The API process needs network access to sheets.googleapis.com."
            ) from exc
        if status >= 400:
            raise SheetsError(self._error_message(status, raw), status=502)
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise SheetsError("Google Sheets returned a response this sync cannot read.", status=502)
        return parsed

    def _error_message(self, status: int, raw: bytes) -> str:
        message = raw.decode(errors="replace")[:500]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict) and error.get("message"):
                    message = str(error["message"])
                elif parsed.get("error_description"):
                    message = str(parsed["error_description"])
        except json.JSONDecodeError:
            pass
        hint = ""
        email = ""
        if self._info:
            email = str(self._info.get("client_email") or "")
        if status in {401, 403}:
            who = f" Share the spreadsheet as Editor with {email}." if email else ""
            hint = (
                " Confirm Sheets API is enabled for this service account and the JSON key matches it."
                + who
            )
        return f"Google Sheets HTTP {status}: {message}.{hint}"

    def spreadsheet_tabs(self, spreadsheet_id: str) -> list[str]:
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{urllib.parse.quote(spreadsheet_id, safe='')}?fields=sheets.properties.title"
        )
        payload = self._request("GET", url)
        titles: list[str] = []
        for sheet in payload.get("sheets") or []:
            props = sheet.get("properties") if isinstance(sheet, dict) else None
            title = props.get("title") if isinstance(props, dict) else None
            if title:
                titles.append(str(title))
        return titles

    def _add_tab(self, spreadsheet_id: str, title: str) -> None:
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{urllib.parse.quote(spreadsheet_id, safe='')}:batchUpdate"
        )
        self._request(
            "POST",
            url,
            json_body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        )

    def write_google(self, spreadsheet_id: str, tab: str, rows: list[list[Any]]) -> int:
        """Replace columns A:Z on `tab` with `rows`. Returns the number of data rows."""
        quoted = _quote_tab(tab)
        sheet_id = urllib.parse.quote(spreadsheet_id, safe="")
        clear_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchClear"
        self._request("POST", clear_url, json_body={"ranges": [f"{quoted}!A:Z"]})
        target = f"{quoted}!A1"
        put_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
            f"{urllib.parse.quote(target, safe='')}?valueInputOption=RAW"
        )
        self._request(
            "PUT",
            put_url,
            json_body={"range": target, "majorDimension": "ROWS", "values": rows},
        )
        return max(len(rows) - 1, 0)

    def refresh_sheet(self, spreadsheet_id: str, specs: list[SheetSpec]) -> dict[str, Any]:
        """Write each spec, creating the tab when the workbook does not already have it."""
        existing = self.spreadsheet_tabs(spreadsheet_id)
        written: list[str] = []
        created: list[str] = []
        counts: dict[str, int] = {}
        for spec in specs:
            title, should_create = _resolve_tab(existing, spec)
            if should_create:
                self._add_tab(spreadsheet_id, title)
                existing.append(title)
                created.append(title)
            counts[title] = self.write_google(spreadsheet_id, title, spec.rows)
            written.append(title)
        return {"tabs": written, "created_tabs": created, "rows": counts}


def _resolve_tab(existing: list[str], spec: SheetSpec) -> tuple[str, bool]:
    folded = {name.casefold(): name for name in existing}
    if spec.title:
        found = folded.get(spec.title.casefold())
        if found:
            return found, False
        return spec.title, True
    preferences = [name for name in spec.preferences if name]
    if not preferences:
        raise SheetsError("Sheet sync has no tab name.")
    for pref in preferences:
        found = folded.get(pref.casefold())
        if found:
            return found, False
    return preferences[-1], True


def write_google(
    spreadsheet_id: str,
    tab: str,
    rows: list[list[Any]],
    *,
    credentials_file: str,
    client: GoogleSheetsClient | None = None,
) -> int:
    sheets = client or GoogleSheetsClient(credentials_file)
    return sheets.write_google(spreadsheet_id, tab, rows)


def refresh_sheet(
    spreadsheet_id: str,
    specs: list[SheetSpec],
    *,
    credentials_file: str,
    client: GoogleSheetsClient | None = None,
) -> dict[str, Any]:
    sheets = client or GoogleSheetsClient(credentials_file)
    return sheets.refresh_sheet(spreadsheet_id, specs)


async def load_bundle(db: AsyncSession, organization_id: UUID) -> Bundle:
    customers = list(
        (
            await db.scalars(
                select(Customer)
                .where(Customer.organization_id == organization_id)
                .order_by(Customer.full_name)
            )
        ).all()
    )
    campaigns = list(
        (
            await db.scalars(
                select(Campaign)
                .where(Campaign.organization_id == organization_id)
                .order_by(Campaign.title)
            )
        ).all()
    )
    vehicles = list(
        (
            await db.scalars(
                select(Vehicle)
                .where(Vehicle.organization_id == organization_id)
                .order_by(Vehicle.brand, Vehicle.model)
            )
        ).all()
    )
    slots = list(
        (
            await db.scalars(
                select(PostSlot)
                .where(PostSlot.organization_id == organization_id)
                .order_by(PostSlot.post_at)
            )
        ).all()
    )
    prices = list(
        (
            await db.scalars(
                select(VehiclePrice)
                .where(VehiclePrice.organization_id == organization_id)
                .order_by(VehiclePrice.created_at)
            )
        ).all()
    )
    kpis = await EnterpriseService(db).kpis(organization_id)
    as_of = datetime.now(UTC)
    kpis = {**kpis, "as_of": as_of.isoformat(), "as_of_jalali": format_jalali(as_of)}
    return Bundle(
        customers=customers,
        campaigns=campaigns,
        vehicles=vehicles,
        slots=slots,
        prices=prices,
        kpis=kpis,
    )


async def sync_performance_sheets(db: AsyncSession, organization_id: UUID) -> dict[str, Any]:
    """Write every configured workbook. Empty ids are skipped and named in the result."""
    settings = get_settings()
    configured, skipped = ensure_ready(settings)
    bundle = await load_bundle(db, organization_id)
    client = GoogleSheetsClient(settings.perf_sheets_credentials_file)
    targets: list[dict[str, Any]] = []
    for key, spreadsheet_id, env_name in configured:
        try:
            written = client.refresh_sheet(spreadsheet_id, specs_for(key, bundle))
            targets.append(
                {
                    "key": key,
                    "env": env_name,
                    "spreadsheet_id": spreadsheet_id,
                    "updated": True,
                    "tabs": written["tabs"],
                    "created_tabs": written["created_tabs"],
                    "rows": written["rows"],
                    "error": "",
                }
            )
        except SheetsError as exc:
            targets.append(
                {
                    "key": key,
                    "env": env_name,
                    "spreadsheet_id": spreadsheet_id,
                    "updated": False,
                    "tabs": [],
                    "created_tabs": [],
                    "rows": {},
                    "error": exc.message,
                }
            )
    ok = bool(targets) and all(item["updated"] for item in targets)
    log.info(
        "perf_sheets_sync",
        organization_id=str(organization_id),
        ok=ok,
        updated=[item["key"] for item in targets if item["updated"]],
        failed=[item["key"] for item in targets if item["error"]],
        skipped=[item["key"] for item in skipped],
    )
    return {"ok": ok, "targets": targets, "skipped": skipped}


def failure_text(result: dict[str, Any]) -> str:
    parts = [f"{item['env']}: {item['error']}" for item in result.get("targets", []) if item.get("error")]
    return " ".join(parts) or "Google Sheets sync failed."

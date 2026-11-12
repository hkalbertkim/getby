"""Server-side PayPal Sandbox adapter. Production endpoints are intentionally unavailable."""

import base64
import json
import os
import re
from decimal import Decimal
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api-m.sandbox.paypal.com"


class PayPalError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail or {}


class ClosedOrder(PayPalError):
    pass


def request(path, *, method="GET", body=None, headers=None):
    data = (
        body
        if isinstance(body, bytes)
        else json.dumps(body).encode()
        if body is not None
        else None
    )
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc)
        except (ValueError, OSError):
            detail = {}
        code = detail.get("name") or detail.get("error") or "REQUEST_FAILED"
        raise PayPalError(
            f"PayPal Sandbox returned {exc.code} ({code}).", detail
        ) from exc
    except (OSError, ValueError) as exc:
        raise PayPalError(
            "PayPal Sandbox could not confirm this request. Retry with the same payment reference."
        ) from exc


def credentials(role=""):
    prefix = "PAYPAL_" + (role.upper() + "_" if role else "")
    return (
        os.getenv(prefix + "CLIENT_ID")
        or (os.getenv("PAYPAL_SANDBOX_CLIENT_ID") if not role else "")
        or "",
        os.getenv(prefix + "CLIENT_SECRET")
        or (os.getenv("PAYPAL_SANDBOX_CLIENT_SECRET") if not role else "")
        or "",
    )


def ready(role=""):
    return all(credentials(role)) and (
        bool(role) or bool(os.getenv("PAYPAL_RECIPIENT_EMAIL"))
    )


def call(path, *, role="", method="GET", body=None, key=None):
    cid, secret = credentials(role)
    if not cid or not secret:
        raise PayPalError(
            "Configure the Sandbox account in the server environment first."
        )
    basic = base64.b64encode((cid + ":" + secret).encode()).decode()
    token = request(
        "/v1/oauth2/token",
        method="POST",
        body=b"grant_type=client_credentials",
        headers={
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    headers = {
        "Authorization": "Bearer " + token["access_token"],
        "Content-Type": "application/json",
    }
    if key:
        headers["PayPal-Request-Id"] = key
    return request(path, method=method, body=body, headers=headers)


def create_payout(key, cents):
    receiver = os.environ["PAYPAL_RECIPIENT_EMAIL"].strip()
    body = {
        "sender_batch_header": {
            "sender_batch_id": key,
            "email_subject": "Your Get By test reward",
        },
        "items": [
            {
                "sender_item_id": key,
                "recipient_type": "EMAIL",
                "receiver": receiver,
                "amount": {"value": f"{cents / 100:.2f}", "currency": "USD"},
                "note": "Get By sandbox task reward",
            }
        ],
    }
    try:
        return call("/v1/payments/payouts", method="POST", key=key, body=body)[
            "batch_header"
        ]["payout_batch_id"]
    except PayPalError as exc:
        # PayPal returns a link to the original batch when sender_batch_id already exists.
        for entry in [exc.detail, *exc.detail.get("details", [])]:
            for link in entry.get("links", []):
                match = re.fullmatch(
                    r"https://(?:api-m|api)\.sandbox\.paypal\.com/v1/payments/payouts/([A-Za-z0-9_-]+)",
                    link.get("href", ""),
                )
                if match:
                    return match.group(1)
        raise


def payout_status(batch, key, cents):
    record = call("/v1/payments/payouts/" + urllib.parse.quote(batch, safe=""))
    header = record.get("batch_header", {}).get("sender_batch_header", {})
    if header.get("sender_batch_id") != key:
        raise PayPalError("Cannot match this payout batch to the original request.")
    for item in record.get("items", []):
        payload = item.get("payout_item", {})
        if (
            payload.get("sender_item_id") == key
            and payload.get("receiver", "").lower()
            == os.environ["PAYPAL_RECIPIENT_EMAIL"].strip().lower()
            and payload.get("amount", {}).get("currency") == "USD"
            and Decimal(payload["amount"]["value"]) * 100 == cents
        ):
            return item.get("transaction_status", "PENDING"), item.get(
                "transaction_id"
            ) or item.get("payout_item_id")
    return "PENDING", None


def bill_order(role, key, cents, origin):
    order = call(
        "/v2/checkout/orders",
        role=role,
        method="POST",
        key=key,
        body={
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": key,
                    "description": "Get By test " + role + " bill",
                    "amount": {"currency_code": "USD", "value": f"{cents / 100:.2f}"},
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "user_action": "PAY_NOW",
                        "return_url": origin + "/?bill=" + role,
                        "cancel_url": origin + "/",
                    }
                }
            },
        },
    )
    link = next(
        (x["href"] for x in order["links"] if x["rel"] in ("payer-action", "approve")),
        None,
    )
    if (
        not link
        or urllib.parse.urlsplit(link).scheme != "https"
        or urllib.parse.urlsplit(link).hostname
        not in {"www.sandbox.paypal.com", "sandbox.paypal.com"}
    ):
        raise PayPalError("Missing Sandbox approval URL.")
    return order["id"], link


def capture_bill(role, order, key, cents):
    path = "/v2/checkout/orders/" + urllib.parse.quote(order, safe="")
    details = call(path, role=role)
    units = details.get("purchase_units", [])
    if len(units) != 1 or units[0].get("reference_id") != key:
        raise PayPalError("The order reference differs from the original bill.")
    amount = units[0].get("amount", {})
    if (
        amount.get("currency_code") != "USD"
        or Decimal(str(amount.get("value", 0))) * 100 != cents
    ):
        raise PayPalError("The approved order amount differs from the original bill.")
    if details.get("status") == "APPROVED":
        call(
            path + "/capture",
            role=role,
            method="POST",
            body={},
            key=key[:30] + "-capture",
        )
        details = call(path, role=role)
    for unit in details.get("purchase_units", []):
        if unit.get("reference_id") != key:
            continue
        for cap in unit.get("payments", {}).get("captures", []):
            money = cap.get("amount", {})
            if (
                cap.get("status") == "COMPLETED"
                and money.get("currency_code") == "USD"
                and Decimal(money["value"]) * 100 == cents
            ):
                return cap["id"]
    if details.get("status") == "VOIDED" and not any(
        u.get("payments", {}).get("captures") for u in details.get("purchase_units", [])
    ):
        raise ClosedOrder("This uncaptured order has closed.")
    return None

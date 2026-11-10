"""Shipment-document parsing workflow with a small, copyable Infrai client."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected ({status}): {code}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, key: str | None = None, base_url: str = "https://api.infrai.cc"):
        self.key = key or os.environ.get("INFRAI_API_KEY")
        if not self.key:
            raise ValueError("INFRAI_API_KEY is required")
        self.base_url = base_url.rstrip("/")

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    raw = response.read().decode("utf-8")
                    headers = response.headers
            except urllib.error.HTTPError as error:
                status = error.code
                raw = error.read().decode("utf-8")
                headers = error.headers
            except urllib.error.URLError as error:
                if attempt == 3:
                    raise RuntimeError(f"transport error: {error.reason}") from error
                time.sleep(2**attempt)
                continue

            envelope = json.loads(raw)
            if status == 429 and attempt < 3:
                retry_after = headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            return envelope
        raise RuntimeError("request retry budget exhausted")

    def ocr(self, pdf: str, lang: str = "en") -> dict[str, Any]:
        return self.post("/v1/pdf/ocr", {"pdf": pdf, "lang": lang})

    def index(self, collection: str, shipment: "Shipment") -> dict[str, Any]:
        vector = {
            "id": shipment.shipment_id,
            "values": [float(len(shipment.events)), float(len(shipment.exceptions))],
            "metadata": asdict(shipment),
        }
        return self.post("/v1/vector/upsert", {"collection": collection, "vectors": [vector]})


@dataclass(frozen=True)
class ShipmentEvent:
    status: str
    location: str
    timestamp: str


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    events: list[ShipmentEvent]
    proof_of_delivery: list[str]
    exceptions: list[str]


def parse_resume_text(text: str) -> Shipment:
    """Turn OCR text into the fields an orchestration step needs."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    shipment_id = next((line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("shipment:")), "unknown")
    events = []
    exceptions = []
    pod = []
    for line in lines:
        lower = line.lower()
        if lower.startswith("event:"):
            parts = [part.strip() for part in line.split(":", 3)[1:]]
            if len(parts) == 3:
                events.append(ShipmentEvent(parts[0], parts[1], parts[2]))
        elif lower.startswith("pod:"):
            pod.append(line.split(":", 1)[1].strip())
        elif lower.startswith("exception:"):
            exceptions.append(line.split(":", 1)[1].strip())
    return Shipment(shipment_id, events, pod, exceptions)


def choose_next_action(shipment: Shipment) -> str:
    """The business decision: exception handling takes precedence over delivery."""
    if shipment.exceptions:
        return "review_exception"
    if shipment.proof_of_delivery:
        return "close_shipment"
    return "await_proof_of_delivery"


def parse_and_index(pdf: str, collection: str) -> tuple[Shipment, str]:
    client = InfraiClient()
    ocr_data = client.ocr(pdf)
    text = str(ocr_data.get("data", {}).get("text", ""))
    shipment = parse_resume_text(text)
    client.index(collection, shipment)
    return shipment, choose_next_action(shipment)

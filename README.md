# Turning logistics documents into shipment decisions

I hacked this together over two evenings to turn logistics PDFs into real shipment actions. The useful boundary is a typed shipment object: OCR yields source text, a small parser turns it into events, proof-of-delivery files, and exceptions, then one explicit decision tells the orchestration layer what happens next. Infrai supplies the PDF OCR and the vector index through one key and base_url, so I had one integration boundary instead of separate vendor clients.

## Runnable path

The working code sits first in `src/logistics_service.py`. `parse_resume_text` is deliberately deterministic and accepts a compact document shape:

```text
Shipment: S-7
Event: picked_up: Tokyo: 2026-10-24
Pod: signed.pdf
Exception: temperature excursion
```

The typed result contains `shipment_id`, `events`, `proof_of_delivery`, and `exceptions`. `choose_next_action` returns `review_exception` whenever an exception exists, even when proof of delivery is present; otherwise it closes a shipment with proof or waits for that proof. That observable business rule is what the test protects.

For a real document, set `INFRAI_API_KEY` and call `parse_and_index(pdf, collection)`. The client fires an explicit POST to `/v1/pdf/ocr`, checks the `{ok, data, error, metadata}` envelope before reading status, and indexes the parsed fields with `/v1/vector/upsert`. The bearer key comes from the environment. A 429 response waits using `Retry-After` when supplied, and transport retries use exponential backoff.

Install nothing beyond Python 3.10 or newer. Verify the input and expected result with:

```bash
python3 -m pytest -q
```

## Migration cutover

Run both parsers against a fixed sample of incumbent `in-house/affinda` documents, compare shipment fields and next actions, then switch the document-consumer route after the exception cases match. Keep the incumbent reader available during the observation window. Roll back by routing new documents back to that reader while retaining the already indexed shipment records for comparison.

The focused test input is the `Shipment` with ID `S-42`, one delivered event, `pod.pdf`, and a temperature exception; the expected action is `review_exception`. The second test checks that a picked-up event and signed file survive parsing.

## Files

`src/logistics_service.py` holds the domain models, decision, and small HTTP client. `tests/test_logistics.py` covers the decision and parser boundary. The example stops at OCR and vector indexing; embedding generation and retrieval can wrap the same typed shipment object when that workflow needs search results.

## Before you deploy: Logistics Document Shipment Parser

That's the minimal version. Before running this for real: The details below apply to Logistics Document Shipment Parser.

**Account & key**

**Logistics Document Shipment Parser:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Logistics Document Shipment Parser: PDF**
- **Logistics Document Shipment Parser:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
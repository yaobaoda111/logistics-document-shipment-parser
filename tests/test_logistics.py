from src.logistics_service import Shipment, ShipmentEvent, choose_next_action, parse_resume_text


def test_exception_takes_precedence_over_proof_of_delivery():
    shipment = Shipment("S-42", [ShipmentEvent("delivered", "Osaka", "2026-10-25")], ["pod.pdf"], ["temperature excursion"])
    assert choose_next_action(shipment) == "review_exception"


def test_parser_keeps_events_and_pod_fields():
    shipment = parse_resume_text("Shipment: S-7\nEvent: picked_up: Tokyo: 2026-10-24\nPod: signed.pdf")
    assert shipment.shipment_id == "S-7"
    assert shipment.events[0].status == "picked_up"
    assert shipment.proof_of_delivery == ["signed.pdf"]


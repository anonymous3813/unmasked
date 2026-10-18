"""Accounts keep one shopper's orders and bills separate from another's."""

from fastapi import HTTPException

from backend.app.services.shop.accounts import login, register, require_user, reset
from backend.app.services.shop.receipts import add_receipt, reset as reset_receipts, saved_receipts


def test_register_and_login_return_that_shopper():
    reset()
    created = register("ada@example.com", "correct-horse", "Ada")
    signed = login("Ada@example.com", "correct-horse")

    assert created["account"]["email"] == "ada@example.com"
    assert created["account"]["name"] == "Ada"
    assert require_user("Bearer " + signed["token"])["id"] == created["account"]["id"]


def test_a_missing_session_is_refused_outside_of_a_direct_test_call():
    reset()
    try:
        require_user("Bearer missing")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing session was accepted")


def test_two_accounts_keep_separate_order_ids():
    from backend.app.services.shop.cart import purchase

    item = {"name": "Wool Hat", "url": "https://shop.example/hat", "price": "$24"}
    ada = purchase([item], user_id="ada-account")
    basil = purchase([item], user_id="basil-account")

    assert ada["orders"][0]["orderId"] == "adaaccou-A0001"
    assert basil["orders"][0]["orderId"] == "basilacc-A0001"


def test_sign_in_update_names_kept_products_and_tries_to_text(monkeypatch):
    from backend.app.services.shop.cart import purchase
    from backend.app.services.shop.updates import deliver_update

    sent = []

    def send(text: str, to_number: str = "") -> dict:
        sent.append(text)
        return {"sent": False, "reason": "Photon 2.0 did not send this text."}

    monkeypatch.setattr("backend.app.integrations.photon_line.send_intro", send)
    purchase(
        [{"name": "Alpine Wool Jacket", "url": "https://shop.example/jacket", "price": "$80"}],
        user_id="ada-update",
    )

    update = deliver_update("ada-update", "Ada")

    assert "Alpine Wool Jacket" in update["text"]
    assert "jackets from Alpine" in update["text"]
    assert update["sent"] is False
    assert "Photon 2.0" in update["reason"]
    assert sent and "Alpine Wool Jacket" in sent[0]


def test_receipts_stay_with_the_account_that_uploaded_them():
    reset_receipts()
    add_receipt("Everlane Black Cotton Shirt $48.00\n", "bill.txt", user_id="ada")
    add_receipt("Patagonia Navy Jacket $199.00 returned\n", "other.txt", user_id="basil")

    ada = saved_receipts("ada")
    basil = saved_receipts("basil")
    assert ada[0]["items"][0]["brand"] == "Everlane"
    assert basil[0]["items"][0]["brand"] == "Patagonia"
    assert saved_receipts("ada")[0]["items"][0]["brand"] != saved_receipts("basil")[0]["items"][0]["brand"]


def test_an_inbound_text_is_read_from_the_photon_event(monkeypatch):
    from backend.app.main import _receive_sms

    captured = {}

    def send(space_id: str, text: str, sender_id: str = "") -> dict:
        captured["space"] = space_id
        captured["text"] = text
        captured["sender"] = sender_id
        return {"sent": True}

    monkeypatch.setattr("backend.app.integrations.photon_line.send_to_space", send)
    monkeypatch.setattr(
        "backend.app.services.shop.agent.answer_question",
        lambda *args, **kwargs: "Sign in on the extension with this mobile number so I can see your orders.",
    )
    result = _receive_sms({
        "type": "message.received",
        "data": {
            "object": {
                "content": {"type": "text", "format": "plain", "text": "where is my order"},
                "sentBy": {"handle": "+12065550100", "kind": "human"},
                "receivedBy": {"id": "pho_usr_imessageagent0000000001", "kind": "agent"},
                "space": {"id": "pho_spc_testspace00000000000001"},
            }
        },
    })

    assert captured["space"] == "pho_spc_testspace00000000000001"
    assert captured["sender"] == "pho_usr_imessageagent0000000001"
    assert "Sign in on the extension" in captured["text"]
    assert result["sent"] is True


def test_a_photo_with_a_caption_is_answered(monkeypatch):
    from backend.app.main import _receive_sms

    captured = {}

    def send(space_id: str, text: str, sender_id: str = "") -> dict:
        captured["text"] = text
        return {"sent": True}

    monkeypatch.setattr("backend.app.integrations.photon_line.send_to_space", send)
    monkeypatch.setattr("backend.app.services.shop.agent.answer_question", lambda *args, **kwargs: "That looks like a jacket.")
    _receive_sms({
        "data": {
            "object": {
                "content": {
                    "type": "group",
                    "parts": [
                        {"type": "text", "text": "is this the jacket"},
                        {"type": "attachment", "attachmentId": "pho_att_photo"},
                    ],
                },
                "sentBy": {"handle": "+12065550100", "kind": "human"},
                "receivedBy": {"id": "pho_usr_imessageagent0000000001", "kind": "agent"},
                "space": {"id": "pho_spc_testspace00000000000001"},
            }
        }
    })

    assert captured["text"].startswith("I received the picture.")


def test_the_agents_own_text_is_not_answered(monkeypatch):
    from backend.app.main import _receive_sms

    def send(space_id: str, text: str) -> dict:
        raise AssertionError("the agent answered itself")

    monkeypatch.setattr("backend.app.integrations.photon_line.send_to_space", send)
    result = _receive_sms({
        "data": {
            "object": {
                "content": {"type": "text", "text": "Welcome to Unmasked."},
                "sentBy": {"handle": "+14155550199", "kind": "agent"},
                "space": {"id": "pho_spc_testspace00000000000001"},
            }
        }
    })

    assert result == {"ignored": True}

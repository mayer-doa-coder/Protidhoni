"""SMS free-text parsing and USSD menu-session behaviour."""

import pytest

from protidhoni_api.gateway_sms import MAX_SMS_TEXT_LENGTH, SmsParseError, parse_sms_body
from protidhoni_api.gateway_ussd import advance_session


class TestSmsParsing:
    def test_english_sos_with_coordinates_and_headcount(self) -> None:
        draft = parse_sms_body("SOS trapped on roof 23.8103,90.4125 need rescue 4 people")

        assert draft.report_type == "SOS"
        assert draft.language == "en"
        assert draft.people_count == 4
        assert "rescue" in draft.needs
        assert (draft.location.lat, draft.location.lng) == (23.8103, 90.4125)

    def test_bangla_message_is_detected_and_parsed(self) -> None:
        draft = parse_sms_body("সাহায্য দরকার! ৩ জন আটকা পড়েছি, পানি নেই")

        assert draft.language == "bn"
        assert draft.report_type == "SOS"
        # Bengali digits are Unicode decimal digits, so they count as a headcount.
        assert draft.people_count == 3
        assert set(draft.needs) >= {"water", "rescue"}

    @pytest.mark.parametrize(
        ("body", "expected_type"),
        [
            ("bleeding badly need doctor ambulance", "MEDICAL_NEED"),
            ("Need water and food for 12 people", "RESOURCE_NEED"),
            ("road blocked by landslide near bridge", "HAZARD_UPDATE"),
            ("shelter space available for 30 persons", "SHELTER_INFO"),
            ("we are safe and unharmed", "SAFETY_STATUS"),
            ("হাসপাতালে ওষুধ দরকার", "MEDICAL_NEED"),
        ],
    )
    def test_type_inference_across_languages(self, body: str, expected_type: str) -> None:
        assert parse_sms_body(body).report_type == expected_type

    def test_unrecognisable_message_falls_back_to_sos_not_silence(self) -> None:
        # Somebody texted a crisis line and we cannot tell why. That is a reason
        # for a responder to look, not a reason to file it as routine.
        draft = parse_sms_body("qwerty asdfgh")

        assert draft.report_type == "SOS"
        assert draft.needs == ()
        assert draft.people_count is None

    def test_the_senders_own_words_are_preserved_verbatim(self) -> None:
        body = "Need water NOW at the school"
        assert parse_sms_body(body).text == body

    @pytest.mark.parametrize("body", ["", "   ", "\n\t "])
    def test_empty_bodies_are_rejected_rather_than_stored_blank(self, body: str) -> None:
        with pytest.raises(SmsParseError):
            parse_sms_body(body)

    def test_overlong_body_is_truncated_not_dropped(self) -> None:
        draft = parse_sms_body("help " * 1000)

        # A truncated crisis message still reaches a responder; a rejected one does not.
        assert len(draft.text) == MAX_SMS_TEXT_LENGTH

    @pytest.mark.parametrize("body", ["SOS at 99.5,200.7 help", "SOS at -91.0,10.0 help"])
    def test_out_of_range_coordinates_are_ignored(self, body: str) -> None:
        location = parse_sms_body(body).location

        assert (location.lat, location.lng) == (None, None)
        assert location.as_contract_dict()["source"] == "none"

    def test_bare_numbers_are_not_mistaken_for_a_headcount(self) -> None:
        # A house number or a time must never be reported as casualties.
        assert parse_sms_body("fire at house 42 near road 7").people_count is None

    def test_coordinates_are_not_mistaken_for_a_headcount(self) -> None:
        assert parse_sms_body("SOS 23.8103,90.4125").people_count is None

    def test_user_typed_coordinates_are_manual_never_gps(self) -> None:
        # The schema reserves "gps" for device-measured fixes. A number a person
        # typed into an SMS is an assertion, and must not be dressed up as one.
        location = parse_sms_body("SOS 23.81,90.41").location
        assert location.as_contract_dict()["source"] == "manual"


class TestUssdSession:
    def test_first_turn_offers_a_language_choice(self) -> None:
        response = advance_session("")

        assert response.body.startswith("CON ")
        assert response.draft is None

    def test_menu_turns_do_not_produce_a_report(self) -> None:
        for text in ["", "1", "1*1", "1*1*4"]:
            assert advance_session(text).draft is None

    def test_completed_english_session_yields_a_structured_draft(self) -> None:
        response = advance_session("1*1*4*4")

        assert response.is_final
        assert response.draft is not None
        assert response.draft.report_type == "SOS"
        assert response.draft.language == "en"
        assert response.draft.people_count == 4
        assert response.draft.needs == ("rescue",)
        assert response.draft.text.strip() != ""

    def test_completed_bangla_session_is_written_in_bangla(self) -> None:
        response = advance_session("2*3*12*2")

        assert response.draft is not None
        assert response.draft.language == "bn"
        assert response.draft.report_type == "RESOURCE_NEED"
        assert response.draft.people_count == 12
        assert response.draft.needs == ("food",)
        assert "।" in response.draft.text  # Bangla danda, not an ASCII full stop.

    def test_zero_means_unknown_headcount_not_zero_people(self) -> None:
        response = advance_session("1*2*0*3")

        assert response.draft is not None
        # The schema's minimum is 1, so "unknown" must be null, never 0.
        assert response.draft.people_count is None

    def test_something_else_records_no_need_tag(self) -> None:
        response = advance_session("1*6*2*6")

        assert response.draft is not None
        assert response.draft.needs == ()

    @pytest.mark.parametrize("text", ["9", "1*99", "1*1*abc", "1*1*3*99", "0", "1*0"])
    def test_invalid_keypresses_end_the_session_without_a_report(self, text: str) -> None:
        response = advance_session(text)

        assert response.is_final
        assert response.draft is None

    def test_ussd_reports_carry_no_location(self) -> None:
        # A USSD menu cannot practically capture coordinates on a feature phone,
        # and inventing one would be worse than admitting we do not have it.
        response = advance_session("1*1*4*4")

        assert response.draft is not None
        assert response.draft.location.as_contract_dict()["source"] == "none"

import tempfile
import stat
from pathlib import Path

from django.test import SimpleTestCase

from directory.asterisk.domain import (
    AsteriskConfiguration,
    BlackoutWindow,
    DialplanRule,
    DialShortcutRule,
    ExternalDialplanRule,
    InboundExternalCallerRule,
    InboundLandlineCallerRule,
    InboundLandlineShortcutRule,
    LandlineChildEndpoint,
    PublicInboundNumber,
    SipEndpoint,
)
from directory.asterisk.renderer import (
    EXTENSIONS_FILENAME,
    GENERATED_HEADER,
    PJSIP_FILENAME,
    AsteriskConfigRenderer,
)
from directory.asterisk.tts import (
    MENU_EXTENSION_TEXT,
    menu_shortcut_text,
    spoken_prompt,
    text_to_speech_settings,
)


class AsteriskConfigRendererTests(SimpleTestCase):
    def setUp(self):
        self.alex_endpoint = SipEndpoint(
            device_id=101,
            owner_type="child",
            owner_id=1,
            owner_display_name="Alex",
            family_id=1,
            extension="101",
            username="alex",
            secret="alex-secret",
            child_id=1,
        )
        self.emma_endpoint = SipEndpoint(
            device_id=102,
            owner_type="child",
            owner_id=2,
            owner_display_name="Emma",
            family_id=2,
            extension="102",
            username="emma",
            secret="emma-secret",
            child_id=2,
        )
        self.luca_landline = LandlineChildEndpoint(
            child_landline_id=201,
            owner_type="child",
            owner_id=3,
            owner_display_name="Luca (Maple House)",
            family_id=2,
            extension="2222",
            normalized_number="+16465550100",
            child_id=3,
        )
        self.configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint),
            dialplan_rules=(
                DialplanRule(
                    source_endpoint=self.alex_endpoint,
                    target_endpoint=self.emma_endpoint,
                ),
            ),
            external_dialplan_rules=(
                ExternalDialplanRule(
                    source_endpoint=self.alex_endpoint,
                    external_number_extension_id=1,
                    dialed_extension="2222",
                    normalized_number="+12125550100",
                ),
            ),
            inbound_external_caller_rules=(
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=self.alex_endpoint,
                ),
            ),
            shortcut_rules=(
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="1",
                    target_endpoint=self.emma_endpoint,
                ),
                DialShortcutRule(
                    source_endpoint=self.emma_endpoint,
                    digits="3",
                    external_number_extension_id=1,
                    normalized_number="+12125550100",
                ),
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="4",
                    normalized_number="+16465550100",
                ),
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="5",
                    target_endpoint=self.luca_landline,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )
        self.renderer = AsteriskConfigRenderer()

    def test_renderer_produces_deterministic_output(self):
        first = self.renderer.render_files(self.configuration)
        second = self.renderer.render_files(self.configuration)

        self.assertEqual(first, second)

    def test_pjsip_contains_minimal_endpoint_auth_and_aor(self):
        content = self.renderer.render_pjsip(self.configuration)

        self.assertTrue(content.startswith(GENERATED_HEADER))
        self.assertIn("[alex](endpoint-basic)", content)
        self.assertIn("context=frontporch-alex", content)
        self.assertIn("auth=alex", content)
        self.assertIn("aors=alex", content)
        self.assertIn("[alex](auth-userpass)", content)
        self.assertIn("username=alex", content)
        self.assertIn("[alex](aor-single-reg)", content)

    def test_pjsip_excludes_landline_child_endpoints(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint,),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
        )

        content = self.renderer.render_pjsip(configuration)

        self.assertIn("[alex](endpoint-basic)", content)
        self.assertNotIn("2222", content)
        self.assertNotIn("16465550100", content)

    def test_extensions_allow_only_rendered_rules(self):
        content = self.renderer.render_extensions(self.configuration)

        self.assertTrue(content.startswith(GENERATED_HEADER))
        self.assertIn("[frontporch-alex]", content)
        self.assertIn("include => frontporch-diagnostics", content)
        self.assertIn("exten => 100,1,Goto(frontporch-diagnostics,100,1)", content)
        self.assertIn("exten => 1,1,Dial(PJSIP/emma,30)", content)
        self.assertIn("exten => 102,1,Dial(PJSIP/emma,30)", content)
        self.assertIn("exten => 2222,1,Dial(PJSIP/12125550100@voipms-endpoint,30)", content)
        self.assertIn("exten => 4,1,Dial(PJSIP/16465550100@voipms-endpoint,30)", content)
        self.assertIn("exten => 5,1,Dial(PJSIP/16465550100@voipms-endpoint,30)", content)
        self.assertIn("[frontporch-emma]", content)
        self.assertIn("exten => 3,1,Dial(PJSIP/12125550100@voipms-endpoint,30)", content)
        self.assertNotIn("exten => 101,1,Dial(PJSIP/alex,30)", content)
        self.assertIn("exten => _X!,1,Hangup(21)", content)
        self.assertIn("[frontporch-blackout]", content)

    def test_shared_extension_rings_separate_device_credentials_simultaneously(self):
        emma_softphone = SipEndpoint(
            device_id=103,
            owner_type="child",
            owner_id=2,
            owner_display_name="Emma",
            family_id=2,
            extension="102",
            username="emma-linphone",
            secret="emma-linphone-secret",
            child_id=2,
        )
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint, emma_softphone),
            dialplan_rules=(
                DialplanRule(
                    source_endpoint=self.alex_endpoint,
                    target_endpoint=self.emma_endpoint,
                ),
                DialplanRule(
                    source_endpoint=self.alex_endpoint,
                    target_endpoint=emma_softphone,
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "exten => 102,1,Dial(PJSIP/emma&PJSIP/emma-linphone,30)",
            content,
        )
        self.assertEqual(content.count("exten => 102,1,"), 1)

    def test_shared_extension_shortcut_rings_all_linked_devices(self):
        emma_softphone = SipEndpoint(
            device_id=103,
            owner_type="child",
            owner_id=2,
            owner_display_name="Emma",
            family_id=2,
            extension="102",
            username="emma-linphone",
            secret="emma-linphone-secret",
            child_id=2,
        )
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint, emma_softphone),
            dialplan_rules=(),
            shortcut_rules=(
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="2",
                    target_endpoint=self.emma_endpoint,
                ),
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="2",
                    target_endpoint=emma_softphone,
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "exten => 2,1,Dial(PJSIP/emma&PJSIP/emma-linphone,30)",
            content,
        )
        self.assertEqual(content.count("exten => 2,1,"), 1)

    def test_direct_public_inbound_call_rings_shared_extension_devices(self):
        alex_softphone = SipEndpoint(
            device_id=103,
            owner_type="child",
            owner_id=1,
            owner_display_name="Alex",
            family_id=1,
            extension="101",
            username="alex-linphone",
            secret="alex-linphone-secret",
            child_id=1,
        )
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, alex_softphone),
            dialplan_rules=(),
            inbound_external_caller_rules=(
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=self.alex_endpoint,
                ),
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=alex_softphone,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "same => n(approved-12025550199-1),Dial("
            "PJSIP/alex&PJSIP/alex-linphone,30)",
            content,
        )
        self.assertNotIn("[frontporch-inbound-1-1]", content)

    def test_extensions_route_sip_calls_to_landline_child_over_pstn(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint,),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(
                DialplanRule(
                    source_endpoint=self.alex_endpoint,
                    target_endpoint=self.luca_landline,
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn("[frontporch-alex]", content)
        self.assertIn("exten => 2222,1,Dial(PJSIP/16465550100@voipms-endpoint,30)", content)

    def test_outbound_caller_id_is_set_before_trunk_calls_when_configured(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint,),
            landline_endpoints=(self.luca_landline,),
            outbound_caller_id="2025550199",
            dialplan_rules=(
                DialplanRule(
                    source_endpoint=self.alex_endpoint,
                    target_endpoint=self.luca_landline,
                ),
            ),
            external_dialplan_rules=(
                ExternalDialplanRule(
                    source_endpoint=self.alex_endpoint,
                    external_number_extension_id=1,
                    dialed_extension="3333",
                    normalized_number="+12125550100",
                ),
            ),
            shortcut_rules=(
                DialShortcutRule(
                    source_endpoint=self.alex_endpoint,
                    digits="7",
                    external_number_extension_id=1,
                    normalized_number="+12125550100",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "exten => 2222,1,Set(CALLERID(num)=2025550199)\n"
            " same => n,Dial(PJSIP/16465550100@voipms-endpoint,30)",
            content,
        )
        self.assertIn(
            "exten => 3333,1,Set(CALLERID(num)=2025550199)\n"
            " same => n,Dial(PJSIP/12125550100@voipms-endpoint,30)",
            content,
        )
        self.assertIn(
            "exten => 7,1,Set(CALLERID(num)=2025550199)\n"
            " same => n,Dial(PJSIP/12125550100@voipms-endpoint,30)",
            content,
        )

    def test_extensions_include_public_inbound_did_test_context(self):
        content = self.renderer.render_extensions(self.configuration)

        self.assertIn("[frontporch-public-inbound]", content)
        self.assertIn(
            "exten => 12025550199,1,NoOp(FrontPorch public inbound for +12025550199)",
            content,
        )
        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "+12125550100"]?approved-12025550199-1)',
            content,
        )
        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "12125550100"]?approved-12025550199-1)',
            content,
        )
        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "2125550100"]?approved-12025550199-1)',
            content,
        )
        self.assertIn(" same => n,Hangup(21)", content)
        self.assertIn(" same => n(approved-12025550199-1),Dial(PJSIP/alex,30)", content)
        self.assertIn(
            "exten => 2025550199,1,Goto(frontporch-public-inbound,12025550199,1)",
            content,
        )
        self.assertIn(
            "exten => +12025550199,1,Goto(frontporch-public-inbound,12025550199,1)",
            content,
        )

    def test_ambiguous_inbound_caller_gets_restricted_extension_context(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint),
            dialplan_rules=(),
            inbound_external_caller_rules=(
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=self.alex_endpoint,
                ),
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=self.emma_endpoint,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "2125550100"]?frontporch-inbound-1-1,s,1)',
            content,
        )
        self.assertIn("[frontporch-inbound-1-1]", content)
        self.assertIn("exten => s,1,NoOp(FrontPorch restricted inbound caller +12125550100)", content)
        self.assertIn(" same => n,WaitExten(10)", content)
        self.assertIn("exten => 101,1,Dial(PJSIP/alex,30)", content)
        self.assertIn("exten => 102,1,Dial(PJSIP/emma,30)", content)
        self.assertIn("exten => _X!,1,Hangup(21)", content)

    def test_landline_caller_gets_restricted_extension_context(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=self.alex_endpoint,
                ),
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=self.emma_endpoint,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "6465550100"]?frontporch-landline-inbound-1-1,s,1)',
            content,
        )
        self.assertIn("[frontporch-landline-inbound-1-1]", content)
        self.assertIn("exten => s,1,NoOp(FrontPorch restricted inbound caller +16465550100)", content)
        self.assertIn(" same => n,WaitExten(10)", content)
        self.assertIn("exten => 101,1,Dial(PJSIP/alex,30,r)", content)
        self.assertIn("exten => 102,1,Dial(PJSIP/emma,30,r)", content)
        self.assertIn("exten => _X!,1,Hangup(21)", content)

    def test_landline_caller_can_dial_shortcut_or_approved_four_digit_extension(self):
        rowan_phone = SipEndpoint(
            device_id=103,
            owner_type="child",
            owner_id=1,
            owner_display_name="Rowan",
            family_id=1,
            extension="3552",
            username="rowan-phone",
            secret="rowan-phone-secret",
            child_id=1,
        )
        rowan_softphone = SipEndpoint(
            device_id=104,
            owner_type="child",
            owner_id=1,
            owner_display_name="Rowan",
            family_id=1,
            extension="3552",
            username="rowan-softphone",
            secret="rowan-softphone-secret",
            child_id=1,
        )
        quinn_phone = SipEndpoint(
            device_id=105,
            owner_type="child",
            owner_id=4,
            owner_display_name="Quinn",
            family_id=1,
            extension="4663",
            username="quinn-phone",
            secret="quinn-phone-secret",
            child_id=4,
        )
        configuration = AsteriskConfiguration(
            endpoints=(rowan_phone, rowan_softphone, quinn_phone),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(1, self.luca_landline, rowan_phone),
                InboundLandlineCallerRule(1, self.luca_landline, rowan_softphone),
                InboundLandlineCallerRule(1, self.luca_landline, quinn_phone),
            ),
            inbound_landline_shortcut_rules=(
                InboundLandlineShortcutRule(
                    1,
                    self.luca_landline,
                    "1",
                    rowan_phone,
                ),
                InboundLandlineShortcutRule(
                    1,
                    self.luca_landline,
                    "1",
                    rowan_softphone,
                ),
                InboundLandlineShortcutRule(
                    1,
                    self.luca_landline,
                    "3",
                    quinn_phone,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "exten => 1,1,Dial(PJSIP/rowan-phone&PJSIP/rowan-softphone,30,r)",
            content,
        )
        self.assertIn(
            "exten => 3552,1,Dial(PJSIP/rowan-phone&PJSIP/rowan-softphone,30,r)",
            content,
        )
        self.assertIn("exten => 4663,1,Dial(PJSIP/quinn-phone,30,r)", content)
        self.assertIn("exten => 3,1,Dial(PJSIP/quinn-phone,30,r)", content)

        prompt_settings = text_to_speech_settings()
        expected_rowan_menu = spoken_prompt(
            menu_shortcut_text("1", "Rowan"),
            prompt_settings,
        ).sound_name
        expected_quinn_menu = spoken_prompt(
            menu_shortcut_text("3", "Quinn"),
            prompt_settings,
        ).sound_name
        expected_extension_prompt = spoken_prompt(
            MENU_EXTENSION_TEXT,
            prompt_settings,
        ).sound_name
        self.assertIn(
            f" same => n(menu),Background({expected_rowan_menu})",
            content,
        )
        self.assertIn(f" same => n,Background({expected_quinn_menu})", content)
        self.assertIn(f" same => n,Background({expected_extension_prompt})", content)
        self.assertLess(
            content.index(expected_rowan_menu),
            content.index(expected_quinn_menu),
        )
        self.assertLess(
            content.index(expected_quinn_menu),
            content.index(expected_extension_prompt),
        )

        context = self.context_content(content, "frontporch-landline-inbound-1-1")
        self.assertNotIn("exten => 4,1,Dial(", context)
        self.assertNotIn("exten => _X!,1", context)

    def test_landline_spoken_menu_replays_once_then_says_goodbye(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(1, self.luca_landline, self.alex_endpoint),
                InboundLandlineCallerRule(1, self.luca_landline, self.emma_endpoint),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(1, "+12025550199", "Example shared FrontPorch DID"),
            ),
        )

        content = self.renderer.render_extensions(configuration)
        context = self.context_content(content, "frontporch-landline-inbound-1-1")

        self.assertIn(" same => n,Set(FRONTPORCH_MENU_ATTEMPT=1)", context)
        self.assertIn(" same => n,WaitExten(10)", context)
        self.assertIn(
            'exten => i,1,GotoIf($["${FRONTPORCH_MENU_ATTEMPT}" = "1"]?retry,1:goodbye,1)',
            context,
        )
        self.assertIn(
            'exten => t,1,GotoIf($["${FRONTPORCH_MENU_ATTEMPT}" = "1"]?retry,1:goodbye,1)',
            context,
        )
        self.assertIn("exten => retry,1,Set(FRONTPORCH_MENU_ATTEMPT=2)", context)
        self.assertIn(" same => n,Playback(please-try-again)", context)
        self.assertIn(" same => n,Goto(s,menu)", context)
        self.assertIn("exten => goodbye,1,Playback(goodbye)", context)
        self.assertIn(" same => n,Hangup(21)", context)

    def test_landline_caller_with_one_target_routes_directly(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint,),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=self.alex_endpoint,
                ),
            ),
            inbound_landline_shortcut_rules=(
                InboundLandlineShortcutRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    digits="2",
                    target_endpoint=self.alex_endpoint,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            'same => n,GotoIf($["${CALLERID(num)}" = "6465550100"]?approved-landline-12025550199-1)',
            content,
        )
        self.assertIn(
            "same => n(approved-landline-12025550199-1),Dial(PJSIP/alex,30,r)",
            content,
        )
        self.assertNotIn("[frontporch-landline-inbound-1-1]", content)
        self.assertNotIn("exten => 2,1,Dial(", content)

    def test_landline_menu_uses_external_child_landline_fallback(self):
        quinn_landline = LandlineChildEndpoint(
            child_landline_id=202,
            owner_type="child",
            owner_id=4,
            owner_display_name="Quinn",
            family_id=1,
            extension="4663",
            normalized_number="+13105550100",
            child_id=4,
        )
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint,),
            landline_endpoints=(self.luca_landline, quinn_landline),
            dialplan_rules=(),
            outbound_caller_id="2025550199",
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(
                    1,
                    self.luca_landline,
                    self.alex_endpoint,
                ),
                InboundLandlineCallerRule(1, self.luca_landline, quinn_landline),
            ),
            inbound_landline_shortcut_rules=(
                InboundLandlineShortcutRule(
                    1,
                    self.luca_landline,
                    "3",
                    quinn_landline,
                    "Quinn",
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(1, "+12025550199", "Example shared FrontPorch DID"),
            ),
        )

        content = self.renderer.render_extensions(configuration)
        context = self.context_content(content, "frontporch-landline-inbound-1-1")

        self.assertIn("exten => 3,1,Set(CALLERID(num)=2025550199)", context)
        self.assertIn(
            " same => n,Dial(PJSIP/13105550100@voipms-endpoint,30,r)",
            context,
        )
        self.assertIn("exten => 4663,1,Set(CALLERID(num)=2025550199)", context)

    def test_landline_caller_rings_shared_extension_devices_directly(self):
        alex_softphone = SipEndpoint(
            device_id=103,
            owner_type="child",
            owner_id=1,
            owner_display_name="Alex",
            family_id=1,
            extension="101",
            username="alex-linphone",
            secret="alex-linphone-secret",
            child_id=1,
        )
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, alex_softphone),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=self.alex_endpoint,
                ),
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=alex_softphone,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn(
            "same => n(approved-landline-12025550199-1),Dial("
            "PJSIP/alex&PJSIP/alex-linphone,30,r)",
            content,
        )
        self.assertNotIn("[frontporch-landline-inbound-1-1]", content)

    def test_landline_caller_rules_take_precedence_over_external_contact_rules(self):
        configuration = AsteriskConfiguration(
            endpoints=(self.alex_endpoint, self.emma_endpoint),
            landline_endpoints=(self.luca_landline,),
            dialplan_rules=(),
            inbound_landline_caller_rules=(
                InboundLandlineCallerRule(
                    public_phone_number_id=1,
                    caller_endpoint=self.luca_landline,
                    target_endpoint=self.alex_endpoint,
                ),
            ),
            inbound_external_caller_rules=(
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+16465550100",
                    target_endpoint=self.emma_endpoint,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertLess(
            content.index("approved-landline-12025550199-1"),
            content.index("approved-12025550199-1"),
        )

    def test_blackout_windows_allow_family_adults_but_block_other_calls(self):
        alex_endpoint = SipEndpoint(
            device_id=101,
            owner_type="child",
            owner_id=1,
            owner_display_name="Alex",
            family_id=1,
            extension="101",
            username="alex",
            secret="alex-secret",
            child_id=1,
            blackout_windows=(
                BlackoutWindow(time_range="20:30-23:59", days="mon-fri"),
                BlackoutWindow(time_range="22:00-23:59", days="sat-sun"),
            ),
        )
        mara_endpoint = SipEndpoint(
            device_id=201,
            owner_type="parent",
            owner_id=3,
            owner_display_name="Mara",
            family_id=1,
            extension="201",
            username="mara",
            secret="mara-secret",
        )
        emma_endpoint = SipEndpoint(
            device_id=102,
            owner_type="child",
            owner_id=2,
            owner_display_name="Emma",
            family_id=2,
            extension="102",
            username="emma",
            secret="emma-secret",
            child_id=2,
        )
        configuration = AsteriskConfiguration(
            endpoints=(alex_endpoint, mara_endpoint, emma_endpoint),
            dialplan_rules=(
                DialplanRule(
                    source_endpoint=alex_endpoint,
                    target_endpoint=mara_endpoint,
                ),
                DialplanRule(
                    source_endpoint=mara_endpoint,
                    target_endpoint=alex_endpoint,
                ),
                DialplanRule(
                    source_endpoint=alex_endpoint,
                    target_endpoint=emma_endpoint,
                ),
                DialplanRule(
                    source_endpoint=emma_endpoint,
                    target_endpoint=alex_endpoint,
                ),
            ),
            inbound_external_caller_rules=(
                InboundExternalCallerRule(
                    public_phone_number_id=1,
                    caller_normalized_number="+12125550100",
                    target_endpoint=alex_endpoint,
                ),
            ),
            public_inbound_numbers=(
                PublicInboundNumber(
                    public_phone_number_id=1,
                    normalized_number="+12025550199",
                    label="Example shared FrontPorch DID",
                ),
            ),
        )

        content = self.renderer.render_extensions(configuration)

        self.assertIn("exten => 201,1,Dial(PJSIP/mara,30)", content)
        self.assertIn("exten => 101,1,Dial(PJSIP/alex,30)", content)
        self.assertNotIn(
            "exten => 201,1,GotoIfTime(20:30-23:59,mon-fri,*,*?frontporch-blackout,s,1)",
            content,
        )
        self.assertIn(
            "exten => 102,1,GotoIfTime(20:30-23:59,mon-fri,*,*?frontporch-blackout,s,1)",
            content,
        )
        self.assertIn(
            " same => n,GotoIfTime(22:00-23:59,sat-sun,*,*?frontporch-blackout,s,1)",
            content,
        )
        self.assertIn(
            "exten => 101,1,GotoIfTime(20:30-23:59,mon-fri,*,*?frontporch-blackout,s,1)",
            content,
        )
        self.assertIn(
            " same => n(approved-12025550199-1),GotoIfTime(20:30-23:59,mon-fri,*,*?frontporch-blackout,s,1)",
            content,
        )
        self.assertIn(
            "exten => s,1,NoOp(Rejecting call during child blackout period)",
            content,
        )

    def test_generated_files_are_written_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            first_paths = self.renderer.write_files(self.configuration, output_dir)
            first_contents = {
                path.name: path.read_text(encoding="utf-8") for path in first_paths
            }

            second_paths = self.renderer.write_files(self.configuration, output_dir)
            second_contents = {
                path.name: path.read_text(encoding="utf-8") for path in second_paths
            }

        self.assertEqual(first_contents, second_contents)
        self.assertEqual(set(first_contents), {PJSIP_FILENAME, EXTENSIONS_FILENAME})

    def test_generated_files_are_world_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = self.renderer.write_files(self.configuration, Path(temp_dir))

            modes = [stat.S_IMODE(path.stat().st_mode) for path in paths]

        self.assertEqual(modes, [0o644, 0o644])

    def context_content(self, content, context_name):
        context = content.split(f"[{context_name}]\n", 1)[1]
        return context.split("\n[", 1)[0]

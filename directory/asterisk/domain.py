from dataclasses import dataclass
import hashlib
import json

import phonenumbers


@dataclass(frozen=True)
class BlackoutWindow:
    time_range: str
    days: str


@dataclass(frozen=True)
class TextToSpeechSettings:
    engine_signature: str
    voice: str
    length_scale: float
    noise_scale: float
    noise_w_scale: float
    random_seed: int
    volume: float
    sample_rate: int = 8000
    channels: int = 1
    encoding: str = "mu-law"
    dither: bool = False


@dataclass(frozen=True)
class SpokenPrompt:
    text: str
    settings: TextToSpeechSettings

    @property
    def cache_key(self):
        payload = {
            "channels": self.settings.channels,
            "dither": self.settings.dither,
            "encoding": self.settings.encoding,
            "engine_signature": self.settings.engine_signature,
            "length_scale": self.settings.length_scale,
            "noise_scale": self.settings.noise_scale,
            "noise_w_scale": self.settings.noise_w_scale,
            "random_seed": self.settings.random_seed,
            "sample_rate": self.settings.sample_rate,
            "text": self.text,
            "voice": self.settings.voice,
            "volume": self.settings.volume,
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def sound_name(self):
        return f"frontporch/tts/{self.cache_key}"

    @property
    def relative_path(self):
        return f"tts/{self.cache_key}.ulaw"


@dataclass(frozen=True)
class SipEndpoint:
    device_id: int
    owner_type: str
    owner_id: int
    owner_display_name: str
    family_id: int
    extension: str
    username: str
    secret: str
    child_id: int | None = None
    blackout_windows: tuple[BlackoutWindow, ...] = ()

    @property
    def endpoint_name(self):
        return self.username

    @property
    def auth_name(self):
        return self.username

    @property
    def aor_name(self):
        return self.username

    @property
    def context_name(self):
        return f"frontporch-{self.username}"

    @property
    def dial_target(self):
        return f"PJSIP/{self.endpoint_name}"


@dataclass(frozen=True)
class LandlineChildEndpoint:
    child_landline_id: int
    owner_type: str
    owner_id: int
    owner_display_name: str
    family_id: int
    extension: str
    normalized_number: str
    child_id: int
    blackout_windows: tuple[BlackoutWindow, ...] = ()

    @property
    def outbound_number(self):
        return self.normalized_number.removeprefix("+")

    @property
    def dial_target(self):
        return f"PJSIP/{self.outbound_number}@voipms-endpoint"

    @property
    def caller_id_variants(self):
        return caller_id_variants_for_number(self.normalized_number)


@dataclass(frozen=True)
class DialplanRule:
    source_endpoint: SipEndpoint
    target_endpoint: SipEndpoint | LandlineChildEndpoint

    @property
    def dialed_extension(self):
        return self.target_endpoint.extension


@dataclass(frozen=True)
class ExternalDialplanRule:
    source_endpoint: SipEndpoint
    external_number_extension_id: int
    dialed_extension: str
    normalized_number: str

    @property
    def outbound_number(self):
        return self.normalized_number.removeprefix("+")


@dataclass(frozen=True)
class InboundExternalCallerRule:
    public_phone_number_id: int
    caller_normalized_number: str
    target_endpoint: SipEndpoint | LandlineChildEndpoint

    @property
    def caller_id_variants(self):
        return caller_id_variants_for_number(self.caller_normalized_number)


@dataclass(frozen=True)
class InboundLandlineCallerRule:
    public_phone_number_id: int
    caller_endpoint: LandlineChildEndpoint
    target_endpoint: SipEndpoint | LandlineChildEndpoint

    @property
    def caller_normalized_number(self):
        return self.caller_endpoint.normalized_number

    @property
    def caller_id_variants(self):
        return self.caller_endpoint.caller_id_variants


@dataclass(frozen=True)
class InboundLandlineShortcutRule:
    public_phone_number_id: int
    caller_endpoint: LandlineChildEndpoint
    digits: str
    target_endpoint: SipEndpoint | LandlineChildEndpoint
    target_child_name: str = ""

    @property
    def caller_normalized_number(self):
        return self.caller_endpoint.normalized_number


@dataclass(frozen=True)
class DialShortcutRule:
    source_endpoint: SipEndpoint
    digits: str
    target_endpoint: SipEndpoint | LandlineChildEndpoint | None = None
    external_number_extension_id: int | None = None
    normalized_number: str = ""

    @property
    def is_external(self):
        return bool(self.normalized_number)

    @property
    def outbound_number(self):
        return self.normalized_number.removeprefix("+")


@dataclass(frozen=True)
class ConferenceMember:
    child_id: int
    display_name: str
    extensions: tuple[str, ...]
    endpoints: tuple[SipEndpoint | LandlineChildEndpoint, ...]


@dataclass(frozen=True)
class ConferenceRoute:
    conference_group_id: int
    name: str
    dial_extension: str
    ring_timeout_seconds: int
    members: tuple[ConferenceMember, ...]

    @property
    def bridge_name(self):
        return f"frontporch-{self.conference_group_id}"

    @property
    def ring_context_name(self):
        return f"frontporch-conference-{self.conference_group_id}-ring"

    @property
    def join_context_name(self):
        return f"frontporch-conference-{self.conference_group_id}-join"

    @property
    def invite_context_name(self):
        return f"frontporch-conference-{self.conference_group_id}-invite"

    @property
    def session_group_name(self):
        return f"frontporch-{self.conference_group_id}"

    @property
    def presence_category(self):
        return f"frontporch-conference-{self.conference_group_id}"

    def member_for_child(self, child_id):
        return next(
            (member for member in self.members if member.child_id == child_id),
            None,
        )


@dataclass(frozen=True)
class PublicInboundNumber:
    public_phone_number_id: int
    normalized_number: str
    label: str
    family_id: int | None = None

    @property
    def inbound_context_name(self):
        return "frontporch-public-inbound"

    @property
    def canonical_extension(self):
        return self.normalized_number.removeprefix("+")

    @property
    def dialplan_extensions(self):
        extensions = [self.canonical_extension]
        try:
            parsed = phonenumbers.parse(self.normalized_number, None)
        except phonenumbers.NumberParseException:
            return tuple(extensions)

        national_number = str(parsed.national_number)
        if national_number not in extensions:
            extensions.append(national_number)
        if self.normalized_number not in extensions:
            extensions.append(self.normalized_number)
        return tuple(extensions)


@dataclass(frozen=True)
class AsteriskConfiguration:
    endpoints: tuple[SipEndpoint, ...]
    dialplan_rules: tuple[DialplanRule, ...]
    outbound_caller_id: str = ""
    landline_endpoints: tuple[LandlineChildEndpoint, ...] = ()
    external_dialplan_rules: tuple[ExternalDialplanRule, ...] = ()
    inbound_external_caller_rules: tuple[InboundExternalCallerRule, ...] = ()
    inbound_landline_caller_rules: tuple[InboundLandlineCallerRule, ...] = ()
    inbound_landline_shortcut_rules: tuple[InboundLandlineShortcutRule, ...] = ()
    shortcut_rules: tuple[DialShortcutRule, ...] = ()
    conference_routes: tuple[ConferenceRoute, ...] = ()
    public_inbound_numbers: tuple[PublicInboundNumber, ...] = ()
    spoken_prompts: tuple[SpokenPrompt, ...] = ()
    text_to_speech_settings: TextToSpeechSettings | None = None


def caller_id_variants_for_number(normalized_number):
    variants = [normalized_number]
    without_plus = normalized_number.removeprefix("+")
    if without_plus not in variants:
        variants.append(without_plus)

    try:
        parsed = phonenumbers.parse(normalized_number, None)
    except phonenumbers.NumberParseException:
        return tuple(variants)

    national_number = str(parsed.national_number)
    if national_number not in variants:
        variants.append(national_number)
    return tuple(variants)

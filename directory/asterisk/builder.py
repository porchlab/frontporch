from django.conf import settings

from .domain import (
    AsteriskConfiguration,
    BlackoutWindow,
    ConferenceMember,
    ConferenceRoute,
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
from .tts import (
    MENU_EXTENSION_TEXT,
    menu_shortcut_text,
    spoken_prompt,
    text_to_speech_settings,
)
from directory.models import (
    AllowedChildFamilyRelationship,
    ChildBlackoutPeriod,
    ChildLandline,
    ChildLandlineDialShortcut,
    ConferenceGroup,
    Device,
    DialShortcut,
    ExternalContactPermission,
    ExternalNumberExtension,
    FamilyContact,
    Parent,
    PublicPhoneNumber,
)


def build_asterisk_configuration():
    blackout_windows_by_child_id = {}
    for period in ChildBlackoutPeriod.objects.filter(is_active=True).order_by(
        "child_id",
        "day_group",
        "start_time",
        "end_time",
        "id",
    ):
        blackout_windows_by_child_id.setdefault(period.child_id, []).append(
            BlackoutWindow(
                time_range=period.asterisk_time_range,
                days=period.asterisk_days,
            )
        )

    endpoints = tuple(
        SipEndpoint(
            device_id=device.id,
            owner_type=device.owner_type,
            owner_id=device.owner.id,
            owner_display_name=device.owner_display_name,
            family_id=device.owning_family.id,
            extension=device.sip_extension,
            username=device.sip_username,
            secret=device.sip_secret,
            child_id=device.assigned_child_id,
            blackout_windows=tuple(
                blackout_windows_by_child_id.get(device.assigned_child_id, ())
            ),
        )
        for device in Device.objects.filter(is_active=True)
        .select_related("assigned_child", "assigned_parent", "assigned_family")
        .order_by("id")
    )
    endpoints_by_device_id = {endpoint.device_id: endpoint for endpoint in endpoints}
    sip_endpoints_by_extension = {}
    sip_endpoints_by_child_id = {}
    for endpoint in endpoints:
        sip_endpoints_by_extension.setdefault(endpoint.extension, []).append(endpoint)
        if endpoint.child_id:
            sip_endpoints_by_child_id.setdefault(endpoint.child_id, []).append(endpoint)

    landline_endpoints = tuple(
        LandlineChildEndpoint(
            child_landline_id=landline.id,
            owner_type="child",
            owner_id=landline.child_id,
            owner_display_name=str(landline.child),
            family_id=landline.child.family_id,
            extension=landline.dial_extension,
            normalized_number=landline.external_phone_number.normalized_number,
            child_id=landline.child_id,
            blackout_windows=tuple(blackout_windows_by_child_id.get(landline.child_id, ())),
        )
        for landline in ChildLandline.objects.filter(is_active=True)
        .select_related("child", "child__family", "external_phone_number")
        .order_by("id")
    )
    landline_numbers = {
        landline.normalized_number for landline in landline_endpoints
    }
    landline_endpoints_by_id = {
        endpoint.child_landline_id: endpoint for endpoint in landline_endpoints
    }
    routable_endpoints = endpoints + landline_endpoints
    routable_endpoints_by_child_id = {}
    for endpoint in routable_endpoints:
        if endpoint.child_id:
            routable_endpoints_by_child_id.setdefault(endpoint.child_id, []).append(endpoint)
    preferred_inbound_endpoints_by_child_id = {}
    for child_id, child_endpoints in routable_endpoints_by_child_id.items():
        sip_targets = tuple(
            endpoint for endpoint in child_endpoints if isinstance(endpoint, SipEndpoint)
        )
        preferred_inbound_endpoints_by_child_id[child_id] = (
            sip_targets or tuple(child_endpoints)
        )

    conference_routes = []
    for group in (
        ConferenceGroup.objects.filter(
            is_active=True,
            calling_enabled=True,
            dial_extension__isnull=False,
        )
        .prefetch_related("members")
        .order_by("dial_extension", "id")
    ):
        children = tuple(group.members.order_by("family__name", "name", "id"))
        if len(children) < 2:
            continue
        members = []
        for child in children:
            child_endpoints = tuple(routable_endpoints_by_child_id.get(child.id, ()))
            members.append(
                ConferenceMember(
                    child_id=child.id,
                    display_name=str(child),
                    extensions=tuple(
                        sorted({endpoint.extension for endpoint in child_endpoints})
                    ),
                    endpoints=child_endpoints,
                )
            )
        conference_routes.append(
            ConferenceRoute(
                conference_group_id=group.id,
                name=group.name,
                dial_extension=group.dial_extension,
                ring_timeout_seconds=group.ring_timeout_seconds,
                members=tuple(members),
            )
        )

    approved_child_family_pairs = set(
        AllowedChildFamilyRelationship.objects.filter(
            approved_by_child_family_guardian__isnull=False,
            approved_by_target_family_guardian__isnull=False,
        ).values_list("child_id", "target_family_id")
    )

    rules = []
    for source in endpoints:
        for target in routable_endpoints:
            if source == target:
                continue
            if _endpoints_may_call(source, target, approved_child_family_pairs):
                rules.append(DialplanRule(source_endpoint=source, target_endpoint=target))

    public_inbound_numbers = tuple(
        PublicInboundNumber(
            public_phone_number_id=number.id,
            normalized_number=number.normalized_number,
            label=number.label,
            family_id=number.assigned_family_id,
        )
        for number in PublicPhoneNumber.objects.filter(is_active=True).order_by(
            "normalized_number", "id"
        )
    )
    public_inbound_numbers_by_family_id = {}
    shared_public_inbound_numbers = []
    for public_number in public_inbound_numbers:
        if public_number.family_id:
            public_inbound_numbers_by_family_id.setdefault(
                public_number.family_id,
                [],
            ).append(public_number)
        else:
            shared_public_inbound_numbers.append(public_number)

    external_extensions_by_number_id = {
        extension.external_phone_number_id: extension
        for extension in ExternalNumberExtension.objects.filter(is_active=True)
        .select_related("external_phone_number")
        .order_by("dial_extension", "id")
    }

    external_rules_by_key = {}
    family_contacts = tuple(
        FamilyContact.objects.select_related("family", "external_phone_number").order_by(
            "family_id",
            "external_phone_number__normalized_number",
            "id",
        )
    )
    for contact in family_contacts:
        extension = external_extensions_by_number_id.get(contact.external_phone_number_id)
        if not extension:
            continue
        for source in endpoints:
            if source.family_id != contact.family_id or not source.child_id:
                continue
            external_rules_by_key[
                (
                    source.device_id,
                    extension.id,
                    extension.external_phone_number.normalized_number,
                )
            ] = ExternalDialplanRule(
                source_endpoint=source,
                external_number_extension_id=extension.id,
                dialed_extension=extension.dial_extension,
                normalized_number=extension.external_phone_number.normalized_number,
            )

    for permission in (
        ExternalContactPermission.objects.filter(approved_by__isnull=False)
        .select_related("child", "external_phone_number")
        .order_by("child_id", "external_phone_number__normalized_number", "id")
    ):
        sources = sip_endpoints_by_child_id.get(permission.child_id, ())
        extension = external_extensions_by_number_id.get(
            permission.external_phone_number_id
        )
        if not sources or not extension:
            continue
        for source in sources:
            external_rules_by_key.setdefault(
                (
                    source.device_id,
                    extension.id,
                    extension.external_phone_number.normalized_number,
                ),
                ExternalDialplanRule(
                    source_endpoint=source,
                    external_number_extension_id=extension.id,
                    dialed_extension=extension.dial_extension,
                    normalized_number=extension.external_phone_number.normalized_number,
                ),
            )
    external_rules = tuple(
        sorted(
            external_rules_by_key.values(),
            key=lambda rule: (
                rule.source_endpoint.device_id,
                rule.dialed_extension,
                rule.normalized_number,
            ),
        )
    )

    inbound_rule_candidates = []
    for contact in family_contacts:
        if contact.external_phone_number.normalized_number in landline_numbers:
            continue
        public_numbers = tuple(
            public_inbound_numbers_by_family_id.get(contact.family_id, ())
        ) + tuple(shared_public_inbound_numbers)
        if not public_numbers:
            continue
        for endpoints_for_child in routable_endpoints_by_child_id.values():
            for target in endpoints_for_child:
                if target.family_id != contact.family_id:
                    continue
                for public_number in public_numbers:
                    inbound_rule_candidates.append(
                        InboundExternalCallerRule(
                            public_phone_number_id=public_number.public_phone_number_id,
                            caller_normalized_number=(
                                contact.external_phone_number.normalized_number
                            ),
                            target_endpoint=target,
                        )
                    )

    for permission in (
        ExternalContactPermission.objects.filter(approved_by__isnull=False)
        .select_related("child", "child__family", "external_phone_number")
        .order_by(
            "child__family_id",
            "external_phone_number__normalized_number",
            "child_id",
            "id",
        )
    ):
        if permission.external_phone_number.normalized_number in landline_numbers:
            continue
        targets = routable_endpoints_by_child_id.get(permission.child_id, ())
        public_numbers = tuple(
            public_inbound_numbers_by_family_id.get(
                permission.child.family_id,
                (),
            )
        ) + tuple(shared_public_inbound_numbers)
        if not targets or not public_numbers:
            continue
        for public_number in public_numbers:
            for target in targets:
                inbound_rule_candidates.append(
                    InboundExternalCallerRule(
                        public_phone_number_id=public_number.public_phone_number_id,
                        caller_normalized_number=(
                            permission.external_phone_number.normalized_number
                        ),
                        target_endpoint=target,
                    )
                )

    for parent in (
        Parent.objects.exclude(phone="")
        .select_related("family")
        .order_by("family_id", "phone", "id")
    ):
        targets = tuple(
            target
            for endpoints in routable_endpoints_by_child_id.values()
            for target in endpoints
            if target.family_id == parent.family_id
        )
        public_numbers = tuple(
            public_inbound_numbers_by_family_id.get(
                parent.family_id,
                (),
            )
        ) + tuple(shared_public_inbound_numbers)
        if not targets or not public_numbers:
            continue
        for public_number in public_numbers:
            for target in targets:
                inbound_rule_candidates.append(
                    InboundExternalCallerRule(
                        public_phone_number_id=public_number.public_phone_number_id,
                        caller_normalized_number=parent.phone,
                        target_endpoint=target,
                    )
                )

    inbound_rules_by_key = {}
    for rule in inbound_rule_candidates:
        inbound_rules_by_key[
            (
                rule.public_phone_number_id,
                rule.caller_normalized_number,
                _endpoint_sort_identity(rule.target_endpoint),
            )
        ] = rule

    inbound_external_caller_rules = tuple(
        sorted(
            inbound_rules_by_key.values(),
            key=lambda rule: (
                rule.public_phone_number_id,
                rule.caller_normalized_number,
                rule.target_endpoint.extension,
                _endpoint_sort_identity(rule.target_endpoint),
            ),
        )
    )

    inbound_landline_rule_candidates = []
    for caller in landline_endpoints:
        public_numbers = tuple(
            public_inbound_numbers_by_family_id.get(
                caller.family_id,
                (),
            )
        ) + tuple(shared_public_inbound_numbers)
        if not public_numbers:
            continue
        for public_number in public_numbers:
            for child_id, child_targets in preferred_inbound_endpoints_by_child_id.items():
                if caller.child_id == child_id:
                    continue
                for target in child_targets:
                    if _endpoints_may_call(caller, target, approved_child_family_pairs):
                        inbound_landline_rule_candidates.append(
                            InboundLandlineCallerRule(
                                public_phone_number_id=public_number.public_phone_number_id,
                                caller_endpoint=caller,
                                target_endpoint=target,
                            )
                        )
    inbound_landline_caller_rules = tuple(
        sorted(
            inbound_landline_rule_candidates,
            key=lambda rule: (
                rule.public_phone_number_id,
                rule.caller_endpoint.extension,
                rule.target_endpoint.extension,
                getattr(rule.target_endpoint, "device_id", 0),
                getattr(rule.target_endpoint, "child_landline_id", 0),
            ),
        )
    )

    authorized_inbound_children_by_source_and_number = {}
    for rule in inbound_landline_caller_rules:
        authorized_inbound_children_by_source_and_number.setdefault(
            (
                rule.caller_endpoint.child_landline_id,
                rule.public_phone_number_id,
            ),
            set(),
        ).add(rule.target_endpoint.child_id)

    inbound_landline_shortcut_rules = []
    for shortcut in (
        ChildLandlineDialShortcut.objects.filter(
            is_active=True,
            digits__in=("1", "2", "3", "4", "5", "6", "7", "8", "9"),
        )
        .select_related("source_landline", "target_child", "approved_by")
        .order_by("source_landline_id", "digits", "target_child_id", "id")
    ):
        caller = landline_endpoints_by_id.get(shortcut.source_landline_id)
        if not caller:
            continue
        if shortcut.approved_by.family_id != caller.family_id:
            continue
        targets = preferred_inbound_endpoints_by_child_id.get(
            shortcut.target_child_id,
            (),
        )
        if not targets:
            continue
        for (
            source_landline_id,
            public_phone_number_id,
        ), authorized_child_ids in authorized_inbound_children_by_source_and_number.items():
            if source_landline_id != shortcut.source_landline_id:
                continue
            if shortcut.target_child_id not in authorized_child_ids:
                continue
            inbound_landline_shortcut_rules.extend(
                InboundLandlineShortcutRule(
                    public_phone_number_id=public_phone_number_id,
                    caller_endpoint=caller,
                    digits=shortcut.digits,
                    target_endpoint=target,
                    target_child_name=shortcut.target_child.spoken_menu_name,
                )
                for target in targets
            )
    inbound_landline_shortcut_rules = tuple(
        sorted(
            inbound_landline_shortcut_rules,
            key=lambda rule: (
                rule.public_phone_number_id,
                rule.caller_endpoint.extension,
                rule.digits,
                rule.target_endpoint.extension,
                _endpoint_sort_identity(rule.target_endpoint),
            ),
        )
    )

    tts_settings = text_to_speech_settings()
    menu_keys = {
        key
        for key, child_ids in authorized_inbound_children_by_source_and_number.items()
        if len(child_ids) > 1
    }
    prompt_texts = set()
    if menu_keys:
        prompt_texts.add(MENU_EXTENSION_TEXT)
    shortcut_prompt_texts = {
        menu_shortcut_text(rule.digits, rule.target_child_name)
        for rule in inbound_landline_shortcut_rules
        if (
            rule.caller_endpoint.child_landline_id,
            rule.public_phone_number_id,
        )
        in menu_keys
    }
    prompt_texts.update(shortcut_prompt_texts)
    spoken_prompts = tuple(
        sorted(
            (spoken_prompt(text, tts_settings) for text in prompt_texts),
            key=lambda prompt: prompt.cache_key,
        )
    )

    shortcut_rules = []
    for shortcut in (
        DialShortcut.objects.filter(is_active=True)
        .select_related(
            "source_device",
            "internal_target_device",
            "external_target_extension",
            "external_target_extension__external_phone_number",
            "parent_phone_target",
            "child_landline_target",
        )
        .order_by("source_device_id", "digits", "id")
    ):
        source = endpoints_by_device_id.get(shortcut.source_device_id)
        if not source:
            continue
        if shortcut.internal_target_device_id:
            target = endpoints_by_device_id.get(shortcut.internal_target_device_id)
            if not target:
                continue
            shared_targets = (
                endpoint
                for endpoint in sip_endpoints_by_extension.get(target.extension, ())
                if endpoint != source
                and endpoint.owner_type == target.owner_type
                and endpoint.owner_id == target.owner_id
            )
            shortcut_rules.extend(
                DialShortcutRule(
                    source_endpoint=source,
                    digits=shortcut.digits,
                    target_endpoint=shared_target,
                )
                for shared_target in shared_targets
            )
        elif (
            shortcut.external_target_extension_id
            and shortcut.external_target_extension.is_active
        ):
            shortcut_rules.append(
                DialShortcutRule(
                    source_endpoint=source,
                    digits=shortcut.digits,
                    external_number_extension_id=shortcut.external_target_extension_id,
                    normalized_number=(
                        shortcut.external_target_extension.external_phone_number.normalized_number
                    ),
                )
            )
        elif shortcut.parent_phone_target_id and shortcut.parent_phone_target.phone:
            shortcut_rules.append(
                DialShortcutRule(
                    source_endpoint=source,
                    digits=shortcut.digits,
                    normalized_number=shortcut.parent_phone_target.phone,
                )
            )
        elif shortcut.child_landline_target_id:
            target = landline_endpoints_by_id.get(shortcut.child_landline_target_id)
            if not target:
                continue
            shortcut_rules.append(
                DialShortcutRule(
                    source_endpoint=source,
                    digits=shortcut.digits,
                    target_endpoint=target,
                )
            )

    return AsteriskConfiguration(
        endpoints=endpoints,
        landline_endpoints=landline_endpoints,
        outbound_caller_id=settings.ASTERISK_OUTBOUND_CALLER_ID,
        public_inbound_numbers=public_inbound_numbers,
        external_dialplan_rules=external_rules,
        inbound_external_caller_rules=inbound_external_caller_rules,
        inbound_landline_caller_rules=inbound_landline_caller_rules,
        inbound_landline_shortcut_rules=inbound_landline_shortcut_rules,
        spoken_prompts=spoken_prompts,
        text_to_speech_settings=tts_settings,
        shortcut_rules=tuple(shortcut_rules),
        conference_routes=tuple(conference_routes),
        dialplan_rules=tuple(
            sorted(
                rules,
                key=lambda rule: (
                    rule.source_endpoint.device_id,
                    rule.target_endpoint.extension,
                    _endpoint_sort_identity(rule.target_endpoint),
                ),
            )
        ),
    )


def _endpoints_may_call(source, target, approved_child_family_pairs):
    if source.family_id == target.family_id:
        return True

    if source.child_id and target.child_id:
        return (
            source.child_id,
            target.family_id,
        ) in approved_child_family_pairs and (
            target.child_id,
            source.family_id,
        ) in approved_child_family_pairs

    if source.child_id:
        return (source.child_id, target.family_id) in approved_child_family_pairs

    if target.child_id:
        return (target.child_id, source.family_id) in approved_child_family_pairs

    return False


def _endpoint_sort_identity(endpoint):
    if hasattr(endpoint, "device_id"):
        return ("sip", endpoint.device_id)
    return ("landline", endpoint.child_landline_id)

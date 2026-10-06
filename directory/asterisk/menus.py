from .domain import SipEndpoint


def external_caller_menu_shortcuts(caller_rules):
    """Assign up to nine children choices, scoped to one caller and public number."""
    rules_by_child = {}
    for rule in caller_rules:
        rules_by_child.setdefault(rule.target_endpoint.child_id, []).append(rule)

    shortcuts = {}
    for index, child_id in enumerate(sorted(rules_by_child)[:9], start=1):
        rules = rules_by_child[child_id]
        # Match landline menus: ring all active SIP phones, or the child's landline.
        sip_rules = [
            rule for rule in rules if isinstance(rule.target_endpoint, SipEndpoint)
        ]
        shortcuts[str(index)] = tuple(sip_rules or rules)
    return shortcuts

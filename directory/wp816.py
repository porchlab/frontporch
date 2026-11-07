"""WP816 XML for the 1.0.3.39 compatibility pilot; no network or database access.

Parameter source: Grandstream config-template-10212026.zip,
wp8x6_config_1.0.3.39.txt. Never log rendered profiles or input configuration.
"""

import base64
import binascii
import configparser
import ipaddress
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from django.views.decorators.debug import sensitive_variables

from .gdms import normalize_mac


class WP816ConfigurationError(ValueError):
    """Messages identify fields without including configuration values."""


def _text(value, field, maximum=255, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or
            (not value and not empty) or
            any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in value)):
        raise WP816ConfigurationError(f"Invalid {field}.")
    return value


def _number(value, field, low, high):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise WP816ConfigurationError(f"Invalid {field}.")
    result = int(value)
    if not low <= result <= high:
        raise WP816ConfigurationError(f"Invalid {field}.")
    return str(result)


@sensitive_variables()
def _key(value, field):
    try:
        valid = isinstance(value, str) and len(base64.b64decode(value, validate=True)) == 32
    except (ValueError, binascii.Error):
        valid = False
    if not valid:
        raise WP816ConfigurationError(f"Invalid {field}.")
    return value


@sensitive_variables()
def _xml(mac, values):
    root = ET.Element("gs_provision", version="1")
    ET.SubElement(root, "mac").text = normalize_mac(mac).lower()
    config = ET.SubElement(root, "config", version="1")
    for name, value in sorted(values.items(), key=lambda item: int(item[0][1:])):
        ET.SubElement(config, name).text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def account_label(extension=None):
    """Keep family/person names out of the handset's account branding."""
    if extension is None or extension == "":
        return "FrontPorch"
    if type(extension) not in (str, int) or not re.fullmatch(r"[0-9]{3,4}", str(extension)):
        raise WP816ConfigurationError("Invalid FrontPorch extension.")
    return f"FrontPorch {extension}"


def account_label_profile(mac, extension=None):
    """Update only the visible account label of an already configured phone."""
    return _xml(mac, {"P270": account_label(extension)})


@sensitive_variables()
def device_profile(mac, wireguard_text, sip):
    """Render one private IPv4 VPN peer and its existing SIP account.

    This deliberately supports only the pilot's UDP/PCMU/RFC2833 configuration.
    Unsupported input fails before any profile can be delivered to the handset.
    """
    if not isinstance(wireguard_text, str) or len(wireguard_text) > 16384 or not isinstance(sip, dict):
        raise WP816ConfigurationError("Invalid pilot configuration format.")
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.optionxform = str
    try:
        config.read_string(wireguard_text)
    except configparser.Error:
        raise WP816ConfigurationError("Invalid WireGuard configuration syntax.") from None
    if config.defaults() or set(config.sections()) != {"Interface", "Peer"}:
        raise WP816ConfigurationError("Provide exactly one WireGuard interface and peer.")
    interface, peer = config["Interface"], config["Peer"]
    allowed_interface = {"PrivateKey", "Address", "DNS", "MTU", "ListenPort"}
    allowed_peer = {"PublicKey", "PresharedKey", "Endpoint", "AllowedIPs", "PersistentKeepalive"}
    if set(interface) - allowed_interface or set(peer) - allowed_peer:
        raise WP816ConfigurationError("Unsupported WireGuard option; hooks are not accepted.")
    try:
        address = ipaddress.ip_interface(interface.get("Address", ""))
        networks = [ipaddress.ip_network(n.strip(), strict=False) for n in peer.get("AllowedIPs", "").split(",")]
        sip_address = ipaddress.ip_address(sip.get("sip_server", ""))
    except (ValueError, TypeError):
        raise WP816ConfigurationError("Invalid VPN address, routes, or private SIP server address.") from None
    private_ranges = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    if address.version != 4 or not any(address.network.subnet_of(n) for n in private_ranges):
        raise WP816ConfigurationError("The pilot requires a private IPv4 VPN address.")
    if not 1 <= len(networks) <= 10 or any(
        n.version != 4 or not any(n.subnet_of(p) for p in private_ranges) for n in networks
    ):
        raise WP816ConfigurationError("VPN routes must be explicit private IPv4 networks, without a default route.")
    if sip_address.version != 4 or not any(sip_address in n for n in networks):
        raise WP816ConfigurationError("The SIP server must be covered by a private VPN route.")
    endpoint = peer.get("Endpoint", "")
    try:
        parsed = urlsplit("udp://" + endpoint)
        port = parsed.port
        valid_endpoint = (parsed.hostname and port and not parsed.username and not parsed.password
                          and not parsed.path and not parsed.query and not parsed.fragment
                          and re.fullmatch(r"[A-Za-z0-9.:[\]-]+", endpoint))
    except ValueError:
        valid_endpoint = False
    if not valid_endpoint:
        raise WP816ConfigurationError("Invalid WireGuard peer endpoint.")
    if (sip.get("transport") != "UDP" or sip.get("nat_traversal") not in ("WireGuard", "VPN")
            or sip.get("codec") not in ("PCMU", "PCMU / G.711u")
            or sip.get("dtmf") != "RFC2833" or type(sip.get("registration")) is not bool):
        raise WP816ConfigurationError("Pilot SIP settings must use UDP, VPN, PCMU, and RFC2833.")
    username = _text(sip.get("sip_username"), "SIP username", 100)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
        raise WP816ConfigurationError("Invalid SIP username.")
    values = {
        "P22583": "1", "P22587": _key(interface.get("PrivateKey"), "WireGuard private key"),
        "P22584": str(address), "P22589": _key(peer.get("PublicKey"), "WireGuard peer public key"),
        "P22588": endpoint, "P22591": ",".join(map(str, networks)),
        "P22590": _number(peer.get("PersistentKeepalive", "25"), "keepalive", 1, 65535),
        "P22586": "", "P22592": "",
        "P271": "1" if sip["registration"] else "0",
        "P31": "1" if sip["registration"] else "0",
        # Maintain the SIP mapping across the bridge-networked VPN server's NAT.
        "P2397": "1", "P2398": "25", "P2399": "3",
        "P270": account_label(sip.get("sip_extension", sip.get("parent_extension"))),
        "P47": f"{sip_address}:{_number(sip.get('sip_port'), 'SIP port', 1, 65535)}",
        "P35": username, "P36": username, "P34": _text(sip.get("sip_password"), "SIP password"),
        "P130": "0", "P52": "5", "P95002": "0", "P57": "0",
        "P2301": "0", "P2302": "1", "P2303": "0", "P79": "101",
    }
    if interface.get("DNS"):
        try:
            dns = ipaddress.ip_address(interface["DNS"])
        except ValueError:
            raise WP816ConfigurationError("The pilot supports one VPN DNS IP address.") from None
        if dns.version != 4 or not any(dns in n for n in networks):
            raise WP816ConfigurationError("VPN DNS must be covered by a private VPN route.")
        values["P22586"] = str(dns)
    if interface.get("MTU"):
        values["P22593"] = _number(interface["MTU"], "VPN MTU", 576, 1500)
    if interface.get("ListenPort"):
        values["P22585"] = _number(interface["ListenPort"], "VPN listening port", 1, 65535)
    if peer.get("PresharedKey"):
        values["P22592"] = _key(peer["PresharedKey"], "WireGuard preshared key")
    return _xml(mac, values)


@sensitive_variables()
def bootstrap_profile(mac, base_url, username, password):
    """GDMS receives only HTTPS bootstrap credentials, not VPN/SIP secrets."""
    try:
        url = urlsplit(base_url)
        valid = (url.scheme == "https" and url.hostname and url.port in (None, 443)
                 and not url.username and not url.password and not url.query and not url.fragment
                 and re.fullmatch(r"[A-Za-z0-9./:_-]+", base_url))
    except ValueError:
        valid = False
    if not valid:
        raise WP816ConfigurationError("Provisioning requires a credential-free HTTPS URL on port 443.")
    return _xml(mac, {
        "P212": "2", "P237": base_url.rstrip("/"),
        "P1360": _text(username, "provisioning username", 64),
        "P1361": _text(password, "provisioning password", 64),
        "P20713": "0", "P8463": "1", "P22030": "1", "P145": "0",
        "P8337": "0", "P8467": "0", "P8375": "0", "P1414": "1",
    })


def disable_provisioning(mac):
    """Retire a temporary download location, preserving VPN and SIP settings."""
    return _xml(mac, {"P1414": "0", "P237": "", "P1360": "", "P1361": ""})

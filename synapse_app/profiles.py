"""Declarative profiles for existing engines; measurements remain model/build specific."""

from copy import deepcopy
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import re


CONTRACTS = {
    ("standard", "auto", "classic", False): (set(), {"native-fitting"}, "baseline"),
    ("standard", "cpu", "classic", False): (set(), {"native-cpu"}, "baseline"),
    ("hybrid", "auto", "classic", False): ({"moe", "hybrid"}, {"expert-sharing"}, "existing-experimental"),
    ("hybrid", "auto", "hosted", False): (
        {"moe", "hybrid", "hosted", "direct"}, {"expert-sharing", "hosted-experts"}, "existing-experimental"),
    ("standard", "auto", "classic", True): (
        {"moe", "native_cache"}, {"native-fitting", "gpu-expert-cache"}, "existing-experimental"),
    ("strata", "auto", "classic", False): (
        {"moe", "strata"}, {"expert-sharing", "native-mtp"}, "existing-experimental"),
}
IDENTIFIERS = dict(zip(CONTRACTS, ("standard-auto", "standard-cpu", "hybrid-classic", "hybrid-hosted",
                                 "standard-native-cache", "strata-mtp")))


def validate(data: object) -> dict:
    if (not isinstance(data, dict) or set(data) != {"schema_version", "profiles"} or
            type(data["schema_version"]) is not int or data["schema_version"] != 1 or
            not isinstance(data["profiles"], list) or not 1 <= len(data["profiles"]) <= 16):
        raise ValueError("Unsupported execution-profile catalog.")
    identifiers = set()
    contracts = set()
    for profile in data["profiles"]:
        if (not isinstance(profile, dict) or
                set(profile) not in ({"id", "settings", "requires", "components", "qualification"},
                                     {"id", "settings", "requires", "components", "qualification", "native_cache"}) or
                not isinstance(profile["id"], str) or
                not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", profile["id"]) or profile["id"] in identifiers):
            raise ValueError("Invalid or duplicate execution profile.")
        settings = profile["settings"]
        if not isinstance(settings, dict) or set(settings) != {"execution_mode", "placement", "hybrid_variant"}:
            raise ValueError("Profiles may configure only existing execution settings.")
        native_cache = profile.get("native_cache", False)
        if type(native_cache) is not bool:
            raise ValueError("Native-cache profile guards must be boolean.")
        core = tuple(settings[key] for key in ("execution_mode", "placement", "hybrid_variant"))
        contract = (*core, native_cache)
        if any(not isinstance(value, str) for value in core) or contract not in CONTRACTS or contract in contracts:
            raise ValueError("Unsupported or duplicate execution-profile contract.")
        if profile["id"] != IDENTIFIERS[contract]:
            raise ValueError("Execution-profile identifiers must preserve the existing engine contract.")
        requirements, components, qualification = CONTRACTS[contract]
        for field, expected in (("requires", requirements), ("components", components)):
            values = profile[field]
            if (not isinstance(values, list) or any(not isinstance(value, str) for value in values) or
                    len(set(values)) != len(values) or set(values) != expected):
                raise ValueError("Profile components and guards must match the existing engine contract.")
        if profile["qualification"] != qualification:
            raise ValueError("Profiles cannot declare unmeasured experimental engines qualified.")
        identifiers.add(profile["id"])
        contracts.add(contract)
    if contracts != set(CONTRACTS):
        raise ValueError("The catalog must preserve every existing execution contract.")
    return deepcopy(data)


@lru_cache(maxsize=1)
def _catalog() -> dict:
    resource = files(__package__).joinpath("execution-profiles.json").read_bytes()
    if len(resource) > 32768:
        raise ValueError("Execution-profile catalog exceeds 32 KiB.")
    return validate(json.loads(resource))


def definition(identifier: str) -> dict:
    for profile in _catalog()["profiles"]:
        if profile["id"] == identifier:
            return deepcopy(profile)
    raise ValueError("Unknown execution profile.")


def revision(identifier: str) -> str:
    return hashlib.sha256(json.dumps(definition(identifier), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def identify(settings: dict) -> str | None:
    cache = settings.get("expert_cache_mib", 0)
    native_cache = settings.get("execution_mode") == "standard" and type(cache) is int and cache > 0
    for profile in _catalog()["profiles"]:
        if (profile.get("native_cache", False) == native_cache and
                all(settings.get(key) == value for key, value in profile["settings"].items())):
            return profile["id"]
    return None


def settings(identifier: str) -> dict:
    return definition(identifier)["settings"]


def assess(capabilities: dict) -> list[dict]:
    result = []
    for profile in _catalog()["profiles"]:
        missing = [name for name in profile["requires"] if capabilities.get(name) is not True]
        result.append({**deepcopy(profile), "revision": revision(profile["id"]),
                       "eligibility": "unavailable" if missing else "candidate",
                       "missing_requirements": missing,
                       "measurement_scope": "Local capacity and speed checks; not general numerical or answer quality.",
                       "requires_runtime_verification": True})
    return result


def measured_profile_valid(entry: dict) -> bool:
    identifier, fingerprint = entry.get("profile_id"), entry.get("profile_revision")
    if "profile_id" not in entry and "profile_revision" not in entry:
        return True
    if not isinstance(identifier, str) or not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        return False
    try:
        definition(identifier)
        return identify(entry["settings"]) == identifier
    except (KeyError, ValueError):
        return False


def measured_profile_current(entry: dict) -> bool:
    if not measured_profile_valid(entry):
        return False
    return "profile_id" not in entry or entry["profile_revision"] == revision(entry["profile_id"])

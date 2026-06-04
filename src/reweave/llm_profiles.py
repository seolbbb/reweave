"""Stored LLM provider profiles backed by OS keyring secrets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

import keyring

SERVICE_NAME = "Reweave"


@dataclass(frozen=True)
class LLMKeyRef:
    id: str
    label: str
    enabled: bool = True
    priority: int = 0


@dataclass(frozen=True)
class LLMProfile:
    id: str
    name: str
    provider: str
    base_url: str = ""
    default_model: str = ""
    custom_models: tuple[str, ...] = ()
    keys: tuple[LLMKeyRef, ...] = ()


@dataclass(frozen=True)
class LLMKeyCredential:
    key_id: str
    label: str
    api_key: str


@dataclass(frozen=True)
class StoredLLMProfiles:
    active_profile_id: str | None = None
    profiles: tuple[LLMProfile, ...] = ()


@dataclass(frozen=True)
class KeyInput:
    label: str
    api_key: str | None = None
    enabled: bool = True
    priority: int = 0


@dataclass(frozen=True)
class ProfileInput:
    name: str
    provider: str
    base_url: str = ""
    default_model: str = ""
    custom_models: tuple[str, ...] = ()
    keys: tuple[KeyInput, ...] = ()


class LLMProfileStore:
    """Store non-secret profile data on disk and API keys in keyring."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> StoredLLMProfiles:
        return self._load()

    def get(self, profile_id: str) -> LLMProfile | None:
        return next(
            (profile for profile in self._load().profiles if profile.id == profile_id),
            None,
        )

    def create(self, data: ProfileInput) -> LLMProfile:
        stored = self._load()
        profile = LLMProfile(
            id=uuid4().hex,
            name=data.name.strip() or "LLM Profile",
            provider=data.provider.strip(),
            base_url=data.base_url.strip(),
            default_model=data.default_model.strip(),
            custom_models=tuple(model.strip() for model in data.custom_models if model.strip()),
            keys=tuple(
                self._create_key_ref(profile_id="", key=data_key)
                for data_key in data.keys
                if data_key.label.strip()
            ),
        )
        profile = self._rebind_key_profile(profile, profile.id)
        for key_ref, key_input in zip(profile.keys, data.keys, strict=False):
            if key_input.api_key:
                self._set_secret(profile.id, key_ref.id, key_input.api_key)

        active_profile_id = stored.active_profile_id or profile.id
        self._save(
            StoredLLMProfiles(
                active_profile_id=active_profile_id,
                profiles=(*stored.profiles, profile),
            )
        )
        return profile

    def update(self, profile_id: str, data: ProfileInput) -> LLMProfile:
        stored = self._load()
        existing = self.get(profile_id)
        if existing is None:
            raise ValueError("LLM profile not found.")

        updated = LLMProfile(
            id=profile_id,
            name=data.name.strip() or existing.name,
            provider=data.provider.strip() or existing.provider,
            base_url=data.base_url.strip(),
            default_model=data.default_model.strip(),
            custom_models=tuple(model.strip() for model in data.custom_models if model.strip()),
            keys=existing.keys,
        )
        profiles = tuple(
            updated if profile.id == profile_id else profile for profile in stored.profiles
        )
        self._save(StoredLLMProfiles(stored.active_profile_id, profiles))
        return updated

    def delete(self, profile_id: str) -> None:
        stored = self._load()
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")

        for key_ref in profile.keys:
            self._delete_secret(profile_id, key_ref.id)
        profiles = tuple(profile for profile in stored.profiles if profile.id != profile_id)
        active_profile_id = stored.active_profile_id
        if active_profile_id == profile_id:
            active_profile_id = profiles[0].id if profiles else None
        self._save(StoredLLMProfiles(active_profile_id, profiles))

    def set_active(self, profile_id: str | None) -> None:
        stored = self._load()
        if profile_id is not None and not any(
            profile.id == profile_id for profile in stored.profiles
        ):
            raise ValueError("LLM profile not found.")
        self._save(StoredLLMProfiles(profile_id, stored.profiles))

    def add_key(self, profile_id: str, data: KeyInput) -> LLMKeyRef:
        stored = self._load()
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")

        key_ref = self._create_key_ref(profile_id=profile_id, key=data)
        if data.api_key:
            self._set_secret(profile_id, key_ref.id, data.api_key)
        updated = LLMProfile(**{**asdict(profile), "keys": (*profile.keys, key_ref)})
        self._replace_profile(stored, updated)
        return key_ref

    def update_key(self, profile_id: str, key_id: str, data: KeyInput) -> LLMKeyRef:
        stored = self._load()
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")
        if not any(key.id == key_id for key in profile.keys):
            raise ValueError("LLM profile key not found.")

        key_ref = LLMKeyRef(
            id=key_id,
            label=data.label.strip() or "API key",
            enabled=data.enabled,
            priority=data.priority,
        )
        if data.api_key is not None:
            self._set_secret(profile_id, key_id, data.api_key)

        keys = tuple(key_ref if key.id == key_id else key for key in profile.keys)
        updated = LLMProfile(**{**asdict(profile), "keys": keys})
        self._replace_profile(stored, updated)
        return key_ref

    def delete_key(self, profile_id: str, key_id: str) -> None:
        stored = self._load()
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")
        if not any(key.id == key_id for key in profile.keys):
            raise ValueError("LLM profile key not found.")

        self._delete_secret(profile_id, key_id)
        keys = tuple(key for key in profile.keys if key.id != key_id)
        updated = LLMProfile(**{**asdict(profile), "keys": keys})
        self._replace_profile(stored, updated)

    def replace_keys(self, profile_id: str, data: KeyInput) -> LLMKeyRef:
        """Replace a profile's credentials with one primary key."""
        self.clear_keys(profile_id)
        return self.add_key(profile_id, data)

    def clear_keys(self, profile_id: str) -> None:
        """Remove every credential from a profile."""
        stored = self._load()
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")

        for key_ref in profile.keys:
            self._delete_secret(profile_id, key_ref.id)
        updated = LLMProfile(**{**asdict(profile), "keys": ()})
        self._replace_profile(stored, updated)

    def credentials_for(self, profile_id: str) -> tuple[LLMKeyCredential, ...]:
        profile = self.get(profile_id)
        if profile is None:
            raise ValueError("LLM profile not found.")

        credentials: list[LLMKeyCredential] = []
        for key_ref in sorted(profile.keys, key=lambda key: (key.priority, key.label)):
            if not key_ref.enabled:
                continue
            secret = self._get_secret(profile_id, key_ref.id)
            if secret:
                credentials.append(
                    LLMKeyCredential(
                        key_id=key_ref.id,
                        label=key_ref.label,
                        api_key=secret,
                    )
                )
        return tuple(credentials)

    def has_secret(self, profile_id: str, key_id: str) -> bool:
        return bool(self._get_secret(profile_id, key_id))

    def _replace_profile(self, stored: StoredLLMProfiles, updated: LLMProfile) -> None:
        profiles = tuple(
            updated if profile.id == updated.id else profile for profile in stored.profiles
        )
        self._save(StoredLLMProfiles(stored.active_profile_id, profiles))

    def _load(self) -> StoredLLMProfiles:
        if not self.path.exists():
            return StoredLLMProfiles()
        with open(self.path, encoding="utf-8") as file:
            data = json.load(file)
        return StoredLLMProfiles(
            active_profile_id=data.get("active_profile_id"),
            profiles=tuple(_profile_from_dict(item) for item in data.get("profiles", [])),
        )

    def _save(self, stored: StoredLLMProfiles) -> None:
        data = {
            "active_profile_id": stored.active_profile_id,
            "profiles": [_profile_to_dict(profile) for profile in stored.profiles],
        }
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    def _create_key_ref(self, *, profile_id: str, key: KeyInput) -> LLMKeyRef:
        return LLMKeyRef(
            id=uuid4().hex,
            label=key.label.strip() or "API key",
            enabled=key.enabled,
            priority=key.priority,
        )

    def _rebind_key_profile(self, profile: LLMProfile, profile_id: str) -> LLMProfile:
        return LLMProfile(
            id=profile_id,
            name=profile.name,
            provider=profile.provider,
            base_url=profile.base_url,
            default_model=profile.default_model,
            custom_models=profile.custom_models,
            keys=profile.keys,
        )

    def _set_secret(self, profile_id: str, key_id: str, value: str) -> None:
        keyring.set_password(SERVICE_NAME, _secret_name(profile_id, key_id), value)

    def _get_secret(self, profile_id: str, key_id: str) -> str | None:
        return keyring.get_password(SERVICE_NAME, _secret_name(profile_id, key_id))

    def _delete_secret(self, profile_id: str, key_id: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, _secret_name(profile_id, key_id))
        except keyring.errors.PasswordDeleteError:
            return


@dataclass(frozen=True)
class ProfileSeed:
    name: str
    provider: str
    default_model: str
    base_url: str = ""
    custom_models: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_PROFILE_SEEDS = (
    ProfileSeed("OpenAI", "openai", "gpt-4o-mini"),
    ProfileSeed("Anthropic", "anthropic", "claude-3-5-sonnet-latest"),
    ProfileSeed("Gemini", "gemini", "gemini-1.5-flash"),
    ProfileSeed("OpenRouter", "openrouter", ""),
    ProfileSeed("OpenAI Compatible", "openai-compatible", ""),
)


def ensure_default_profiles(store: LLMProfileStore) -> None:
    stored = store.list()
    existing_providers = {profile.provider for profile in stored.profiles}
    for seed in DEFAULT_PROFILE_SEEDS:
        if seed.provider in existing_providers:
            continue
        store.create(
            ProfileInput(
                name=seed.name,
                provider=seed.provider,
                base_url=seed.base_url,
                default_model=seed.default_model,
                custom_models=seed.custom_models,
            )
        )


def _secret_name(profile_id: str, key_id: str) -> str:
    return f"llm-profile:{profile_id}:key:{key_id}"


def _profile_from_dict(data: dict) -> LLMProfile:
    return LLMProfile(
        id=str(data["id"]),
        name=str(data.get("name") or "LLM Profile"),
        provider=str(data.get("provider") or "openai"),
        base_url=str(data.get("base_url") or ""),
        default_model=str(data.get("default_model") or ""),
        custom_models=tuple(str(item) for item in data.get("custom_models", [])),
        keys=tuple(_key_from_dict(item) for item in data.get("keys", [])),
    )


def _key_from_dict(data: dict) -> LLMKeyRef:
    return LLMKeyRef(
        id=str(data["id"]),
        label=str(data.get("label") or "API key"),
        enabled=bool(data.get("enabled", True)),
        priority=int(data.get("priority", 0)),
    )


def _profile_to_dict(profile: LLMProfile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "provider": profile.provider,
        "base_url": profile.base_url,
        "default_model": profile.default_model,
        "custom_models": list(profile.custom_models),
        "keys": [asdict(key) for key in profile.keys],
    }

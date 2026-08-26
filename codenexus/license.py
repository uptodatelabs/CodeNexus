"""License management for CodeNexus Pro.

Honest limitation: keys are structurally validated only (no cryptographic
signature), and state lives in a local JSON file — a determined user can
forge either. This module's real value is consistent *enforcement* of tier
limits across the product; it is not DRM.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class LicenseTier(Enum):
    """License tier levels."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class License:
    """License information."""

    tier: LicenseTier
    key: str
    owner: str
    expires_at: datetime | None = None
    features: list[str] | None = None

    def __post_init__(self):
        if self.features is None:
            self.features = []


class LicenseManager:
    """Manage license validation and features."""

    # Free tier limitations
    FREE_LIMITS = {
        "max_nodes": 5000,
        "max_repos": 1,
        "languages": ["python", "javascript", "typescript"],
        "llm": False,
        "multi_repo": False,
        "memory": False,
        "vscode_extension": True,
        "cli": True,
    }

    # Pro tier features
    PRO_FEATURES = {
        "max_nodes": 100000,
        "max_repos": 10,
        "languages": "all",
        "llm": True,
        "multi_repo": True,
        "memory": True,
        "vscode_extension": True,
        "cli": True,
        "priority_support": True,
        "custom_themes": True,
    }

    def __init__(self):
        self.config_path = Path.home() / ".codenexus" / "license.json"
        self._license: License | None = None
        self._load_license()

    def _load_license(self):
        """Load license from disk."""
        if not self.config_path.exists():
            return
        try:
            with open(self.config_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            self._license = License(
                tier=LicenseTier(data["tier"]),
                key=data.get("key", ""),
                owner=data.get("owner", ""),
                expires_at=datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None,
                features=data.get("features", []),
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Could not load license file %s: %s", self.config_path, e)
            self._license = None

    def _save_license(self):
        """Save license to disk."""
        if not self._license:
            return

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "tier": self._license.tier.value,
            "key": self._license.key,
            "owner": self._license.owner,
            "expires_at": self._license.expires_at.isoformat()
            if self._license.expires_at
            else None,
            "features": self._license.features,
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def activate_license(self, license_key: str) -> bool:
        """
        Activate a license key.

        Args:
            license_key: License key to activate

        Returns:
            True if activation successful
        """
        # In production, this would call a license server
        # For now, simulate validation

        if not license_key or not license_key.startswith("CNX-"):
            return False

        # Parse license key (simplified)
        parts = license_key.split("-")
        if len(parts) != 4:
            return False

        tier = parts[1]
        owner = parts[2]
        expiry_str = parts[3]

        try:
            expires_at = datetime.strptime(expiry_str, "%Y%m%d")
        except ValueError:
            return False

        try:
            tier_enum = LicenseTier(tier)
        except ValueError:
            logger.warning("Unknown tier %r in license key", tier)
            return False

        # Check if expired
        if expires_at < datetime.now():
            return False

        self._license = License(
            tier=tier_enum, key=license_key, owner=owner, expires_at=expires_at
        )

        self._save_license()
        return True

    def get_tier(self) -> LicenseTier:
        """Get current license tier."""
        if not self._license:
            return LicenseTier.FREE

        # Check if expired
        if self._license.expires_at and self._license.expires_at < datetime.now():
            return LicenseTier.FREE

        return self._license.tier

    def has_feature(self, feature: str) -> bool:
        """
        Check if current tier has a feature.

        Only strict ``True`` counts as available on the free tier, so list /
        string values like ``languages`` correctly read as Pro-only here.
        Use :meth:`get_limit` for raw numeric/list values.

        Args:
            feature: Feature name

        Returns:
            True if feature is available
        """
        tier = self.get_tier()

        if tier == LicenseTier.FREE:
            return self.FREE_LIMITS.get(feature, False) is True

        # Fail closed on unknown features rather than silently granting them.
        return bool(self.PRO_FEATURES.get(feature, False))

    def get_limit(self, limit_name: str):
        """
        Get a raw limit value for the current tier.

        Args:
            limit_name: Limit name (e.g. ``max_nodes``, ``max_repos``)

        Returns:
            The configured value; callers decide how to interpret it.
        """
        tier = self.get_tier()

        if tier == LicenseTier.FREE:
            return self.FREE_LIMITS.get(limit_name)
        elif tier in [LicenseTier.PRO, LicenseTier.TEAM, LicenseTier.ENTERPRISE]:
            return self.PRO_FEATURES.get(limit_name)

        return None

    def check_feature(self, feature: str) -> bool:
        """
        Check feature and log a message if not available.

        Args:
            feature: Feature name

        Returns:
            True if feature is available
        """
        if self.has_feature(feature):
            return True

        tier = self.get_tier()
        # Library code must not print to stdout: the stdio MCP server shares
        # that stream with JSON-RPC responses.
        logger.warning(
            "Feature '%s' requires Pro license (current tier: %s). "
            "Upgrade at https://codenexus.dev/pricing",
            feature,
            tier.value,
        )
        return False

    def get_license_info(self) -> dict:
        """Get license information."""
        tier = self.get_tier()

        return {
            "tier": tier.value,
            "owner": self._license.owner if self._license else "",
            "expires_at": self._license.expires_at.isoformat()
            if self._license and self._license.expires_at
            else None,
            "is_valid": tier != LicenseTier.FREE or not self._license,
        }


# Global license instance
_global_license: LicenseManager | None = None


def get_license() -> LicenseManager:
    """Get or create global license instance."""
    global _global_license
    if _global_license is None:
        _global_license = LicenseManager()
    return _global_license

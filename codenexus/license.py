"""License management for CodeNexus Pro."""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


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
    features: list[str] = None

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
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    self._license = License(
                        tier=LicenseTier(data.get("tier", "free")),
                        key=data.get("key", ""),
                        owner=data.get("owner", ""),
                        expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
                        features=data.get("features", [])
                    )
            except Exception:
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
            "expires_at": self._license.expires_at.isoformat() if self._license.expires_at else None,
            "features": self._license.features
        }

        with open(self.config_path, "w") as f:
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

        # Check if expired
        if expires_at < datetime.now():
            return False

        self._license = License(
            tier=LicenseTier(tier),
            key=license_key,
            owner=owner,
            expires_at=expires_at
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
        
        Args:
            feature: Feature name
        
        Returns:
            True if feature is available
        """
        tier = self.get_tier()

        if tier == LicenseTier.FREE:
            return self.FREE_LIMITS.get(feature, False)
        elif tier in [LicenseTier.PRO, LicenseTier.TEAM, LicenseTier.ENTERPRISE]:
            return self.PRO_FEATURES.get(feature, True)

        return False

    def get_limit(self, limit_name: str) -> int | None:
        """
        Get a limit for the current tier.
        
        Args:
            limit_name: Limit name
        
        Returns:
            Limit value or None for unlimited
        """
        tier = self.get_tier()

        if tier == LicenseTier.FREE:
            return self.FREE_LIMITS.get(limit_name)
        elif tier in [LicenseTier.PRO, LicenseTier.TEAM, LicenseTier.ENTERPRISE]:
            return self.PRO_FEATURES.get(limit_name)

        return None

    def check_feature(self, feature: str) -> bool:
        """
        Check feature and print message if not available.
        
        Args:
            feature: Feature name
        
        Returns:
            True if feature is available
        """
        if self.has_feature(feature):
            return True

        tier = self.get_tier()
        print(f"Feature '{feature}' requires Pro license")
        print(f"Current tier: {tier.value}")
        print("Upgrade at: https://codenexus.dev/pricing")
        return False

    def get_license_info(self) -> dict:
        """Get license information."""
        tier = self.get_tier()

        return {
            "tier": tier.value,
            "owner": self._license.owner if self._license else "",
            "expires_at": self._license.expires_at.isoformat() if self._license and self._license.expires_at else None,
            "is_valid": tier != LicenseTier.FREE or not self._license
        }


# Global license instance
_global_license: LicenseManager | None = None

def get_license() -> LicenseManager:
    """Get or create global license instance."""
    global _global_license
    if _global_license is None:
        _global_license = LicenseManager()
    return _global_license

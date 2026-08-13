"""SystemConfig model — represents the data in system.toml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssetConfig:
    """The [asset] section of system.toml."""

    use_local_asset: bool = False
    local_asset_path: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> AssetConfig:
        return cls(
            use_local_asset=data.get("use_local_asset", False),
            local_asset_path=data.get("local_asset_path", ""),
        )

    def to_dict(self) -> dict:
        return {
            "use_local_asset": self.use_local_asset,
            "local_asset_path": self.local_asset_path,
        }


@dataclass
class SimConfig:
    """The [sim] section of system.toml."""

    default_version: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> SimConfig:
        return cls(default_version=str(data.get("default_version", "") or "").strip())

    def to_dict(self) -> dict:
        return {"default_version": self.default_version}


@dataclass
class SystemConfig:
    """
    In-memory representation of system.toml.

    File structure
    --------------
    [asset]
      use_local_asset  — bool, set by 'pow asset attach / detach'
      local_asset_path — absolute path to the attached local asset directory

    [sim]
      default_version  — Isaac Sim version used when '-v' is omitted; empty
                         means auto (the newest installed version)
    """

    asset: AssetConfig
    sim: SimConfig = field(default_factory=SimConfig)

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> SystemConfig:
        return cls(
            asset=AssetConfig.from_dict(data.get("asset", {})),
            sim=SimConfig.from_dict(data.get("sim", {})),
        )

    @classmethod
    def from_file(cls, path: Path) -> SystemConfig:
        """Load a SystemConfig from an existing system.toml file."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> SystemConfig:
        """Return a SystemConfig with default (template) values."""
        return cls(asset=AssetConfig(), sim=SimConfig())

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"asset": self.asset.to_dict(), "sim": self.sim.to_dict()}

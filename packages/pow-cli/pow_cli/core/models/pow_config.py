try:
    import tomllib
except ImportError:
    import tomli as tomllib
import distro
import click
from pathlib import Path
from typing import Any, Optional

class PowConfig:
    """Singleton class that provides project-wide configuration.

    Responsibilities:
    - Isaac Sim / ROS constants (class-level).
    - Global directory paths (home, global_path) – always available.
    - pow.toml project settings – available only when a pow.toml is found.
    """

    _instance = None

    # ── Isaac Sim constants ───────────────────────────────────────────────────

    ISAACSIM_VERSION = "5.1.0"
    ISAACSIM_FILENAME = f"isaac-sim-standalone-{ISAACSIM_VERSION}-linux-x86_64.zip"
    ISAACSIM_URL = f"https://download.isaacsim.omniverse.nvidia.com/{ISAACSIM_FILENAME}"
    SUPPORTED_UBUNTU_VERSIONS = ["22.04", "24.04"]

    # ── ROS constants ────────────────────────────────────────────────────────

    ROS_DISTRO_MAP: dict[str, str] = {"24.04": "jazzy", "22.04": "humble"}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PowConfig, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        # ── Global / home paths (always available) ────────────────────────────
        self._global_dir_name: str = self._read_global_dir_name()
        self._home: Path = Path.home()
        self._global_path: Path = self._home / self._global_dir_name

        # ── Project config (requires pow.toml) ───────────────────────────────
        self._project_root: Optional[Path] = self._find_project_root()
        self._data: dict[str, Any] = {}

        if self._project_root:
            self._load_config(self._project_root)

    @staticmethod
    def _read_global_dir_name(start_path: Optional[Path] = None) -> str:
        """Read global_dir_name from pyproject.toml or default to .pow"""
        if start_path is None:
            start_path = Path.cwd()

        current = start_path.resolve()

        while True:
            pyproject_path = current / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    try:
                        data = tomllib.load(f)
                        val = data.get("tool", {}).get("pow-cli", {}).get("global_dir_name")
                        if val:
                            return val
                    except Exception:
                        pass
                break # Found pyproject.toml but no valid global_dir_name, use default
            
            if current == current.parent:
                break
            current = current.parent

        return ".pow"

    def _find_project_root(self, start_path: Optional[Path] = None) -> Optional[Path]:
        """Find the project root by locating pow.toml."""
        if start_path is None:
            start_path = Path.cwd()

        current = start_path.resolve()

        while current != current.parent:
            if (current / "pow.toml").exists():
                return current
            current = current.parent

        if (current / "pow.toml").exists():
            return current

        return None

    def _load_config(self, project_root: Path) -> None:
        """Load pow.toml configuration into memory."""
        config_path = project_root / "pow.toml"
        if not config_path.exists():
            return

        with open(config_path, "rb") as f:
            self._data = tomllib.load(f)

    # ── Global / home path properties ────────────────────────────────────────

    @property
    def global_dir_name(self) -> str:
        """The name of the global pow directory (e.g. '.pow')."""
        return self._global_dir_name

    @property
    def home(self) -> Path:
        """The current user's home directory."""
        return self._home

    @property
    def global_path(self) -> Path:
        """Absolute path to the global pow directory (e.g. ~/.pow)."""
        return self._global_path

    @property
    def ros_ws_path(self) -> Path:
        """Absolute path to the ROS workspaces directory.

        Reads ``isaacsim_ros_ws`` from pow.toml ``[sim]``.  The value is
        stored as a tilde-relative string (e.g. ``~/IsaacSim-ros_workspaces``)
        and expanded to an absolute path here.  Falls back to
        ``~/IsaacSim-ros_workspaces`` when the key is missing or pow.toml
        is not loaded.
        """
        default = "~/IsaacSim-ros_workspaces"
        try:
            raw = self.get("isaacsim_ros_ws", default)
        except RuntimeError:
            raw = default
        return Path(raw).expanduser()

    @property
    def ros_dockerfile(self) -> str:
        """Relative path to a custom ROS Dockerfile, or "" if unset.

        Reads ``ros_dockerfile`` from pow.toml ``[sim]``.  When set, the custom
        Dockerfile is built on top of the bundled ``pow_simros_<distro>`` base
        image during ``pow init``.  Falls back to an empty string when the key
        is missing or pow.toml is not loaded.
        """
        try:
            return self.get("ros_dockerfile", "") or ""
        except RuntimeError:
            return ""

    @property
    def ros_container_name(self) -> str:
        """Name for the ROS container (and custom image tag).

        Reads ``ros_container_name`` from pow.toml ``[sim]``.  Defaults to
        ``"pow_simros"`` when the key is missing or pow.toml is not loaded.
        """
        try:
            return self.get("ros_container_name", "pow_simros") or "pow_simros"
        except RuntimeError:
            return "pow_simros"

    @property
    def ros_image_name(self) -> str:
        """Image to run with ``pow ros``.

        Returns the custom ``ros_container_name`` tag when ``ros_dockerfile`` is
        set, otherwise the bundled ``pow_simros_<distro>`` base image.
        """
        if self.ros_dockerfile:
            return self.ros_container_name
        return f"pow_simros_{self.ros_distro}"

    @property
    def ros_distro(self) -> str:
        """Get the ROS distribution for the current OS version."""
        return self.ROS_DISTRO_MAP.get(self.ubuntu_version, "humble")

    @property
    def ubuntu_version(self) -> str:
        """Get the current Ubuntu version or fallback to 22.04."""
        try:
            v = distro.version()
            if v in self.ROS_DISTRO_MAP:
                return v
        except Exception:
            pass
        return "22.04"

    # ── Project config properties ────────────────────────────────────────────

    @property
    def project_root(self) -> Optional[Path]:
        """Get the project root directory, or None if pow.toml was not found."""
        return self._project_root

    @property
    def data(self) -> dict[str, Any]:
        """Get the complete parsed data from pow.toml.

        Raises RuntimeError if pow.toml was not found during initialization.
        """
        self._require_project()
        return self._data

    def get_profile(self, profile_name: str = "default") -> dict[str, Any]:
        """
        Get a merged profile dictionary with ``extends`` and ``.add`` support.

        Resolution order
        ----------------
        1. If *profile_name* is ``"default"`` or ``"sim"``, return ``[sim]`` data.
        2. Otherwise locate the ``[[profiles]]`` entry whose ``name`` matches.
        3. Determine the *base* config:
           - No ``extends`` key, or ``extends = "default"`` → ``[sim]``
           - ``extends = "<other>"`` → recursively resolve that profile first.
             Circular references and missing targets raise ``ClickException``.
        4. Apply ``.add`` append keys: a key like ``exts.add`` appends its list
           value to the base ``exts`` list.  If the base value is not a list a
           ``ClickException`` is raised immediately (fail-fast at ``pow run``).
        5. Strip ``name``, ``extends``, and all ``*.add`` keys from the result.

        Raises
        ------
        RuntimeError
            If pow.toml was not found during initialization.
        click.ClickException
            If ``extends`` is circular, targets a missing profile, or a ``.add``
            key targets a non-list base value.
        """
        self._require_project()
        return self._resolve_profile(profile_name, _seen=set())

    def _resolve_profile(
        self,
        profile_name: str,
        _seen: "set[str]",
    ) -> "dict[str, Any]":
        """Internal recursive resolver for ``get_profile``."""
        import copy

        sim_data: dict[str, Any] = copy.deepcopy(self._data.get("sim", {}))

        if profile_name in ("default", "sim"):
            return sim_data

        profiles: list[dict[str, Any]] = self._data.get("profiles", [])
        target: dict[str, Any] | None = next(
            (p for p in profiles if p.get("name") == profile_name), None
        )
        if target is None:
            raise click.ClickException(
                f"Profile '{profile_name}' not found in pow.toml [[profiles]]."
            )

        extends: str = target.get("extends", "default")

        # ── Circular-extends guard ────────────────────────────────────────────
        if profile_name in _seen:
            cycle = " → ".join(sorted(_seen)) + f" → {profile_name}"
            raise click.ClickException(
                f"Circular 'extends' detected in pow.toml profiles: {cycle}"
            )
        _seen = _seen | {profile_name}

        # ── Resolve base ──────────────────────────────────────────────────────
        if extends in ("default", "sim"):
            base: dict[str, Any] = sim_data
        else:
            base = self._resolve_profile(extends, _seen)

        # ── Apply overrides and .add append keys ──────────────────────────────
        merged = dict(base)

        # TOML parses `exts.add = [...]` as {"exts": {"add": [...]}} (dotted keys
        # create nested dicts rather than literal string keys).  Flatten those so
        # the rest of the logic can treat them uniformly as "exts.add" string keys.
        flat_target: dict[str, Any] = {}
        for key, value in target.items():
            if (
                isinstance(value, dict)
                and list(value.keys()) == ["add"]
                and isinstance(value["add"], list)
            ):
                flat_target[f"{key}.add"] = value["add"]
            else:
                flat_target[key] = value

        # First pass: plain overrides (skip meta-keys and *.add keys)
        for key, value in flat_target.items():
            if key in ("name", "extends"):
                continue
            if key.endswith(".add"):
                continue
            merged[key] = value

        # Second pass: .add append keys
        for key, value in flat_target.items():
            if not key.endswith(".add"):
                continue
            root_key = key[: -len(".add")]
            base_value = merged.get(root_key)
            if base_value is None:
                # Key doesn't exist in base yet – treat as a plain list assignment
                merged[root_key] = list(value) if isinstance(value, list) else [value]
            elif not isinstance(base_value, list):
                raise click.ClickException(
                    f"Profile '{profile_name}': '{key}' targets '{root_key}' which is "
                    f"not a list (got {type(base_value).__name__}). "
                    "The '.add' append keyword only works with list values."
                )
            else:
                if not isinstance(value, list):
                    raise click.ClickException(
                        f"Profile '{profile_name}': '{key}' value must be a list, "
                        f"got {type(value).__name__}."
                    )
                merged[root_key] = base_value + value

        return merged


    def get(self, key: str, default: Any = None, profile: str = "default") -> Any:
        """
        Get a specific setting from pow.toml, defaulting to the '[sim]' profile.

        Args:
            key: The setting key to fetch.
            default: The default value if the key does not exist.
            profile: The profile name to look in, defaults to 'default' (which maps to [sim]).

        Raises RuntimeError if pow.toml was not found.
        """
        profile_data = self.get_profile(profile)
        return profile_data.get(key, default)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _require_project(self) -> None:
        """Raise RuntimeError if no pow.toml was found during initialization."""
        if self._project_root is None:
            raise RuntimeError("Project not initialized: pow.toml not found")

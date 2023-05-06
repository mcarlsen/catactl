from dataclasses import dataclass
import json
from .config import current_env as env
from . import Release


@dataclass
class SimpleMod:
    id: str
    mod_info: list

    def install(self):
        build = Release.load(env.current_install_data_file)
        mod_dir = build.install_target / "data" / "mods" / self.id
        mod_dir.mkdir(exist_ok=True)
        with open(mod_dir / "modinfo.json", mode="w") as output:
            json.dump(self.mod_info, fp=output, indent=2)


no_portal_storms = [
    {
        "type": "MOD_INFO",
        "id": "no_portal_storms",
        "name": "No Portal Storms",
        "authors": ["Ramza13"],
        "description": "Prevents portal storms from happening.",
        "category": "rebalance",
        "dependencies": ["dda"]
    },
    {
        "type": "effect_on_condition",
        "id": "EOC_PORTAL_STORM_WARN_OR_CAUSE_RECURRING",
        "recurrence_min": "10 days",
        "recurrence_max": "10 days",
        "global": True,
        "effect": []
    }
]

mods = {
    "no-portal-storms": SimpleMod("no_portal_storms", no_portal_storms)
}

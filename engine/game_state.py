import json
from dataclasses import dataclass, field
from typing import Optional

# Weapon (referenced by Entity — Section 4.4)

@dataclass
class Weapon:
    name: str
    weapon_type: str   # e.g. "staff", "sword", "dagger", "axe"
    damage: int        # base damage value used in combat resolution (Section 5.5)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weapon_type": self.weapon_type,
            "damage": self.damage,
        }

    @staticmethod
    def from_dict(data: dict) -> "Weapon":
        return Weapon(
            name=data["name"],
            weapon_type=data["weapon_type"],
            damage=data["damage"],
        )

# Stats (sub-object of Entity — Section 4.4)

@dataclass
class Stats:
    str: int   # Strength
    dex: int   # Dexterity
    int: int   # Intelligence  

    def to_dict(self) -> dict:
        return {
            "str": self.str,
            "dex": self.dex,
            "int": self.int,
        }

    @staticmethod
    def from_dict(data: dict) -> "Stats":
        return Stats(
            str=data["str"],
            dex=data["dex"],
            int=data["int"],
        )

# Entity (Section 4.4)

@dataclass
class Entity:
    id: str
    type: str            # "player" or "enemy"
    role: str            # e.g. "warrior", "mage", "rogue", "brute", "caster"
    level: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    stats: Stats
    weapon: Weapon
    items: list          # inventory — players only (Section 4.4)

    def is_alive(self) -> bool:
        return self.hp > 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "level": self.level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "stats": self.stats.to_dict(),
            "weapon": self.weapon.to_dict(),
            "items": self.items,
        }

    @staticmethod
    def from_dict(data: dict) -> "Entity":
        return Entity(
            id=data["id"],
            type=data["type"],
            role=data["role"],
            level=data["level"],
            hp=data["hp"],
            max_hp=data["max_hp"],
            mp=data["mp"],
            max_mp=data["max_mp"],
            stats=Stats.from_dict(data["stats"]),
            weapon=Weapon.from_dict(data["weapon"]),
            items=data["items"],
        )

# AdventureState (Section 4.2)

@dataclass
class AdventureState:
    title: str
    current_chapter: int
    boss_name: str
    boss_defeated: bool
    story_flags: dict    # e.g. {"npc_aldric_alive": True, "bridge_destroyed": False}

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "current_chapter": self.current_chapter,
            "boss_name": self.boss_name,
            "boss_defeated": self.boss_defeated,
            "story_flags": self.story_flags,
        }

    @staticmethod
    def from_dict(data: dict) -> "AdventureState":
        return AdventureState(
            title=data["title"],
            current_chapter=data["current_chapter"],
            boss_name=data["boss_name"],
            boss_defeated=data["boss_defeated"],
            story_flags=data["story_flags"],
        )


# SceneState (Section 4.3)

@dataclass
class SceneState:
    description_seed: str        # e.g. "dark forest clearing, moonlit, fog"
    active_entity_ids: list      # e.g. ["player_1", "player_2", "goblin_1"]

    def to_dict(self) -> dict:
        return {
            "description_seed": self.description_seed,
            "active_entity_ids": self.active_entity_ids,
        }

    @staticmethod
    def from_dict(data: dict) -> "SceneState":
        return SceneState(
            description_seed=data["description_seed"],
            active_entity_ids=data["active_entity_ids"],
        )
    

# GameState — Root object (Section 4.1)


@dataclass
class GameState:
    adventure: AdventureState
    scene: SceneState
    entities: dict               # { entity_id (str) : Entity }

    # Combat metadata — root level per Section 4.1
    in_combat: bool = False
    initiative_order: list = field(default_factory=list)   # ordered entity IDs
    current_turn_index: int = 0
    round_number: int = 0

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def get_active_entities(self) -> list:
        return [
            self.entities[eid]
            for eid in self.scene.active_entity_ids
            if eid in self.entities
        ]

    def to_dict(self) -> dict:
        return {
            "adventure": self.adventure.to_dict(),
            "scene": self.scene.to_dict(),
            "entities": {eid: entity.to_dict() for eid, entity in self.entities.items()},
            "in_combat": self.in_combat,
            "initiative_order": self.initiative_order,
            "current_turn_index": self.current_turn_index,
            "round_number": self.round_number,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(data: dict) -> "GameState":
        entities = {
            eid: Entity.from_dict(edata)
            for eid, edata in data["entities"].items()
        }
        return GameState(
            adventure=AdventureState.from_dict(data["adventure"]),
            scene=SceneState.from_dict(data["scene"]),
            entities=entities,
            in_combat=data["in_combat"],
            initiative_order=data["initiative_order"],
            current_turn_index=data["current_turn_index"],
            round_number=data["round_number"],
        )

    @staticmethod
    def from_json(json_str: str) -> "GameState":
        return GameState.from_dict(json.loads(json_str))

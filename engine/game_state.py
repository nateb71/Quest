import json
 
 
class Weapon:
    def __init__(self, name, weapon_type, damage):
        self.name = name
        self.weapon_type = weapon_type
        self.damage = damage
 
    def to_dict(self):
        return {
            "name": self.name,
            "weapon_type": self.weapon_type,
            "damage": self.damage,
        }
 
    @staticmethod
    def from_dict(data):
        return Weapon(
            name=data["name"],
            weapon_type=data["weapon_type"],
            damage=data["damage"],
        )
 
 
class Stats:
    def __init__(self, str, dex, int):
        self.str = str
        self.dex = dex
        self.int = int
 
    def to_dict(self):
        return {
            "str": self.str,
            "dex": self.dex,
            "int": self.int,
        }
 
    @staticmethod
    def from_dict(data):
        return Stats(
            str=data["str"],
            dex=data["dex"],
            int=data["int"],
        )
 
 
class Entity:
    def __init__(self, id, type, role, level, hp, max_hp, mp, max_mp, stats, weapon, items):
        self.id = id
        self.type = type
        self.role = role
        self.level = level
        self.hp = hp
        self.max_hp = max_hp
        self.mp = mp
        self.max_mp = max_mp
        self.stats = stats
        self.weapon = weapon
        self.items = items
 
    def is_alive(self):
        return self.hp > 0
 
    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "level": self.level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_hp,
            "stats": self.stats.to_dict(),
            "weapon": self.weapon.to_dict(),
            "items": self.items,
        }
 
    @staticmethod
    def from_dict(data):
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
 
 
class AdventureState:
    def __init__(self, title, current_chapter, boss_name, boss_defeated, story_flags):
        self.title = title
        self.current_chapter = current_chapter
        self.boss_name = boss_name
        self.boss_defeated = boss_defeated
        self.story_flags = story_flags
 
    def to_dict(self):
        return {
            "title": self.title,
            "current_chapter": self.current_chapter,
            "boss_name": self.boss_name,
            "boss_defeated": self.boss_defeated,
            "story_flags": self.story_flags,
        }
 
    @staticmethod
    def from_dict(data):
        return AdventureState(
            title=data["title"],
            current_chapter=data["current_chapter"],
            boss_name=data["boss_name"],
            boss_defeated=data["boss_defeated"],
            story_flags=data["story_flags"],
        )
 
 
class SceneState:
    def __init__(self, description_seed, active_entity_ids):
        self.description_seed = description_seed
        self.active_entity_ids = active_entity_ids
 
    def to_dict(self):
        return {
            "description_seed": self.description_seed,
            "active_entity_ids": self.active_entity_ids,
        }
 
    @staticmethod
    def from_dict(data):
        return SceneState(
            description_seed=data["description_seed"],
            active_entity_ids=data["active_entity_ids"],
        )
 
 
class Action:
    def __init__(self, actor_id, action_type, target_id, action_name, mp_cost=None):
        self.actor_id = actor_id
        self.action_type = action_type
        self.target_id = target_id
        self.action_name = action_name
        self.mp_cost = mp_cost
 
 
class GameState:
    def __init__(self, adventure, scene, entities, in_combat=False,
                 initiative_order=None, current_turn_index=0, round_number=0):
        self.adventure = adventure
        self.scene = scene
        self.entities = entities
        self.in_combat = in_combat
        self.initiative_order = initiative_order if initiative_order is not None else []
        self.current_turn_index = current_turn_index
        self.round_number = round_number
 
    def get_entity(self, entity_id):
        return self.entities.get(entity_id)
 
    def get_active_entities(self):
        return [
            self.entities[eid]
            for eid in self.scene.active_entity_ids
            if eid in self.entities
        ]
 
    def to_dict(self):
        return {
            "adventure": self.adventure.to_dict(),
            "scene": self.scene.to_dict(),
            "entities": {eid: entity.to_dict() for eid, entity in self.entities.items()},
            "in_combat": self.in_combat,
            "initiative_order": self.initiative_order,
            "current_turn_index": self.current_turn_index,
            "round_number": self.round_number,
        }
 
    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)
 
    @staticmethod
    def from_dict(data):
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
    def from_json(json_str):
        return GameState.from_dict(json.loads(json_str))
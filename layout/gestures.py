from dataclasses import dataclass


class RuleConflict(ValueError):
    def __init__(self, position: str, message: str):
        super().__init__(message)
        self.position = position


def rule_key(language: str, region_a: str, region_b: str) -> tuple[str, str, str]:
    first, second = sorted((region_a, region_b))
    return language, first, second


@dataclass(frozen=True)
class GestureRule:
    rule_id: str
    name: str
    regions: tuple[str, str]
    language: str
    clip_id: int
    wait: int

    @classmethod
    def from_document(cls, item: dict) -> 'GestureRule':
        return cls(**(item | {'regions': tuple(item['regions'])}))


def validate_rules(data: object, region_ids: set[str]) -> tuple[GestureRule, ...]:
    if not isinstance(data, list):
        raise RuleConflict('rules', 'rules must be an array')

    rules = []
    ids = set()
    used_pairs = {}
    allowed = {'rule_id', 'name', 'regions', 'language', 'clip_id', 'wait'}
    for index, item in enumerate(data):
        position = f'rules[{index}]'
        if not isinstance(item, dict) or item.keys() - allowed:
            raise RuleConflict(position, 'invalid rule object')
        rule_id = item.get('rule_id')
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise RuleConflict(f'{position}.rule_id', 'rule_id must be a nonblank string')
        if rule_id in ids:
            raise RuleConflict(f'{position}.rule_id', f'duplicate rule {rule_id}')
        name = item.get('name', rule_id)
        language = item.get('language')
        for field, value in (('name', name), ('language', language)):
            if not isinstance(value, str) or not value.strip():
                raise RuleConflict(f'{position}.{field}', f'{field} must be a nonblank string')

        pair = item.get('regions')
        if not isinstance(pair, list) or len(pair) != 2:
            raise RuleConflict(f'{position}.regions', 'expected two region IDs')
        for endpoint, region_id in enumerate(pair):
            if not isinstance(region_id, str) or region_id not in region_ids:
                raise RuleConflict(f'{position}.regions[{endpoint}]', 'unknown region')
        if pair[0] == pair[1]:
            raise RuleConflict(f'{position}.regions', 'rule endpoints must differ')
        key = rule_key(language, *pair)
        if key in used_pairs:
            raise RuleConflict(f'{position}.regions', f'pair already used by {used_pairs[key]}')

        clip_id = item.get('clip_id')
        if type(clip_id) is not int or not 0 < clip_id < 2**63:
            raise RuleConflict(f'{position}.clip_id', 'expected a positive clip ID')
        wait = item.get('wait')
        if type(wait) is not int or wait < 0:
            raise RuleConflict(f'{position}.wait', 'wait must be a nonnegative integer')
        ids.add(rule_id)
        used_pairs[key] = rule_id
        rules.append(GestureRule(rule_id, name, (key[1], key[2]), language, clip_id, wait))
    return tuple(rules)

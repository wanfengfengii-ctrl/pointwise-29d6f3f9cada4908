from dataclasses import dataclass


class RegionConflict(ValueError):
    def __init__(self, position: str, message: str):
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class Region:
    region_id: str
    name: str
    x0: int
    y0: int
    x1: int
    y1: int

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1

    def overlaps(self, other: 'Region') -> bool:
        return (
            max(self.x0, other.x0) < min(self.x1, other.x1)
            and max(self.y0, other.y0) < min(self.y1, other.y1)
        )


def validate_regions(data: object) -> tuple[Region, ...]:
    if not isinstance(data, list):
        raise RegionConflict('regions', 'regions must be an array')

    regions = []
    ids = set()
    boundaries = ('x0', 'y0', 'x1', 'y1')
    allowed = {'region_id', 'name', *boundaries}
    for index, item in enumerate(data):
        position = f'regions[{index}]'
        if not isinstance(item, dict) or item.keys() - allowed:
            raise RegionConflict(position, 'invalid region object')
        region_id = item.get('region_id')
        if not isinstance(region_id, str) or not region_id.strip():
            raise RegionConflict(f'{position}.region_id', 'region_id must be a nonblank string')
        if region_id in ids:
            raise RegionConflict(f'{position}.region_id', f'duplicate region {region_id}')
        name = item.get('name', region_id)
        if not isinstance(name, str) or not name.strip():
            raise RegionConflict(f'{position}.name', 'name must be a nonblank string')
        for field in boundaries:
            if type(item.get(field)) is not int:
                raise RegionConflict(f'{position}.{field}', 'boundary must be an integer')
        region = Region(region_id, name, **{field: item[field] for field in boundaries})
        if region.x0 >= region.x1 or region.y0 >= region.y1:
            raise RegionConflict(position, 'both rectangle intervals must have positive length')
        for previous in regions:
            if region.overlaps(previous):
                raise RegionConflict(position, f'region {region_id} overlaps {previous.region_id}')
        ids.add(region_id)
        regions.append(region)
    return tuple(regions)

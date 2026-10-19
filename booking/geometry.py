"""Геометрия плана: многоугольники хранятся как [[x, y], ...] в клетках сетки."""
from django.core.exceptions import ValidationError


def points_are_valid(points):
    try:
        validate_points(points)
    except ValidationError:
        return False
    return True


def validate_points(points):
    """Список из >= 3 вершин [x, y] с целыми неотрицательными координатами и ненулевой площадью."""
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise ValidationError('Нужно минимум 3 вершины в формате [[x, y], ...].')
    for p in points:
        if (
            not isinstance(p, (list, tuple)) or len(p) != 2
            or any(isinstance(c, bool) or not isinstance(c, int) or c < 0 for c in p)
        ):
            raise ValidationError(
                'Каждая вершина — пара целых неотрицательных чисел [x, y].'
            )
    if polygon_area(points) == 0:
        raise ValidationError('Многоугольник имеет нулевую площадь.')


def polygon_area(points):
    """Площадь по формуле Гаусса (в клетках²)."""
    s = 0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def bounding_box(points):
    """(min_x, min_y, max_x, max_y)."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def point_in_polygon(x, y, points):
    """Точка внутри многоугольника или на его границе (метод луча)."""
    n = len(points)
    inside = False
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        # точка на ребре
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            cross == 0
            and min(x1, x2) <= x <= max(x1, x2)
            and min(y1, y2) <= y <= max(y1, y2)
        ):
            return True
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside
import h3

from api.models import FirmsDetection


RAW_PRODUCTS = {
    ("MODIS_SP", "Aqua"): "aqua",
    ("VIIRS_SNPP_SP", "N"): "snpp",
}


def parent_is_inside_bounds(parent, bounds):
    south, north, west, east = bounds
    return all(
        south <= latitude <= north and west <= longitude <= east
        for latitude, longitude in h3.cell_to_boundary(parent)
    )


def raw_detection_counts(start_at, end_at, bounds):
    south, north, west, east = bounds
    queryset = FirmsDetection.objects.filter(
        acquired_at__gte=start_at,
        acquired_at__lt=end_at,
        source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
    ).filter(
        latitude__gte=south,
        latitude__lte=north,
        longitude__gte=west,
        longitude__lte=east,
    )
    counts = {"aqua": 0, "snpp": 0}
    for row in queryset.values_list("source", "attributes", "grid_cell").iterator(
        chunk_size=2000
    ):
        key = (row[0], (row[1] or {}).get("satellite"))
        metric = RAW_PRODUCTS.get(key)
        if metric is not None:
            counts[metric] += 1
    return counts

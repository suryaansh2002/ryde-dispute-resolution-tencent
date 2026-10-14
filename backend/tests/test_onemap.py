"""OneMap's routing response: the polyline is top-level `route_geometry`; `route_summary`
only carries distances and times. Reading it from the wrong place silently fell back to a
synthetic straight line for every trip."""

from data_generation.pipeline.onemap import _decode_onemap_geometry


def test_decodes_the_top_level_polyline_even_with_a_route_summary():
    # "_p~iF~ps|U_ulLnnqC_mqNvxq`@" is the reference polyline from Google's docs.
    data = {
        "route_geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
        "route_summary": {"total_distance": 9112, "total_time": 1095},
    }
    assert _decode_onemap_geometry(data) == [
        [-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252],
    ]

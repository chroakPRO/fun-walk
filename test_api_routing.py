import unittest
import sys
import types

import networkx as nx

# The route-quality unit tests use synthetic graphs and do not need the real
# OSMnx package. Some local environments have osmnx installed without its
# numeric stack, so stub the tiny surface api.py needs during import.
sys.modules.setdefault(
    'osmnx',
    types.SimpleNamespace(
        distance=types.SimpleNamespace(nearest_nodes=lambda *args, **kwargs: None),
        graph_from_point=lambda *args, **kwargs: None,
    ),
)

import api  # noqa: E402


def add_bidirectional_edge(graph, u, v, length, **attrs):
    edge_attrs = {'length': length, **attrs}
    graph.add_edge(u, v, **edge_attrs)
    graph.add_edge(v, u, **edge_attrs.copy())


def build_fixture_graph():
    graph = nx.MultiDiGraph()
    coordinates = {
        1: (0.0, 0.0),
        2: (1.0, 0.0),
        3: (2.0, 0.0),
        4: (0.5, 0.5),
        5: (1.5, 0.5),
        6: (0.5, 1.0),
        7: (1.5, 1.0),
        8: (1.0, -0.4),
    }
    for node_id, (x, y) in coordinates.items():
        graph.add_node(node_id, x=x, y=y)

    # Shortest route: 200m residential street.
    add_bidirectional_edge(graph, 1, 2, 100, highway='residential', surface='asphalt')
    add_bidirectional_edge(graph, 2, 3, 100, highway='residential', surface='asphalt')

    # Fun route: 270m through park/wood tags, inside the 45% detour cap.
    add_bidirectional_edge(graph, 1, 4, 90, highway='footway', surface='gravel', leisure='park')
    add_bidirectional_edge(graph, 4, 5, 90, highway='path', surface='ground', natural='wood')
    add_bidirectional_edge(graph, 5, 3, 90, highway='footway', surface='gravel')

    # Very scenic but too long: should be rejected by the detour cap.
    add_bidirectional_edge(graph, 1, 6, 120, highway='footway', surface='gravel', tourism='viewpoint')
    add_bidirectional_edge(graph, 6, 7, 120, highway='footway', surface='gravel', leisure='nature_reserve')
    add_bidirectional_edge(graph, 7, 3, 120, highway='footway', surface='gravel', natural='wood')

    # Mild alternative for balanced-route tests.
    add_bidirectional_edge(graph, 1, 8, 115, highway='service', surface='asphalt')
    add_bidirectional_edge(graph, 8, 3, 115, highway='service', surface='asphalt')
    return graph


class ApiRoutingTests(unittest.TestCase):
    def test_nearest_node_does_not_require_optional_osmnx_dependencies(self):
        graph = nx.MultiDiGraph()
        graph.add_node('far', x=11.0, y=57.0)
        graph.add_node('near', x=11.95, y=57.69)

        nearest = api._nearest_graph_node(
            graph,
            api.Coordinate(lat=57.6901, lng=11.9501),
        )
        self.assertEqual(nearest, 'near')

    def test_nearby_context_changes_edge_scenery_without_faking_direct_tags(self):
        edge = {
            'highway': 'footway',
            'context_scenery': {'park': 0.12, 'water': 0.08},
        }

        self.assertEqual(api._edge_scenery_tags(edge), {'park', 'water'})
        self.assertGreater(api._edge_scenery_score(edge), 0.12)
        self.assertLess(api._edge_scenery_score(edge), 0.22 + 0.18)

    def test_fast_road_without_sidewalk_is_strongly_penalized(self):
        quiet = {'highway': 'residential', 'surface': 'asphalt', 'sidewalk': 'both'}
        exposed = {
            'highway': 'primary',
            'surface': 'asphalt',
            'sidewalk': 'no',
            'maxspeed': '70',
            'lanes': '4',
        }

        self.assertGreater(api._edge_fun_factor(exposed), api._edge_fun_factor(quiet) * 2)

    def test_scenic_anchor_search_finds_fun_detour_missed_by_weighted_shortest_path(self):
        graph = nx.MultiDiGraph()
        for node_id, x, y in [(1, 0, 0), (2, 1, 0), (3, 2, 0), (4, 1, 0.0015)]:
            graph.add_node(node_id, x=x, y=y)

        add_bidirectional_edge(graph, 1, 2, 100, highway='residential', surface='asphalt')
        add_bidirectional_edge(graph, 2, 3, 100, highway='residential', surface='asphalt')
        add_bidirectional_edge(graph, 1, 4, 130, highway='residential', surface='asphalt')
        add_bidirectional_edge(
            graph,
            4,
            3,
            130,
            highway='residential',
            surface='asphalt',
            context_scenery={'park': 0.20},
        )
        api.annotate_fun_weights(graph)

        self.assertEqual(nx.shortest_path(graph, 1, 3, weight='fun_weight'), [1, 2, 3])
        candidates = api._generate_route_candidates(
            graph,
            1,
            3,
            direct_distance=200,
            max_distance=290,
            base_weights=['fun_weight'],
        )
        self.assertIn([1, 4, 3], [route for route, _ in candidates])

        best = api._best_capped_route(
            graph,
            1,
            3,
            [],
            290,
            direct_distance=200,
            route_candidates=candidates,
        )
        self.assertEqual(best['route'], [1, 4, 3])

    def test_park_anchors_require_real_nature_context(self):
        graph = nx.MultiDiGraph()
        for node_id in [1, 2, 3]:
            graph.add_node(node_id, x=float(node_id), y=0.0)
        add_bidirectional_edge(graph, 1, 2, 100, highway='footway', surface='gravel')
        add_bidirectional_edge(graph, 2, 3, 100, highway='footway', surface='gravel')
        api.annotate_fun_weights(graph)

        anchors = api._find_scenic_anchor_nodes(
            graph,
            1,
            3,
            direct_distance=200,
            max_distance=300,
            required_tags={'park', 'forest', 'water'},
        )
        self.assertEqual(anchors, [])

    def test_generic_path_is_not_blanket_penalized_below_residential(self):
        graph = nx.MultiDiGraph()
        for node_id in [1, 2, 3, 4]:
            graph.add_node(node_id, x=float(node_id), y=0.0)
        add_bidirectional_edge(graph, 1, 2, 100, highway='path')
        add_bidirectional_edge(graph, 3, 4, 100, highway='residential', surface='asphalt')

        api.annotate_fun_weights(graph)

        path_weight = graph.get_edge_data(1, 2)[0]['fun_weight']
        residential_weight = graph.get_edge_data(3, 4)[0]['fun_weight']
        self.assertLess(path_weight, residential_weight)

    def test_route_stats_use_actual_surface_tags(self):
        graph = nx.MultiDiGraph()
        for node_id in [1, 2, 3]:
            graph.add_node(node_id, x=float(node_id), y=0.0)
        add_bidirectional_edge(graph, 1, 2, 80, highway='footway', surface='grass')
        add_bidirectional_edge(graph, 2, 3, 120, highway='residential', surface='asphalt')

        api.annotate_fun_weights(graph)
        stats = api.calculate_detailed_route_stats(graph, [1, 2, 3])

        self.assertEqual(stats['distance'], 200)
        self.assertEqual(stats['surface_types']['grass']['distance'], 80)
        self.assertEqual(stats['surface_types']['paved']['distance'], 120)
        self.assertEqual(stats['surface_types']['unpaved']['distance'], 0)
        self.assertEqual(len(stats['segments']), 2)
        self.assertEqual(stats['segments'][0]['surface_type'], 'grass')

    def test_overlap_ratio_is_length_based(self):
        graph = build_fixture_graph()
        api.annotate_fun_weights(graph)

        self.assertEqual(api._route_overlap_ratio(graph, [1, 2, 3], [[1, 4, 5, 3]]), 0)
        self.assertEqual(api._route_overlap_ratio(graph, [1, 2, 3], [[1, 2, 3]]), 1)

    def test_compute_routes_rejects_uncapped_scenic_detour(self):
        graph = build_fixture_graph()
        original_fetch_graph = api.fetch_graph

        try:
            api.fetch_graph = lambda start, end, buffer_dist=5000, route_type='all': graph

            routes = api.compute_multiple_routes(
                api.Coordinate(lat=0.0, lng=0.0),
                api.Coordinate(lat=0.0, lng=2.0),
            )
        finally:
            api.fetch_graph = original_fetch_graph

        by_name = {route['name']: route for route in routes}
        self.assertIn('SHORTEST', by_name)
        self.assertIn('MOST_FUN', by_name)
        self.assertEqual(by_name['SHORTEST']['stats']['distance'], 200)
        self.assertLessEqual(
            by_name['MOST_FUN']['stats']['distance'],
            by_name['SHORTEST']['stats']['distance'] * api.FUN_ROUTE_MAX_DETOUR,
        )
        self.assertNotEqual(by_name['MOST_FUN']['stats']['distance'], 360)

    def test_fastest_mode_returns_only_the_shortest_route(self):
        graph = build_fixture_graph()
        original_fetch_graph = api.fetch_graph
        try:
            api.fetch_graph = lambda start, end, buffer_dist=5000, route_type='all': graph
            routes = api.compute_multiple_routes(
                api.Coordinate(lat=0.0, lng=0.0),
                api.Coordinate(lat=0.0, lng=2.0),
                route_type='fastest',
            )
        finally:
            api.fetch_graph = original_fetch_graph

        self.assertEqual([route['name'] for route in routes], ['SHORTEST'])
        self.assertEqual(routes[0]['stats']['distance'], 200)

    def test_shopping_mode_prefers_retail_context_and_returns_one_route(self):
        graph = nx.MultiDiGraph()
        for node_id, x, y in [(1, 0, 0), (2, 1, 0), (3, 2, 0), (4, 1, 0.0015)]:
            graph.add_node(node_id, x=x, y=y)
        add_bidirectional_edge(graph, 1, 2, 100, highway='residential', surface='asphalt')
        add_bidirectional_edge(graph, 2, 3, 100, highway='residential', surface='asphalt')
        add_bidirectional_edge(
            graph, 1, 4, 130, highway='pedestrian', surface='paved',
            context_scenery={'shopping': 0.28, 'food': 0.12},
        )
        add_bidirectional_edge(
            graph, 4, 3, 130, highway='pedestrian', surface='paved',
            context_scenery={'shopping': 0.28, 'food': 0.12},
        )

        original_fetch_graph = api.fetch_graph
        try:
            api.fetch_graph = lambda start, end, buffer_dist=5000, route_type='all': graph
            routes = api.compute_multiple_routes(
                api.Coordinate(lat=0.0, lng=0.0),
                api.Coordinate(lat=0.0, lng=2.0),
                route_type='shopping',
            )
        finally:
            api.fetch_graph = original_fetch_graph

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]['name'], 'SHOPPING')
        self.assertEqual(routes[0]['stats']['distance'], 260)
        self.assertIn('shopping', routes[0]['stats']['special_areas'])


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Layout is geometry the page depends on: dependencies read top to bottom,
boxes never overlap, edges leave and enter the faces that point along them,
lane bands wrap at a fixed width, and malformed graphs still terminate."""
from __future__ import annotations

import unittest

from executor.graph_layout import COL_GAP, MARGIN, NODE_H, NODE_W, layered_dag, lane_layout


class LayeredDag(unittest.TestCase):
    def test_a_dependency_sits_on_a_lower_row(self):
        laid = layered_dag(["a", "b", "c"], [("a", "b"), ("b", "c")])
        ys = [laid["nodes"][n]["y"] for n in "abc"]
        self.assertLess(ys[0], ys[1])
        self.assertLess(ys[1], ys[2])

    def test_the_longest_chain_decides_the_row(self):
        laid = layered_dag(["a", "b", "d"], [("a", "d"), ("a", "b"), ("b", "d")])
        self.assertEqual(laid["nodes"]["d"]["group"], 2)

    def test_no_two_boxes_overlap(self):
        ids = [f"t{i:02d}" for i in range(13)]
        edges = [(ids[i], ids[j]) for i in range(13) for j in range(i + 1, 13)
                 if (i * 7 + j) % 4 == 0]
        laid = layered_dag(ids, edges)
        boxes = [(laid["nodes"][n]["x"], laid["nodes"][n]["y"]) for n in ids]
        for i, (x1, y1) in enumerate(boxes):
            for x2, y2 in boxes[i + 1:]:
                self.assertFalse(abs(x1 - x2) < NODE_W and abs(y1 - y2) < NODE_H)

    def test_a_short_row_is_centred_under_the_widest_row(self):
        laid = layered_dag(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d")])
        centred = MARGIN + (2 * NODE_W + COL_GAP - NODE_W) // 2
        self.assertEqual(laid["nodes"]["a"]["x"], centred)
        self.assertEqual(laid["nodes"]["d"]["x"], centred)

    def test_crossings_are_reduced_by_barycentre_ordering(self):
        # s1 feeds t2 and s2 feeds t1. Uncrossed means t2 sits left of t1.
        laid = layered_dag(["s1", "s2", "t1", "t2"], [("s1", "t2"), ("s2", "t1")])
        self.assertLess(laid["nodes"]["t2"]["x"], laid["nodes"]["t1"]["x"])

    def test_an_edge_leaves_the_source_bottom_and_enters_the_target_top(self):
        laid = layered_dag(["a", "b"], [("a", "b")])
        a, b = laid["nodes"]["a"], laid["nodes"]["b"]
        (edge,) = laid["edges"]
        self.assertTrue(edge["d"].startswith(f"M{a['x'] + NODE_W // 2} {a['y'] + NODE_H} "))
        self.assertTrue(edge["d"].endswith(f" {b['x'] + NODE_W // 2} {b['y']}"))

    def test_the_same_graph_in_any_input_order_gives_the_same_geometry(self):
        ids, edges = ["x", "y", "z"], [("x", "z"), ("y", "z")]
        self.assertEqual(layered_dag(ids, edges),
                         layered_dag(list(reversed(ids)), list(reversed(edges))))

    def test_a_cycle_terminates_and_places_every_node(self):
        laid = layered_dag(["a", "b"], [("a", "b"), ("b", "a")])
        self.assertEqual(set(laid["nodes"]), {"a", "b"})

    def test_an_edge_to_an_unknown_node_is_dropped(self):
        laid = layered_dag(["a"], [("a", "ghost"), ("ghost", "a")])
        self.assertEqual(laid["edges"], [])

    def test_an_empty_graph_is_a_margin_only_canvas(self):
        laid = layered_dag([], [])
        self.assertEqual(laid["nodes"], {})
        self.assertGreater(laid["width"], 0)
        self.assertGreater(laid["height"], 0)


class LaneLayout(unittest.TestCase):
    def test_lanes_follow_the_entity_order_and_unknown_lanes_come_last(self):
        laid = lane_layout({"i": "initiative", "t": "task", "a": "artifact", "x": "weird"}, {}, [])
        self.assertEqual([lane["name"] for lane in laid["lanes"]],
                         ["initiative", "task", "artifact", "weird"])

    def test_each_lane_band_is_labelled_below_the_one_before_it(self):
        laid = lane_layout({"i": "initiative", "t": "task"}, {}, [])
        first, second = laid["lanes"]
        self.assertLess(first["y"], second["y"])
        self.assertEqual(first["x"], MARGIN)

    def test_members_of_one_lane_share_a_row_until_it_is_full(self):
        laid = lane_layout({"t1": "task", "t2": "task", "a": "artifact"}, {}, [])
        self.assertEqual(laid["nodes"]["t1"]["y"], laid["nodes"]["t2"]["y"])
        self.assertNotEqual(laid["nodes"]["t1"]["y"], laid["nodes"]["a"]["y"])

    def test_a_lane_wraps_into_a_new_row_after_its_row_width(self):
        members = {f"a{i}": "artifact" for i in range(6)}
        laid = lane_layout(members, {}, [])
        self.assertEqual(len({laid["nodes"][n]["y"] for n in members}), 2)

    def test_the_sort_key_orders_a_lane_before_the_id(self):
        laid = lane_layout({"b": "artifact", "a": "artifact"}, {"a": ("z",), "b": ("a",)}, [])
        self.assertLess(laid["nodes"]["b"]["x"], laid["nodes"]["a"]["x"])

    def test_a_downward_edge_keeps_its_kind(self):
        laid = lane_layout({"t": "task", "a": "artifact"}, {}, [("t", "a", "cites")])
        (edge,) = laid["edges"]
        self.assertEqual(edge["kind"], "cites")

    def test_a_citation_from_a_lower_band_bows_outward_from_the_right_face(self):
        laid = lane_layout({"t": "task", "a": "artifact"}, {}, [("a", "t", "cites")])
        (edge,) = laid["edges"]
        source = laid["nodes"]["a"]
        self.assertTrue(edge["d"].startswith(f"M{source['x'] + NODE_W} {source['y'] + NODE_H // 2} "))


if __name__ == "__main__":
    unittest.main()

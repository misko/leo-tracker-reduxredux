import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_parent_extras import parent_rows, replay


class ParentViewTests(unittest.TestCase):
    def test_parent_view_retains_gap_separated_ids_without_claiming_contiguous_duration(self):
        track=dict(observation_ids=["a","b","c"],times=[0,2,12],pieces=[{}])
        fragments=[dict(case="S",track_index=i,observation_ids=["a"]) for i in range(10)]
        fragments.append(dict(case="S",track_index=10,observation_ids=["a"]))
        parent=dict(case="S",track_index=10,parent_rank=2,track_id="parent",remaining_observation_ids=["a","c"],points=2,duration_s=12,max_gap_s=12,contiguous_fragments=2,longest_native_fragment_duration_s=0)
        inventory=dict(tracks=fragments,parent_tracks=[parent])
        rows=parent_rows(inventory,{"S":dict(tracks=[track]*11)})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["observation_ids"],["a","c"])
        self.assertEqual(rows[0]["duration_s"],12)
        self.assertEqual(rows[0]["longest_native_fragment_duration_s"],0)
        self.assertTrue(rows[0]["parent_view"])
        parent["track_index"]=0
        self.assertEqual(parent_rows(inventory,{"S":dict(tracks=[track]*11)}),[])

    def test_standalone_packet_restores_owner_ids_and_parent_metadata(self):
        packet=dict(schema="ds27-parent-extra-plot-packet/v1",native=dict(top10=[dict(parent_view=True)],cases=dict(S=dict(tracks=[],observations=[],associated_ids=["a"]))),diagnostic=dict(tracks=[]))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"packet.gz";path.write_bytes(gzip.compress(json.dumps(packet).encode(),mtime=0))
            with patch("audit_parent_extras.render") as render:
                replay(path,Path(d)/"output")
            self.assertEqual(render.call_args.args[2]["S"]["associated"],{"a"})
            self.assertTrue(render.call_args.args[1][0]["parent_view"])


if __name__=="__main__":unittest.main()

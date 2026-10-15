# -*- coding: utf-8 -*-
import unittest
from dataclasses import replace
from eod_decision_gate import EODEvidence,decide_eod_retirement,GATES

def complete():
    return EODEvidence(True,True,True,True,True,True,0,True,True)

class TestEODDecision(unittest.TestCase):
    def test_all_evidence_passes(self):
        self.assertTrue(decide_eod_retirement(complete())["retire"])
    def test_every_individual_gate_blocks(self):
        for name in GATES:
            with self.subTest(name=name):
                result=decide_eod_retirement(replace(complete(),**{name:False}))
                self.assertFalse(result["retire"])
                self.assertIn(name,result["hold_reasons"])
    def test_missing_authority_blocks_even_if_bars_match(self):
        e=replace(complete(),rest_final_authoritative=False)
        self.assertFalse(decide_eod_retirement(e)["retire"])
    def test_pending_line_blocks(self):
        e=replace(complete(),pending_line_count=1)
        self.assertEqual(decide_eod_retirement(e)["hold_reasons"],["pending_line_count"])
    def test_unknown_line_count_blocks(self):
        e=replace(complete(),pending_line_count=-1)
        self.assertFalse(decide_eod_retirement(e)["retire"])
    def test_boolean_line_count_blocks(self):
        e=replace(complete(),pending_line_count=False)
        self.assertFalse(decide_eod_retirement(e)["retire"])
    def test_missing_gate_blocks(self):
        e=replace(complete(),worker_exited=None)
        self.assertFalse(decide_eod_retirement(e)["retire"])
    def test_invalid_input_rejected(self):
        with self.assertRaises(TypeError):decide_eod_retirement({})
if __name__=="__main__":unittest.main(verbosity=2)

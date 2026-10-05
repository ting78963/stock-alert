# -*- coding: utf-8 -*-
"""F15 v2 compatibility fix for LINE Flex text argument validation.
Keeps F15 v1 data/archive/send semantics unchanged; only normalizes a legacy
positional align/flex call before Flex JSON is built.
"""
import f15_eod_signal_report as _m

_v1_text=_m.text

def _text_fixed(t,size="xs",color=_m.C_TEXT,weight=None,align=None,flex=None,wrap=False):
    # v1 footer used text(..., "end", 1) positionally; normalize that to
    # align="end", flex=1 rather than the invalid weight="end".
    if weight in {"start","center","end"} and isinstance(align,(int,float)) and flex is None:
        flex=align;align=weight;weight=None
    return _v1_text(t,size,color,weight,align,flex,wrap)

_m.text=_text_fixed
loop=_m.loop
process_day=_m.process_day
build_report=_m.build_report
build_flex=_m.build_flex

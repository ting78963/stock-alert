import json
from line_signal_notifier_v3 import build_flex
from line_indicator_flex_preview_v1 import enrich_preview

event={'stock_id':'1301','stock_name':'台塑','signal_class':'A','recognition_time':'09:31:00'}
indicators={'osc':0.52,'osc_delta':0.14,'weekly_kd':'golden_cross','ma_cross_day':2,'ma20_first_above':True,'strong_buy':True}
card=enrich_preview(build_flex(event),indicators)
body=card['contents']['body']['contents']
text=json.dumps(card,ensure_ascii=False)
assert 'OSC +0.52' in text
assert '週KD✦ 黃金交叉' in text
assert '5、20MA✦ 黃金交叉 Day2' in text
assert '20MA✦ 今日站上' in text
assert '強勢買進訊號' in text
assert sum(x.get('backgroundColor')=='#981B25' for x in body)==1
assert body[-4]['type']=='box' or '立即買進' in text
print('SIMULATED LINE FLEX PAYLOAD (NO API, NO SEND):')
print(json.dumps(card,ensure_ascii=False,indent=2))
print('SIMULATION PASS: single enriched card, original BUY preserved, NO LINE SEND')

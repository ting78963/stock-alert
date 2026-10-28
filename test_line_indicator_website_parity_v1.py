"""Cross-language parity test against pinned original website JavaScript.

Read pinned original website JavaScript from repository during CI. Run extracted original
functions in Node, compare against Python on deterministic historical-like fixtures.
No API keys, DB, LINE, or production state involved.
"""
import json, subprocess, unittest
from pathlib import Path
from datetime import date,timedelta
from line_indicator_calculations_v1 import macd,ma_cross_day,ma_prepare,weekly_kd_label,kd

SOURCE=Path(__file__).parent / "research" / "website_indicator_functions_pinned_v1.js"
NAMES=["calcKD","calcMACD","calcMA5MA20CrossLabel","calcMA5MA20Prepare","calcWeeklyKDLabel"]

def extract(src,name):
    start=src.index("function "+name+"(")
    brace=src.index("{",start)
    depth=0
    for i in range(brace,len(src)):
        if src[i]=="{":depth+=1
        elif src[i]=="}":
            depth-=1
            if depth==0:return src[start:i+1]
    raise ValueError("unclosed function "+name)

def fixture(n,variant):
    d=date(2025,10,6);out=[]
    for i in range(n):
        while d.weekday()>4:d+=timedelta(days=1)
        c=round(60+(i*.12 if variant==0 else (-i*.14 if variant==1 else ((i%17)-8)*.7))+((i*7)%11-5)*.18,3)
        out.append({"date":d.isoformat(),"high":c+1.7,"low":c-1.4,"close":c})
        d+=timedelta(days=1)
    return out

class WebsiteParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=SOURCE.read_text(encoding="utf-8")
        cls.js="\n".join(extract(source,n) for n in NAMES)

    def test_original_js_python_parity(self):
        fixtures=[fixture(n,v) for n in (20,35,50,80,125) for v in range(3)]
        js=self.js+"""
const fs=require('fs');
const samples=JSON.parse(fs.readFileSync(0,'utf8'));
const result=samples.map(rows=>({
  macd:calcMACD(rows.map(r=>r.close)),
  maCross:calcMA5MA20CrossLabel(rows),
  maPrepare:calcMA5MA20Prepare(rows),
  weeklyKD:calcWeeklyKDLabel(rows),
  kd:calcKD(rows)
}));
process.stdout.write(JSON.stringify(result));
"""
        p=subprocess.run(["node","-e",js],input=json.dumps(fixtures),text=True,capture_output=True,check=True)
        results=json.loads(p.stdout)
        self.assertEqual(len(results), len(fixtures))
        for i,(rows,actual) in enumerate(zip(fixtures,results)):
            with self.subTest(case=i):
                py=macd([r["close"] for r in rows])
                for field in ("dif","sig","hist","prev_hist","histArr","histArr5"):
                    self.assertEqual(py[field],actual["macd"].get(field),field)
                self.assertEqual(ma_cross_day(rows),actual["maCross"])
                self.assertEqual(ma_prepare(rows),actual["maPrepare"])
                self.assertEqual(weekly_kd_label(rows),actual["weeklyKD"])
                self.assertEqual(kd(rows),actual["kd"]["hist"])

if __name__=="__main__":unittest.main()

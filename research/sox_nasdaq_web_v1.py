"""Parse Nasdaq SOX overview HTML without adding dependencies or network calls."""
import re
from datetime import datetime
from html.parser import HTMLParser

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self,data):
        value=' '.join(data.split())
        if value: self.parts.append(value)

def parse_nasdaq_sox_html(html):
    parser=_Text(); parser.feed(html)
    text=' '.join(parser.parts)
    pattern=r'DATA\s+AS\s+OF\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+\.\d{2})\s+([+-]?[\d,]+\.\d{2})\s+([+-]?[\d,]+\.\d{2})\s*%'
    match=re.search(pattern,text,re.I)
    if not match: raise ValueError('SOX dated overview quote not found')
    date,price,change,pct=match.groups()
    parsed=datetime.strptime(date,'%m/%d/%Y').date().isoformat()
    result={'date':parsed,'close':float(price.replace(',','')),'change':float(change.replace(',','')),'change_pct':float(pct.replace(',','')),'source':'nasdaq_sox_overview'}
    previous=result['close']-result['change']
    if result['close']<=0 or previous<=0 or abs(result['change']/previous*100-result['change_pct'])>0.05:
        raise ValueError('SOX inconsistent quote')
    return result

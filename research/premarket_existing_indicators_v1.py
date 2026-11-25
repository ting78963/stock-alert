"""Read-only existing TAIEX and USD/TWD history for the 08:55 report."""
from datetime import date,timedelta
from taiex_fugle_store_v1 import read_store as read_taiex
from usdtwd_cbc_store_v1 import read_store as read_fx
from taiex_market_history_v1 import snapshot as taiex_snapshot
from usdtwd_cbc_daily_v1 import trend_snapshot as fx_snapshot


def read_premarket_indicators(report_day, taiex_reader=read_taiex, fx_reader=read_fx):
    day=date.fromisoformat(str(report_day)[:10]).isoformat()
    def safe(reader, calculator):
        try:
            rows=reader()
            result=calculator(rows,day)
            previous=result.get('last_close_date')
            if previous:
                result['previous']=calculator(rows,previous)
            if calculator is taiex_snapshot:
                result['previous_week']=calculator(rows,(date.fromisoformat(day)-timedelta(weeks=1)).isoformat())
            return result
        except (OSError,ValueError,KeyError,TypeError,IndexError):
            return None
    return {"taiex":safe(taiex_reader,taiex_snapshot),"usdtwd":safe(fx_reader,fx_snapshot)}

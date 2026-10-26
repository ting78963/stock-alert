// Frozen verbatim from ting78963/stock index.html @ ad8f0b9a36065a7771577c1860a323f43b3b1bf3
function calcKD(data, period=9){
  const isOHLC=data.length>0&&typeof data[0]==='object';
  if(!data||data.length<period) return{k:null,d:null,hist:[]};
  let k=50,d=50;
  const hist=[];
  for(let i=period-1;i<data.length;i++){
    const slice=data.slice(i-period+1,i+1);
    const hi=isOHLC?Math.max(...slice.map(x=>x.high)):Math.max(...slice);
    const lo=isOHLC?Math.min(...slice.map(x=>x.low)):Math.min(...slice);
    const cl=isOHLC?data[i].close:data[i];
    const rsv=hi===lo?50:((cl-lo)/(hi-lo))*100;
    const pk=k,pd=d;
    k=k*2/3+rsv/3;
    d=d*2/3+k/3;
    hist.push({k:Math.round(k*10)/10,d:Math.round(d*10)/10,pk:Math.round(pk*10)/10,pd:Math.round(pd*10)/10});
  }
  return{k:hist[hist.length-1]?.k??null,d:hist[hist.length-1]?.d??null,hist};
}

function calcMACD(closes,fast=12,slow=26,signal=9){
  if(!closes||closes.length<slow+signal) return{dif:null,sig:null,hist:null,histArr:[],histArr5:[]};
  function emaArr(arr,n){
    const res=[];
    // 用前N筆SMA當初始值
    const initSMA=arr.slice(0,n).reduce((a,b)=>a+b,0)/n;
    let e=initSMA;
    const k=2/(n+1);
    for(let i=0;i<arr.length;i++){
      if(i<n-1){res.push(null);continue;}
      if(i===n-1){res.push(initSMA);continue;}
      e=arr[i]*k+e*(1-k);
      res.push(e);
    }
    return res;
  }
  const cl=closes.map(x=>typeof x==='object'?x.close:x);
  const fastEma=emaArr(cl,fast);
  const slowEma=emaArr(cl,slow);
  // DIF只取兩者都有值的部分
  const dif=[];
  for(let i=0;i<cl.length;i++){
    if(fastEma[i]!=null&&slowEma[i]!=null) dif.push(fastEma[i]-slowEma[i]);
  }
  if(dif.length<signal) return{dif:null,sig:null,hist:null,histArr:[],histArr5:[]};
  // Signal用SMA初始
  const sigInit=dif.slice(0,signal).reduce((a,b)=>a+b,0)/signal;
  const sigArr=[];let sigE=sigInit;const sigK=2/(signal+1);
  for(let i=0;i<dif.length;i++){
    if(i<signal-1){sigArr.push(null);continue;}
    if(i===signal-1){sigArr.push(sigInit);continue;}
    sigE=dif[i]*sigK+sigE*(1-sigK);
    sigArr.push(sigE);
  }
  const histArr=dif.map((v,i)=>sigArr[i]!=null?Math.round((v-sigArr[i])*100)/100:null).filter(x=>x!=null);
  const n=histArr.length;
  const difLast=dif[dif.length-1];
  const sigLast=sigArr[sigArr.length-1];
  return{
    dif:Math.round(difLast*100)/100,
    sig:sigLast!=null?Math.round(sigLast*100)/100:null,
    hist:histArr[n-1]??null,
    prev_hist:histArr[n-2]??null,
    histArr:histArr.slice(-3),
    histArr5:histArr.slice(-5)
  };
}

function calcMA5MA20CrossLabel(sortedDayData){
  if(!sortedDayData||sortedDayData.length<25) return null;
  const closes=sortedDayData.map(r=>parseFloat(r.close)||0);
  const ma=(arr,n,i)=>arr.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n;
  const n=closes.length;
  // 找最近一次黃金交叉（最近10天內）
  for(let day=1;day<=5;day++){
    const i=n-day;
    if(i<20) break;
    const ma5cur=ma(closes,5,i);
    const ma20cur=ma(closes,20,i);
    const ma5prev=ma(closes,5,i-1);
    const ma20prev=ma(closes,20,i-1);
    if(ma5prev<=ma20prev && ma5cur>ma20cur){
      return day; // 幾天前交叉
    }
  }
  return null;
}

function calcMA5MA20Prepare(sortedDayData){
  if(!sortedDayData||sortedDayData.length<25) return false;
  const closes=sortedDayData.map(r=>parseFloat(r.close)||0);
  const ma=(arr,n,i)=>arr.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n;
  const n=closes.length;
  const ma5now=ma(closes,5,n-1);
  const ma20now=ma(closes,20,n-1);
  const ma5before=ma(closes,5,n-2);
  if(ma5now<ma20now){
    const diffPct=(ma20now-ma5now)/ma20now*100;
    if(diffPct<=1 && ma5now>ma5before) return true;
  }
  return false;
}

function calcWeeklyKDLabel(sortedDayData){
  if(!sortedDayData||sortedDayData.length<30) return null;
  // 按自然週（週一為起點）切割，不用固定5根
  const weeklyOHLC=[];
  let wk=[];
  for(let i=0;i<sortedDayData.length;i++){
    const row=sortedDayData[i];
    const d=new Date(row.date);
    const dayOfWeek=d.getDay(); // 0=日,1=一,...,5=五,6=六
    // 遇到週一且 wk 有資料 → 上一週結束，push 進去
    if(dayOfWeek===1 && wk.length>0){
      weeklyOHLC.push({
        close:parseFloat(wk[wk.length-1].close)||0,
        high:Math.max(...wk.map(r=>parseFloat(r.max||r.high||r.close)||0)),
        low:Math.min(...wk.map(r=>parseFloat(r.min||r.low||r.close)||0))
      });
      wk=[];
    }
    wk.push(row);
    // 最後一筆資料直接 push
    if(i===sortedDayData.length-1 && wk.length>0){
      weeklyOHLC.push({
        close:parseFloat(wk[wk.length-1].close)||0,
        high:Math.max(...wk.map(r=>parseFloat(r.max||r.high||r.close)||0)),
        low:Math.min(...wk.map(r=>parseFloat(r.min||r.low||r.close)||0))
      });
    }
  }
  if(weeklyOHLC.length<12) return null;
  const wkKD=calcKD(weeklyOHLC,9);
  if(!wkKD.hist||wkKD.hist.length<6) return null;

  const cur=wkKD.hist[wkKD.hist.length-1];
  const prev=wkKD.hist[wkKD.hist.length-2];

  // 黃金交叉第一天：上週 K<D，本週 K>D
  if(prev.k<prev.d && cur.k>cur.d) return 'golden_cross';

  // 準備黃金交叉：K在D下方，差距≤5，且K上升中
  if(cur.k<cur.d && (cur.d-cur.k)<=5 && cur.k>prev.k) return 'prepare';

  return null;
}

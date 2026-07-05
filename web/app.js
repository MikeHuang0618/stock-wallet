const $ = s => document.querySelector(s);
const api = () => window.pywebview.api;
const TYPE_NAMES={CPI:'CPI 通膨',NFP:'非農就業',FOMC:'FOMC 利率',EARN:'個股財報',
  TWR:'央行利率決議',TWCPI:'台灣 CPI'};
const OVERLAYS=[
  {id:'sma_5', label:'MA5',  color:'#5bc0de'},
  {id:'sma_10',label:'MA10', color:'#c792ea'},
  {id:'sma_20',label:'MA20', color:'#ffb454'},
  {id:'sma_60',label:'MA60', color:'#ff6b6b'},
];
const PANELS=[
  {id:'', label:'— 不顯示 —'},
  {id:'volume',   label:'成交量 Volume'},
  {id:'kd',       label:'KD 隨機指標'},
  {id:'rsi',      label:'RSI 相對強弱'},
  {id:'macd',     label:'MACD'},
  {id:'obv',      label:'OBV 能量潮'},
  {id:'bollinger',label:'布林通道 Bollinger'},
];
const SERIES_COLOR={K:'#e8c37a',D:'#c792ea',RSI:'#5bc0de',MACD:'#e8c37a',Signal:'#c792ea',
  OBV:'#5bc0de','上軌':'#ff6b6b','中軌':'#e8c37a','下軌':'#38d39f','收盤':'#9aa0b0'};
const MONTHS=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
const DOWS=['日','一','二','三','四','五','六'];

const INDICES_US=[
  {sym:'^IXIC',name:'那斯達克綜合',short:'NASDAQ'},
  {sym:'^GSPC',name:'標普 500',short:'S&P 500'},
  {sym:'^DJI',name:'道瓊工業',short:'DOW 30'},
  {sym:'^RUT',name:'羅素 2000',short:'RUSSELL'},
  {sym:'^SOX',name:'費城半導體',short:'SOX'},
  {sym:'^VIX',name:'VIX 恐慌指數',short:'VIX'},
];
const INDICES_TW=[
  {sym:'^TWII',name:'加權指數 TAIEX',short:'加權',bias:'集中市場'},
  {sym:'^TWOII',name:'櫃買指數 OTC',short:'櫃買',bias:'櫃買市場'},
  {sym:'TWTXF',name:'臺股期貨 近月',short:'台指期',bias:'期貨',clickable:false},
  {sym:'TWVIX',name:'臺指選擇權波動率指數',short:'台股VIX',bias:'波動率',clickable:false},
];
const INDICES=INDICES_US;   // 向下相容別名
function activeIndices(){return STATE.market==='tw'?INDICES_TW:INDICES_US;}
// 黃金訊號:美股 / 台股各一組槓桿+反向 ETF + 金價參考。跟隨全域 STATE.market。
// 台股無 -2x 黃金 ETF,反向只有 00674R (-1x),已如實標示。
const GOLD_US=[
  {sym:'UGL',name:'ProShares Ultra Gold',short:'UGL',bias:'+2x 做多黃金',cls:'long'},
  {sym:'GLL',name:'ProShares UltraShort Gold',short:'GLL',bias:'-2x 做空黃金',cls:'short'},
  {sym:'GC=F',name:'黃金期貨 COMEX (美元)',short:'GOLD',bias:'現貨參考',cls:'spot'},
];
const GOLD_TW=[
  {sym:'00708L.TW',name:'期元大S&P黃金正2',short:'00708L',bias:'+2x 做多黃金',cls:'long'},
  {sym:'00674R.TW',name:'期元大S&P黃金反1',short:'00674R',bias:'-1x 做空黃金',cls:'short'},
  {sym:'GC=F',name:'國際金價 COMEX (美元)',short:'GOLD',bias:'現貨參考',cls:'spot'},
];
function activeGold(){return STATE.market==='tw'?GOLD_TW:GOLD_US;}
// 兩市場所有黃金代號(去重),用於一次抓齊報價與跨市場的訊號名稱查找
const GOLD_SYMS=[...new Set([...GOLD_US,...GOLD_TW].map(g=>g.sym))];
function goldMeta(sym){return [...GOLD_US,...GOLD_TW].find(g=>g.sym===sym)||{short:sym};}
const PAGE_META={
  dashboard:{t:'主畫面',d:'大盤指數 · 觀察名單 · 重大事件與財報日曆'},
  wallet:{t:'我的錢包',d:'資產總覽 · 持倉分布 · 買賣紀錄與總結'},
  gold:{t:'黃金訊號',d:'美股 / 台股 槓桿黃金 ETF 訊號 · CPI / 非農 / FOMC 影響評估'},
  calendar:{t:'重大事件',d:'各年度重大事件與財報日曆 · 自訂事件'},
  settings:{t:'設定',d:'API 金鑰管理 · 資料匯入 / 匯出'},
  detail:{t:'標的詳細',d:'技術面圖表 · 均線 / 成交量 / KD / RSI / MACD 自選'},
};
const PIE_COLORS=['#e8c37a','#5bc0de','#c792ea','#38d39f','#ffb454','#ff6b6b','#7ec8ff','#f0a3c8','#a0e57a','#c0c4d0'];

let STATE={events:[],twEvents:[],today:null,quotes:{},alerts:[],
  market:'us',watchlists:{us:[],tw:[]},earnings:{},wlView:'cards',wlGroup:'all',
  palette:{open:false,items:[],base:[],sel:0,q:'',timer:null},
  page:'dashboard',prevPage:'dashboard',firing:new Set(),
  aicfg:{provider:'none',prompt:'',keys:{},models:{}},
  wallet:{data:null,history:null,loading:false,charts:[],ccy:'USD',symName:''},
  detail:{sym:null,name:'',timeframe:'天',overlays:['sma_20'],panels:['volume','kd'],
    chartType:'line',custom:false,start:'',end:'',data:null,loading:false,charts:[]}};

/* 依目前選擇的市場 (美股 / 台股) 取用對應資料 */
// 把 v2 群組結構(或舊扁平陣列)攤平成去重的扁平陣列。
function flattenWatchlist(wl){
  if(!wl)return [];
  if(Array.isArray(wl))return wl;
  const seen=new Set(),out=[];
  (wl.groups||[]).forEach(g=>(g.items||[]).forEach(it=>{if(it&&it.sym&&!seen.has(it.sym)){seen.add(it.sym);out.push(it);}}));
  return out;
}
// 扁平陣列(合併所有群組、去重)——維持既有呼叫點(報價/財報/palette/alerts)不變。
function activeWatchlist(){return flattenWatchlist(STATE.watchlists[STATE.market]);}
// v2 群組陣列(供群組 tabs 與管理 modal 渲染)。
function activeWatchlistGrouped(){
  const wl=STATE.watchlists[STATE.market];
  if(!wl||Array.isArray(wl))return [{id:'default',name:'預設',items:Array.isArray(wl)?wl:[]}];
  return wl.groups||[];
}
// 取當前市場的 v2 結構(必要時就地升級並補預設群組),供變更操作使用。
function currentWL(){
  let wl=STATE.watchlists[STATE.market];
  if(!wl||Array.isArray(wl)){wl={version:2,groups:[{id:'default',name:'預設',items:Array.isArray(wl)?wl:[]}]};STATE.watchlists[STATE.market]=wl;}
  if(!wl.groups.some(g=>g.id==='default'))wl.groups.unshift({id:'default',name:'預設',items:[]});
  return wl;
}
function saveWL(){api().save_watchlist(STATE.watchlists[STATE.market],STATE.market);}
function activeEvents(){return STATE.market==='tw'?STATE.twEvents:STATE.events;}

/* ---------- utils ---------- */
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),2200);}
function fmt(n,d=2){return n==null||isNaN(n)?'—':Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function daysBetween(a,b){return Math.round((new Date(b+'T00:00:00')-new Date(a+'T00:00:00'))/86400000);}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
// 鍵盤可近性:讓元素可聚焦(tabindex)並具 button 語意,Enter/Space 觸發 click。
function keyActivatable(el){
  el.setAttribute('tabindex','0');el.setAttribute('role','button');
  el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}});
}
// 漲跌色:讀當前 --up/--down(受漲跌慣例 body class 影響),供圖表硬著色處跟隨。
function cssVar(name){return getComputedStyle(document.documentElement).getPropertyValue(name).trim();}
function upColor(){return cssVar('--up')||'#38d39f';}
function downColor(){return cssVar('--down')||'#ff6b6b';}
// 卡片容器:首次渲染播 card-in 進場動畫並標記 data-live;之後重建先加 .no-anim
// 不重播動畫(避免資料刷新時卡片反覆浮起)。markNoAnim 供多行模板就地套用。
function markNoAnim(el){
  if(!el)return;
  if(el.dataset.live)el.classList.add('no-anim');
  else{el.classList.remove('no-anim');el.dataset.live='1';}
}
function renderCards(el,html){if(!el)return;markNoAnim(el);el.innerHTML=html;}
// 漲跌顏色慣例:us=綠漲紅跌(預設)、tw=紅漲綠跌。以 html class 交換 --up/--down。
function initUpDown(){
  const c=localStorage.getItem('updown')==='tw'?'tw':'us';
  document.documentElement.classList.toggle('updown-tw',c==='tw');
  const sel=$('#updown-sel');if(sel)sel.value=c;
}

/* Theme Engine */
function initTheme(){
  const t = localStorage.getItem('theme') || 'system';
  if(t==='system') document.documentElement.dataset.theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  else document.documentElement.dataset.theme = t;
  const sel=$('#theme-sel'); if(sel) sel.value=t;
}
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
  if((localStorage.getItem('theme')||'system')==='system') initTheme();
});

/* Custom Select Logic */
function createCustomSelect(sel){
  if(sel.nextElementSibling && sel.nextElementSibling.classList.contains('custom-select')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'custom-select';
  sel.parentNode.insertBefore(wrapper, sel);
  wrapper.appendChild(sel);
  
  const selected = document.createElement('div');
  selected.className = 'select-selected';
  selected.innerHTML = sel.options[sel.selectedIndex>=0?sel.selectedIndex:0]?.innerHTML||'';
  wrapper.appendChild(selected);
  
  const items = document.createElement('div');
  items.className = 'select-items select-hide';
  items._owner = selected;
  sel._itemsContainer = items;
  Array.from(sel.options).forEach((opt, idx) => {
    const item = document.createElement('div');
    item.innerHTML = opt.innerHTML;
    item.onclick = function(e) {
      sel.selectedIndex = idx;
      selected.innerHTML = this.innerHTML;
      sel.dispatchEvent(new Event('change'));
      selected.click();
    };
    items.appendChild(item);
  });
  document.body.appendChild(items);
  
  selected.onclick = function(e) {
    e.stopPropagation();
    const isHide = items.classList.contains('select-hide');
    closeAllSelect(this);
    if(isHide) {
      items.classList.remove('select-hide');
      this.classList.add('select-arrow-active');
      const rect = this.getBoundingClientRect();
      items.style.top = (rect.bottom + 4) + 'px';
      items.style.left = rect.left + 'px';
      items.style.width = rect.width + 'px';
    } else {
      items.classList.add('select-hide');
      this.classList.remove('select-arrow-active');
    }
  };
}
function syncCustomSelect(sel){
  if(sel.parentNode.classList.contains('custom-select')){
    sel.parentNode.querySelector('.select-selected').innerHTML = sel.options[sel.selectedIndex>=0?sel.selectedIndex:0]?.innerHTML||'';
    const items = sel._itemsContainer;
    if(!items) return;
    items.innerHTML = '';
    Array.from(sel.options).forEach((opt, idx) => {
      const item = document.createElement('div');
      item.innerHTML = opt.innerHTML;
      item.onclick = function(e) {
        sel.selectedIndex = idx;
        sel.parentNode.querySelector('.select-selected').innerHTML = this.innerHTML;
        sel.dispatchEvent(new Event('change'));
        sel.parentNode.querySelector('.select-selected').click();
      };
      items.appendChild(item);
    });
  }
}
function closeAllSelect(except) {
  document.querySelectorAll('.select-items').forEach(el => {
    if (el._owner !== except) el.classList.add('select-hide');
  });
  document.querySelectorAll('.select-selected').forEach(el => {
    if (el !== except) el.classList.remove('select-arrow-active');
  });
}
document.addEventListener('click', closeAllSelect);
window.addEventListener('wheel', (e) => {
  if (e.target && e.target.closest && e.target.closest('.select-items')) return;
  closeAllSelect();
}, {passive: true});
window.addEventListener('touchmove', (e) => {
  if (e.target && e.target.closest && e.target.closest('.select-items')) return;
  closeAllSelect();
}, {passive: true});
window.addEventListener('resize', ()=>closeAllSelect());

function sparkSVG(vals,dir){
  if(!vals||vals.length<2) return '<svg class="spark"></svg>';
  const w=100,h=34,pad=3,min=Math.min(...vals),max=Math.max(...vals),rng=(max-min)||1;
  const pts=vals.map((v,i)=>{const x=pad+i*(w-2*pad)/(vals.length-1);const y=h-pad-(v-min)/rng*(h-2*pad);return x.toFixed(1)+','+y.toFixed(1);});
  // 顏色跟隨「當日漲跌方向」(與百分比一致),線本身仍畫 30 點走勢。方向未知則中性色。
  const col=dir==='up'?'var(--up)':dir==='down'?'var(--down)':'var(--muted)',id='g'+Math.random().toString(36).slice(2,7);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <polyline points="${pad},${h-pad} ${pts.join(' ')} ${w-pad},${h-pad}" fill="url(#${id})" stroke="none"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function quoteCard(sym,meta){
  const p=STATE.quotes[sym]||{};
  const dir=p.change==null?'flat':(p.change>0?'up':(p.change<0?'down':'flat'));
  const arrow=dir==='up'?'▲':dir==='down'?'▼':'—';
  const dec=(meta.dec!=null)?meta.dec:2;
  const chg=p.change==null?(p.error?'無資料':'讀取中…'):`${arrow} ${fmt(Math.abs(p.change),dec)} (${fmt(Math.abs(p.changePct))}%)`;
  const biasHtml=meta.bias?`<span class="bias ${meta.cls}">${meta.bias}</span>`:'';
  const rm=meta.removable?`<span class="rm" data-rm="${esc(sym)}">✕</span>`:'';
  const open=meta.clickable?` clk" data-open="${esc(sym)}" data-name="${esc(meta.name||sym)}" tabindex="0" role="button`:'';
  return `<div class="qcard${open}" data-sym="${esc(sym)}" style="--i:${meta._i||0}">${rm}
    <div class="tk"><span class="sym">${esc(meta.short||sym)}</span>${biasHtml}</div>
    <div class="nm">${esc(meta.name||'')}</div>
    <div class="row"><div class="price">${p.error||p.price==null?(p.price==null&&!p.error?'…':'—'):fmt(p.price,dec)}</div>
    <div class="chg ${dir}">${chg}</div></div><div class="spark-wrap">${sparkSVG(p.spark,dir)}${(p.spark&&p.spark.length>1)?'<span class="spark-30d">30d</span>':''}</div></div>`;
}

/* ---------- dashboard ---------- */
function renderIndices(){
  const idx=activeIndices();
  $('#idx-count').textContent=`${idx.length} 項`;
  renderCards($('#indices'),idx.map((i,n)=>quoteCard(i.sym,{name:i.name,short:i.short,bias:i.bias||'指數',cls:'idx',dec:2,clickable:i.clickable!==false,_i:n})).join(''));
}
function heatColor(pct){
  if(pct==null)return 'rgba(255,255,255,.04)';
  const m=Math.min(Math.abs(pct)/3,1),a=(0.12+m*0.5).toFixed(2);  // 3% 達到最深
  return pct>=0?`rgba(56,211,159,${a})`:`rgba(255,107,107,${a})`;
}
function heatTile(w){
  const pct=(STATE.quotes[w.sym]||{}).changePct;
  return `<div class="hm-tile clk" data-open="${esc(w.sym)}" data-name="${esc(w.name)}" style="background:${heatColor(pct)}">
    <div class="hm-sym">${esc(w.sym)}</div>
    <div class="hm-pct">${pct==null?'—':(pct>=0?'+':'')+fmt(pct)+'%'}</div></div>`;
}
function renderWlTabs(){
  const tabs=$('#wl-tabs');if(!tabs)return;
  const groups=activeWatchlistGrouped();
  // 選中的群組在此市場不存在時退回「全部」(群組 id 為各市場專屬)
  let sel=STATE.wlGroup||'all';
  if(sel!=='all'&&!groups.some(g=>g.id===sel)){sel='all';STATE.wlGroup='all';}
  let html=`<button class="wl-tab${sel==='all'?' on':''}" data-g="all">全部</button>`;
  html+=groups.map(g=>`<button class="wl-tab${sel===g.id?' on':''}" data-g="${esc(g.id)}">${esc(g.name)} <span class="wl-tn">${(g.items||[]).length}</span></button>`).join('');
  html+=`<button class="wl-tab wl-manage" data-g="__manage" title="管理群組">⚙</button>`;
  tabs.innerHTML=html;
  tabs.querySelectorAll('.wl-tab').forEach(b=>b.onclick=()=>{
    const g=b.dataset.g;
    if(g==='__manage')openWlgModal();else setWlGroup(g);
  });
}
function setWlGroup(id){
  STATE.wlGroup=id;try{localStorage.setItem('wlGroup',id);}catch(e){}
  renderWatchlist();
}
// 依選中 tab 決定顯示的清單:「全部」= 合併去重;群組 = 該群組 items。
function watchlistForView(){
  const sel=STATE.wlGroup||'all';
  if(sel==='all')return activeWatchlist();
  const g=activeWatchlistGrouped().find(x=>x.id===sel);
  return g?(g.items||[]):activeWatchlist();
}
function renderWatchlist(){
  renderWlTabs();
  const wl=watchlistForView();
  $('#wl-count').textContent=`${wl.length} 檔`;
  const box=$('#watchlist');
  if(!wl.length){box.className='qgrid';box.innerHTML=`<div class="empty">${STATE.wlGroup==='all'?'觀察名單是空的':'此群組是空的'} · 用上方搜尋框加入標的</div>`;return;}
  if(STATE.wlView==='heatmap'){
    box.className='heatmap';
    box.innerHTML=wl.map(heatTile).join('');
    box.querySelectorAll('.hm-tile[data-open]').forEach(t=>t.onclick=()=>openDetail(t.dataset.open,t.dataset.name));
  }else{
    box.className='qgrid';
    renderCards(box,wl.map((w,n)=>quoteCard(w.sym,{name:w.name,short:w.sym,removable:true,clickable:true,_i:n})).join(''));
    box.querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>removeWatch(b.dataset.rm));
  }
}
// ---- 群組變更操作(就地改 v2 結構並存檔)----
function addGroup(name){
  const wl=currentWL(),id='g'+Date.now().toString(36)+Math.floor(Math.random()*1e3);
  wl.groups.push({id,name:name||'新群組',items:[]});saveWL();
}
function renameGroup(id,name){
  const g=currentWL().groups.find(x=>x.id===id);
  if(g){g.name=name;saveWL();renderWatchlist();}
}
function deleteGroup(id){
  if(id==='default')return;                 // 預設群組不可刪
  const wl=currentWL(),g=wl.groups.find(x=>x.id===id);if(!g)return;
  const def=wl.groups.find(x=>x.id==='default');
  (g.items||[]).forEach(it=>{if(!def.items.some(d=>d.sym===it.sym))def.items.push(it);});  // items 併回預設
  wl.groups=wl.groups.filter(x=>x.id!==id);
  if(STATE.wlGroup===id)setWlGroup('all');
  saveWL();
}
function moveSymbol(sym,toId){
  const wl=currentWL();let item=null;
  wl.groups.forEach(g=>{const i=(g.items||[]).findIndex(it=>it.sym===sym);if(i>=0){item=g.items[i];g.items.splice(i,1);}});
  if(!item)return;
  (wl.groups.find(x=>x.id===toId)||wl.groups.find(x=>x.id==='default')).items.push(item);saveWL();
}
// ---- 群組管理 modal ----
function renderWlgModal(){
  const groups=currentWL().groups,box=$('#wlg-list');
  box.innerHTML=groups.map(g=>{
    const isDef=g.id==='default';
    const items=(g.items||[]).map(it=>{
      const opts=groups.filter(x=>x.id!==g.id).map(x=>`<option value="${esc(x.id)}">移到 ${esc(x.name)}</option>`).join('');
      return `<div class="wlg-item"><span class="wlg-sym">${esc(it.sym)}</span><span class="wlg-nm">${esc(it.name||'')}</span>${opts?`<select class="wlg-move" data-sym="${esc(it.sym)}"><option value="">移到…</option>${opts}</select>`:''}</div>`;
    }).join('')||'<div class="wlg-empty">(空)</div>';
    return `<div class="wlg-group"><div class="wlg-ghead">
      <input class="wlg-gname" data-gid="${esc(g.id)}" value="${esc(g.name)}" maxlength="20"${isDef?' disabled':''}>
      ${isDef?'<span class="wlg-deftag">預設</span>':`<button class="wlg-del" data-gid="${esc(g.id)}">🗑</button>`}
    </div><div class="wlg-items">${items}</div></div>`;
  }).join('');
  box.querySelectorAll('.wlg-gname').forEach(inp=>inp.onchange=()=>renameGroup(inp.dataset.gid,inp.value.trim()||'群組'));
  box.querySelectorAll('.wlg-del').forEach(b=>b.onclick=()=>{deleteGroup(b.dataset.gid);renderWlgModal();renderWatchlist();});
  box.querySelectorAll('.wlg-move').forEach(sel=>sel.onchange=()=>{if(sel.value){moveSymbol(sel.dataset.sym,sel.value);renderWlgModal();renderWatchlist();}});
}
function openWlgModal(){renderWlgModal();$('#wlg-modal').classList.add('show');}
function closeWlgModal(){$('#wlg-modal').classList.remove('show');}
function initWatchlistView(){
  STATE.wlView=localStorage.getItem('wlView')==='heatmap'?'heatmap':'cards';
  STATE.wlGroup=localStorage.getItem('wlGroup')||'all';
  // 群組管理 modal 綁定(新增/關閉/背景/Esc)
  $('#wlg-add').onclick=()=>{const n=$('#wlg-new-name').value.trim();if(!n){toast('請輸入群組名稱');return;}addGroup(n);$('#wlg-new-name').value='';renderWlgModal();renderWatchlist();};
  $('#wlg-close').onclick=closeWlgModal;
  $('#wlg-modal').onclick=e=>{if(e.target.id==='wlg-modal')closeWlgModal();};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#wlg-modal').classList.contains('show'))closeWlgModal();});
  const sw=$('#wl-view');if(!sw)return;
  sw.querySelectorAll('button').forEach(b=>{
    b.classList.toggle('on',b.dataset.v===STATE.wlView);
    b.onclick=()=>{STATE.wlView=b.dataset.v;try{localStorage.setItem('wlView',b.dataset.v);}catch(e){}
      sw.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.v===STATE.wlView));
      renderWatchlist();};
  });
}
async function addWatch(sym,name){
  if(activeWatchlist().some(w=>w.sym===sym)){toast(`${sym} 已在觀察名單`);return;}
  // 加入目前選中的群組(「全部」時進預設群組)
  const wl=currentWL(),gid=(STATE.wlGroup&&STATE.wlGroup!=='all')?STATE.wlGroup:'default';
  const g=wl.groups.find(x=>x.id===gid)||wl.groups.find(x=>x.id==='default');
  g.items.push({sym,name:name||sym});saveWL();
  api().set_quote_symbols(quoteSymbols());   // 讓背景刷新器納入新標的
  renderWatchlist();toast(`已加入 ${sym}`);
  const q=await api().get_quotes([sym]);Object.assign(STATE.quotes,q);renderWatchlist();
  refreshEarnings();
}
function removeWatch(sym){
  const wl=currentWL();
  wl.groups.forEach(g=>{g.items=(g.items||[]).filter(it=>it.sym!==sym);});
  delete STATE.earnings[sym];
  saveWL();api().set_quote_symbols(quoteSymbols());
  renderWatchlist();renderDashEvents();renderFullCalendar();
}

/* ---------- search ---------- */
let searchTimer=null;
function initSearch(){
  const inp=$('#search'),res=$('#results');
  inp.addEventListener('input',()=>{
    clearTimeout(searchTimer);const q=inp.value.trim();
    if(q.length<1){res.classList.remove('show');return;}
    searchTimer=setTimeout(async()=>{
      const list=await api().search_symbol(q);
      if(!list.length){res.innerHTML='<div class="rrow"><span class="rn">查無結果</span></div>';res.classList.add('show');return;}
      res.innerHTML=list.map(r=>`<div class="rrow" data-sym="${esc(r.sym)}" data-name="${esc(r.name)}">
        <span class="rs">${esc(r.sym)}</span><span class="rn">${esc(r.name)}</span>
        <span class="re">${esc(r.exch||r.type||'')}</span><span class="radd">＋</span></div>`).join('');
      res.classList.add('show');
      res.querySelectorAll('.rrow[data-sym]').forEach(row=>{row.onclick=()=>{
        addWatch(row.dataset.sym,row.dataset.name);res.classList.remove('show');inp.value='';
      };keyActivatable(row);});
    },260);
  });
  document.addEventListener('click',e=>{if(!e.target.closest('.searchbar'))res.classList.remove('show');});
}

/* ---------- gold ---------- */
function renderGoldPrices(){
  const g=activeGold();
  const t=$('#gold-title');if(t)t.textContent=(STATE.market==='tw'?'台股':'美股')+'槓桿黃金 · '+g[0].short+' / '+g[1].short;
  renderCards($('#gold-prices'),g.map((x,n)=>quoteCard(x.sym,{name:x.name,short:x.short,bias:x.bias,cls:x.cls,dec:2,clickable:true,_i:n})).join(''));
}
function earningsEvents(){
  return Object.entries(STATE.earnings).map(([sym,info])=>({
    date:info.date,type:'EARN',title:`${sym} 財報${info.estimate?'(預估)':''}`,
    time:'盤後',impact:'high'})).filter(e=>e.date);
}
function renderEventsInto(boxId,countId,events,limit){
  const today=STATE.today;
  const up=events.filter(e=>daysBetween(today,e.date)>=0).sort((a,b)=>a.date.localeCompare(b.date)).slice(0,limit);
  if(countId)$(countId).textContent=`未來 ${up.length} 場`;
  const box=$(boxId);
  if(!up.length){box.innerHTML='<div class="empty">目前沒有即將到來的事件</div>';return;}
  box.innerHTML=up.map(e=>{
    const d=daysBetween(today,e.date),soon=d<=3;
    const label=d===0?'今天':d===1?'明天':d,unit=d<=1?'':'天後',md=e.date.slice(5).replace('-','/');
    const tm=e.time==='—'?'':`(${e.time==='盤後'?'':'台北 '}${e.time})· `;
    return `<div class="ev ${soon?'soon':''}" style="cursor:pointer" data-date="${esc(e.date)}">
      <div class="impact ${esc(e.impact)}"></div>
      <div class="badge ${esc(e.type)}">${esc(e.type)}</div>
      <div class="body"><div class="t">${esc(e.title)}</div><div class="m">${esc(md)}${esc(tm)}${esc(TYPE_NAMES[e.type]||'自訂')}</div></div>
      <div class="cd ${d===0?'today':''}"><div class="n">${label}</div><div class="u">${unit}</div></div></div>`;
  }).join('');
  // 事件委派取代 inline onclick(相容 CSP):點事件卡跳到該日期的日曆。
  box.onclick=ev=>{const el=ev.target.closest('.ev[data-date]');if(el)openCalendarToDate(el.dataset.date);};
}
function renderEvents(){renderEventsInto('#events','#evcount',STATE.events,9);}
function renderDashEvents(){
  renderEventsInto('#dash-events','#dash-evcount',activeEvents().concat(earningsEvents()),8);
  // 觀察個股財報清單
  const today=STATE.today;
  const list=Object.entries(STATE.earnings).map(([sym,info])=>({sym,...info}))
    .filter(e=>e.date&&daysBetween(today,e.date)>=0).sort((a,b)=>a.date.localeCompare(b.date));
  $('#dash-ercount').textContent=`${list.length} 檔`;
  const box=$('#dash-earnings');
  if(!list.length){box.innerHTML='<div class="empty">觀察名單暫無即將到來的財報日<br>(加入個股後自動抓取)</div>';return;}
  box.innerHTML=list.map(e=>{
    const d=daysBetween(today,e.date),soon=d<=7,md=e.date.slice(5).replace('-','/');
    const name=(activeWatchlist().find(w=>w.sym===e.sym)||{}).name||'';
    return `<div class="ev ${soon?'soon':''}"><div class="impact high"></div>
      <div class="badge EARN">財報</div>
      <div class="body"><div class="t">${esc(e.sym)} <span style="color:var(--muted);font-weight:400">${esc(name)}</span></div>
        <div class="m">${md}${e.estimate?' · 預估日期':''} · 盤後公布</div></div>
      <div class="cd ${d===0?'today':''}"><div class="n">${d===0?'今天':d}</div><div class="u">${d<=0?'':'天後'}</div></div></div>`;
  }).join('');
}
function renderAlerts(){
  const box=$('#alerts');
  if(!STATE.alerts.length){box.innerHTML='<div class="empty">尚未設定任何價位訊號 · 於上方新增</div>';return;}
  const nowFiring=new Set();
  box.innerHTML=STATE.alerts.map((a,i)=>{
    const p=STATE.quotes[a.tk]||{},now=p.price;
    let hit=false;if(now!=null)hit=a.cond==='above'?now>=a.lvl:now<=a.lvl;
    const key=a.tk+a.cond+a.lvl;if(hit)nowFiring.add(key);
    const meta=goldMeta(a.tk);
    const condTxt=a.cond==='above'?'突破 ≥':'跌破 ≤';
    return `<div class="al ${hit?'hit':''}"><span class="k">${esc(meta.short)}</span><span class="cond">${condTxt}</span>
      <span class="lvl">${fmt(a.lvl)}</span><span class="now">現價<br>${now==null?'—':fmt(now)}</span>
      <span class="st ${hit?'fire':'wait'}">${hit?'✓ 觸發':'等待中'}</span><span class="x" data-i="${i}">✕</span></div>`;
  }).join('');
  box.querySelectorAll('.x').forEach(x=>x.onclick=()=>{STATE.alerts.splice(+x.dataset.i,1);persistAlerts();renderAlerts();});
  // 新觸發 -> 系統通知
  nowFiring.forEach(key=>{
    if(!STATE.firing.has(key)){
      const a=STATE.alerts.find(z=>z.tk+z.cond+z.lvl===key);
      if(a){const meta=goldMeta(a.tk);
        const now=(STATE.quotes[a.tk]||{}).price;
        api().notify('🔔 價位訊號觸發',`${meta.short} ${a.cond==='above'?'突破':'跌破'} ${fmt(a.lvl)}(現價 ${fmt(now)})`);}
    }
  });
  STATE.firing=nowFiring;
}
function persistAlerts(){api().save_alerts(STATE.alerts);}
function refreshAlertSymbols(){
  const sel=$('#a-tk');if(!sel)return;
  sel.innerHTML=activeGold().map(g=>`<option value="${g.sym}">${g.short}</option>`).join('');
  syncCustomSelect(sel);
}
function initAlertForm(){
  refreshAlertSymbols();
  $('#a-add').onclick=async()=>{
    const tk=$('#a-tk').value,lvl=parseFloat($('#a-lvl').value),cond=$('#a-cond').value;
    if(isNaN(lvl)||lvl<=0){toast('請輸入有效價位');return;}
    STATE.alerts.push({tk,lvl,cond});persistAlerts();
    STATE.firing.add(tk+cond+lvl); // 避免加入當下若已觸發立刻重複通知,交由下輪比較
    STATE.firing.delete(tk+cond+lvl);
    renderAlerts();$('#a-lvl').value='';
    const meta=goldMeta(tk);
    api().notify('已新增價位訊號',`${meta.short} ${cond==='above'?'突破 ≥':'跌破 ≤'} ${fmt(lvl)}`);
    toast(`已新增 ${meta.short} 訊號`);
  };
  $('#a-lvl').addEventListener('keydown',e=>{if(e.key==='Enter')$('#a-add').click();});
}
function renderFullCalendar(){
  const year=$('#cal-year-sel').value;
  // 跟隨全域市場(與儀表板 renderDashEvents 一致),使自訂事件在對應市場的日曆可見。
  renderCalendarInto('#full-calendar',activeEvents().concat(earningsEvents()),year);
}
function openCalendarToDate(date_str){
  if(!date_str)return;
  const year=date_str.slice(0,4);
  $('#cal-year-sel').value=year;
  renderFullCalendar();
  nav('calendar');
  setTimeout(()=>{
    const el=document.querySelector(`[data-date="${date_str}"]`);
    if(el){
      el.scrollIntoView({behavior:'smooth',block:'center'});
      el.classList.remove('blink');
      void el.offsetWidth; // trigger reflow
      el.classList.add('blink');
    }
  },100);
}
function renderCustomEvents(){
  const box=$('#ce-list');
  // 只列出使用者自訂事件(source==='custom');內建事件不可刪除,不列入管理清單。
  // 跟隨全域市場:美股管美股自訂事件、台股管台股自訂事件。
  const evs=activeEvents().filter(e=>e.source==='custom');
  if(!evs.length){box.innerHTML='<div class="empty">目前沒有自訂事件</div>';return;}
  box.innerHTML=evs.map((e,i)=>`
    <div class="txrow" style="padding:4px 8px">
      <span class="badge ${esc(e.type)}">${esc(e.type)}</span>
      <span class="g">${esc(e.date)}</span>
      <span class="g" style="flex:1;font-weight:600">${esc(e.title)}</span>
      <span class="del" data-delce="${i}" data-cedate="${esc(e.date)}" data-cetitle="${esc(e.title)}">🗑 刪除</span>
    </div>
  `).join('');
  box.querySelectorAll('[data-delce]').forEach(b=>b.onclick=async()=>{
    await api().delete_event(b.dataset.cedate,b.dataset.cetitle,STATE.market);
    await reloadEvents();
  });
}
async function reloadEvents(){
  // 兩個市場的事件都重載,維持 STATE.events / STATE.twEvents 一致。
  const ev=await api().get_events('us');STATE.events=ev.events;STATE.today=ev.today;
  const evtw=await api().get_events('tw');STATE.twEvents=evtw.events;
  renderEvents();renderDashEvents();renderFullCalendar();renderCustomEvents();
}
function initCustomEventsForm(){
  $('#cal-year-sel').onchange=renderFullCalendar;
  $('#ce-date').value=(STATE.today||new Date().toISOString().slice(0,10));
  
  const applyCeCol=c=>{
    $('#ce-body').classList.toggle('collapsed',c);
    $('#ce-arrow').textContent=c?'▼':'▲';
  };
  applyCeCol(localStorage.getItem('calendarEventsCollapsed')!=='0');
  $('#ce-toggle').onclick=()=>{
    const c=!$('#ce-body').classList.contains('collapsed');
    applyCeCol(c);localStorage.setItem('calendarEventsCollapsed',c?'1':'0');
  };

  $('#ce-add').onclick=async()=>{
    const d=$('#ce-date').value, t=$('#ce-type').value, title=$('#ce-title').value,
          time=$('#ce-time').value, imp=$('#ce-impact').value;
    if(!d||!title){toast('請填寫日期與事件名稱');return;}
    const r=await api().add_event(d,t,title,time,imp,STATE.market);
    if(!r.ok){toast('新增失敗');return;}
    toast('已新增事件');$('#ce-title').value='';
    await reloadEvents();
  };
}
function renderCalendarInto(boxId,events,year='2026'){
  const byDate={};events.forEach(e=>{if(e.date&&e.date.startsWith(year))(byDate[e.date]=byDate[e.date]||[]).push(e.type);});
  const [,tm,td]=STATE.today.split('-').map(Number);
  const box=$(boxId);if(!box)return;
  let html='';
  for(let m=0;m<12;m++){
    const first=new Date(year,m,1).getDay(),dim=new Date(year,m+1,0).getDate(),cur=(m+1===tm && STATE.today.startsWith(year));
    let cells='';for(let i=0;i<first;i++)cells+='<div class="day"></div>';
    for(let dn=1;dn<=dim;dn++){
      const ds=`${year}-${String(m+1).padStart(2,'0')}-${String(dn).padStart(2,'0')}`;
      const types=[...new Set(byDate[ds]||[])],isToday=(ds===STATE.today);
      const cls='day d'+(types.length?' has':'')+(isToday?' today':'');
      const marks=types.length?`<div class="mk">${types.map(t=>`<i class="${esc(t)}"></i>`).join('')}</div>`:'';
      const tip=types.length?`data-tip="${ds.slice(5)} · ${(byDate[ds]).map(t=>TYPE_NAMES[t]||'自訂').join('、')}"`:'';
      cells+=`<div class="${cls}" data-date="${ds}" ${tip}>${dn}${marks}</div>`;
    }
    html+=`<div class="mo ${cur?'cur':''}"><h3>${MONTHS[m]}</h3><div class="dows">${DOWS.map(d=>`<span>${d}</span>`).join('')}</div><div class="days">${cells}</div></div>`;
  }
  box.innerHTML=html;
  const tip=$('#tip');
  box.querySelectorAll('[data-tip]').forEach(el=>{
    el.onmousemove=ev=>{tip.textContent=el.dataset.tip;tip.classList.add('show');
      tip.style.left=Math.min(ev.clientX+12,innerWidth-230)+'px';tip.style.top=(ev.clientY+14)+'px';};
    el.onmouseleave=()=>tip.classList.remove('show');
  });
}

/* ---------- chart engine (SVG) ---------- */
function fmtVol(n){if(n==null)return'';const a=Math.abs(n);
  if(a>=1e9)return(n/1e9).toFixed(2)+'B';if(a>=1e6)return(n/1e6).toFixed(2)+'M';if(a>=1e3)return(n/1e3).toFixed(1)+'K';return String(Math.round(n));}
function polySegs(values,xAt,yAt,color,w){
  let segs=[],cur=[];
  values.forEach((v,i)=>{if(v==null){if(cur.length>1)segs.push(cur);cur=[];}else cur.push(xAt(i)+','+yAt(v));});
  if(cur.length>1)segs.push(cur);
  return segs.map(s=>`<polyline points="${s.join(' ')}" fill="none" stroke="${color}" stroke-width="${w||1.6}" stroke-linejoin="round" stroke-linecap="round"/>`).join('');
}
const CHART_GEO={W:760,PL:55,PR:40,PT:8,PB:20};
function xAtG(g,i){
  const bw = Math.max(1, g.plotW/Math.max(1,g.n)*0.62);
  const pad = bw/2 + 1;
  return g.n<=1 ? g.PL+g.plotW/2 : g.PL+pad+i*(g.plotW-2*pad)/(g.n-1);
}
function yAtG(g,v){return g.PT+g.plotH-(v-g.yMin)/(g.yMax-g.yMin)*g.plotH;}
function chartGeo(o,width){
  const {PL,PR,PT,PB}=CHART_GEO,H=o.height;
  // viewBox 寬 = 容器實寬(後備 760)。與顯示寬 1:1,preserveAspectRatio="none" 便不再
  // 於寬螢幕橫向拉伸文字。crosshair 的 xAtG/px 對映用比例,g.W 改變仍一致。
  const W=Math.max(320,Math.round(width||CHART_GEO.W));
  const n=(o.labels||[]).length,plotW=W-PL-PR,plotH=H-PT-PB;
  const vals=[];
  (o.lines||[]).forEach(s=>s.values.forEach(v=>{if(v!=null)vals.push(v);}));
  if(o.bars)o.bars.values.forEach(v=>{if(v!=null)vals.push(v);});
  if(o.candles){o.candles.high.forEach(v=>{if(v!=null)vals.push(v);});o.candles.low.forEach(v=>{if(v!=null)vals.push(v);});}
  (o.guides||[]).forEach(g=>vals.push(g));
  if(o.zeroLine)vals.push(0);
  if(o.bars&&o.bars.baseline==='bottom')vals.push(0);
  if(!vals.length)return null;
  let yMin=Math.min(...vals),yMax=Math.max(...vals);
  if(yMin===yMax){yMin-=1;yMax+=1;}
  const pad=(yMax-yMin)*0.06;yMin-=pad;yMax+=pad;
  if(o.bars&&o.bars.baseline==='bottom')yMin=0;
  return {W,PL,PR,PT,PB,H,n,plotW,plotH,yMin,yMax};
}
function chartSVG(o,g){
  let s='';
  const ticks=4;for(let k=0;k<=ticks;k++){const val=g.yMin+(g.yMax-g.yMin)*k/ticks,y=yAtG(g,val);
    s+=`<line class="gridline" x1="${g.PL}" y1="${y.toFixed(1)}" x2="${g.W-g.PR}" y2="${y.toFixed(1)}"/>`;
    s+=`<text class="axis-lbl" x="${g.PL-5}" y="${(y+3).toFixed(1)}" text-anchor="end">${o.fmtY?o.fmtY(val):val.toFixed(2)}</text>`;}
  (o.guides||[]).forEach(gv=>{const y=yAtG(g,gv);s+=`<line class="guide" x1="${g.PL}" y1="${y.toFixed(1)}" x2="${g.W-g.PR}" y2="${y.toFixed(1)}"/>`;
    s+=`<text class="axis-lbl" x="${g.W-g.PR}" y="${(y-2).toFixed(1)}" text-anchor="end">${gv}</text>`;});
  if(o.zeroLine){const y=yAtG(g,0);s+=`<line class="zeroline" x1="${g.PL}" y1="${y.toFixed(1)}" x2="${g.W-g.PR}" y2="${y.toFixed(1)}"/>`;}
  if(o.bars){const base=(o.bars.baseline==='zero')?yAtG(g,0):yAtG(g,g.yMin);const bw=Math.max(1,g.plotW/g.n*0.62);
    o.bars.values.forEach((v,i)=>{if(v==null)return;const x=xAtG(g,i),y=yAtG(g,v),top=Math.min(y,base),hh=Math.abs(y-base);
      s+=`<rect x="${(x-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.5,hh).toFixed(1)}" fill="${o.bars.colors[i]}" opacity="0.75"/>`;});}
  if(o.candles){const cd=o.candles,bw=Math.max(1.2,g.plotW/g.n*0.6);
    for(let i=0;i<g.n;i++){const op=cd.open[i],hi=cd.high[i],lw=cd.low[i],cl=cd.close[i];
      if(op==null||hi==null||lw==null||cl==null)continue;
      const x=xAtG(g,i),col=cl>=op?'var(--up)':'var(--down)';
      s+=`<line x1="${x.toFixed(1)}" y1="${yAtG(g,hi).toFixed(1)}" x2="${x.toFixed(1)}" y2="${yAtG(g,lw).toFixed(1)}" stroke="${col}" stroke-width="1"/>`;
      const yo=yAtG(g,op),yc=yAtG(g,cl),top=Math.min(yo,yc),bh=Math.max(1,Math.abs(yo-yc));
      s+=`<rect x="${(x-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`;}}
  (o.lines||[]).forEach(sr=>{s+=polySegs(sr.values,i=>xAtG(g,i),v=>yAtG(g,v),sr.color,sr.w);});
  const steps=Math.min(5,g.n);for(let k=0;k<steps;k++){const i=Math.round(k*(g.n-1)/Math.max(1,steps-1)),x=xAtG(g,i);
    const anchor=k===0?'start':k===steps-1?'end':'middle';
    s+=`<text class="axis-lbl" x="${x.toFixed(1)}" y="${g.H-5}" text-anchor="${anchor}">${esc((o.labels[i]||''))}</text>`;}
  return `<svg viewBox="0 0 ${g.W} ${g.H}" preserveAspectRatio="none" style="height:${g.H}px">${s}</svg>`;
}
function mountChart(boxEl,o){
  const g=chartGeo(o,boxEl.clientWidth);
  if(!g){boxEl.innerHTML='<div class="chart-msg">此範圍資料不足以計算</div>';return null;}
  boxEl.innerHTML=`<div class="chartwrap" style="height:${o.height}px">${chartSVG(o,g)}<div class="cross-v"></div></div>`;
  const wrap=boxEl.querySelector('.chartwrap');
  const lines=o.lines||[];
  const dots=lines.map(sr=>{const d=document.createElement('div');d.className='cross-dot';d.style.background=sr.color;wrap.appendChild(d);return d;});
  const model={wrap,g,lines,labels:o.labels,dots,fmtY:o.fmtY};
  if(o.candles)model.candles=o.candles;
  if(o.bars&&o.barName){model.barVals=o.bars.values;model.barName=o.barName;model.barFmt=o.barFmt||o.fmtY;}
  STATE.detail.charts.push(model);
  return model;
}

/* crosshair (十字游標,對應日期與價格) */
function drawCross(m,i){
  const r=m.wrap.getBoundingClientRect();if(!r.width)return;
  const px=xAtG(m.g,i)/m.g.W*r.width;
  const v=m.wrap.querySelector('.cross-v');v.style.left=px+'px';v.style.display='block';
  m.lines.forEach((sr,k)=>{const val=sr.values[i],dot=m.dots[k];
    if(val==null){dot.style.display='none';return;}
    dot.style.left=px+'px';dot.style.top=yAtG(m.g,val)+'px';dot.style.display='block';});
}
function hideCross(){
  STATE.detail.charts.forEach(m=>{const v=m.wrap.querySelector('.cross-v');if(v)v.style.display='none';m.dots.forEach(d=>d.style.display='none');});
  const tip=$('#cross-tip');if(tip)tip.classList.remove('show');
}
function initCrosshair(){
  const page=$('#page-detail');
  page.addEventListener('mousemove',e=>{
    const ms=STATE.detail.charts;if(!ms.length)return;
    const hov=ms.find(m=>{const r=m.wrap.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;});
    if(!hov){hideCross();return;}
    const r=hov.wrap.getBoundingClientRect();
    const vx=(e.clientX-r.left)/r.width*hov.g.W;
    let i=Math.round((vx-hov.g.PL)/hov.g.plotW*(hov.g.n-1));
    i=Math.max(0,Math.min(hov.g.n-1,i));
    ms.forEach(m=>drawCross(m,i));
    showCrossTip(ms,i,e);
  });
  page.addEventListener('mouseleave',hideCross);
}
function showCrossTip(models,i,e){
  const tip=$('#cross-tip');const date=(models[0].labels||[])[i]||'';
  let rows=`<div class="ct-d">${esc(date)}</div>`;
  models.forEach(m=>{
    if(m.candles){const cd=m.candles,oo=cd.open[i],hh=cd.high[i],ll=cd.low[i],cc=cd.close[i];
      if(cc!=null){const col=cc>=oo?'var(--up)':'var(--down)';
        rows+=`<div class="ct-r"><span><i style="background:${col}"></i>開高低收</span><span>${fmt(oo)} / ${fmt(hh)} / ${fmt(ll)} / ${fmt(cc)}</span></div>`;}}
    m.lines.forEach(sr=>{const val=sr.values[i];if(val==null)return;
      rows+=`<div class="ct-r"><span><i style="background:${sr.color}"></i>${esc(sr.name)}</span><span>${m.fmtY?m.fmtY(val):val.toFixed(2)}</span></div>`;});
    if(m.barVals&&m.barVals[i]!=null)
      rows+=`<div class="ct-r"><span><i style="background:#7a8090"></i>${esc(m.barName)}</span><span>${m.barFmt?m.barFmt(m.barVals[i]):m.barVals[i]}</span></div>`;
  });
  tip.innerHTML=rows;tip.classList.add('show');
  let x=e.clientX+16,y=e.clientY+16;
  if(x+190>innerWidth)x=e.clientX-190;if(y+160>innerHeight)y=e.clientY-160;
  tip.style.left=x+'px';tip.style.top=y+'px';
}
function legendHTML(items){return items.map(it=>`<span><i style="background:${it.color}"></i>${esc(it.name)}${it.val!=null?' '+it.val:''}</span>`).join('');}
function lastVal(arr,fmtFn){const v=[...arr].reverse().find(x=>x!=null);return v==null?'—':(fmtFn?fmtFn(v):v.toFixed(2));}

/* ---------- detail page ---------- */
function initDetail(){
  $('#detail-back').onclick=()=>showPage(STATE.prevPage||'dashboard');
  $('#d-timeframe').innerHTML=Object.keys(TF_LABELS).map(t=>`<button data-tf="${t}">${t}</button>`).join('');
  $('#d-timeframe').querySelectorAll('button').forEach(b=>b.onclick=()=>{
    STATE.detail.timeframe=b.dataset.tf;STATE.detail.custom=false;$('#d-range').classList.remove('show');loadDetail();});
  $('#d-overlays').innerHTML=OVERLAYS.map(o=>`<span class="chip" data-ov="${o.id}"><span class="swatch" style="background:${o.color}"></span>${o.label}</span>`).join('');
  $('#d-overlays').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
    const id=c.dataset.ov,arr=STATE.detail.overlays,idx=arr.indexOf(id);
    if(idx<0)arr.push(id);else arr.splice(idx,1);loadDetail();});
  [0,1].forEach(i=>{
    const sel=$('#d-panel-'+i);
    sel.innerHTML=PANELS.map(p=>`<option value="${p.id}">${p.label}</option>`).join('');
    sel.value=STATE.detail.panels[i];
    syncCustomSelect(sel);
    sel.onchange=()=>{
      STATE.detail.panels[i]=sel.value;
      if(STATE.detail.sym)renderDetail();
    };
  });
  // 線 / K 棒 切換(不需重抓,直接重繪)
  $('#d-charttype').querySelectorAll('button').forEach(b=>b.onclick=()=>{
    STATE.detail.chartType=b.dataset.ct;syncDetailControls();if(STATE.detail.sym&&STATE.detail.data)renderDetail();});
  // 自訂區間
  $('#d-custom-toggle').onclick=()=>$('#d-range').classList.toggle('show');
  $('#d-range').querySelectorAll('[data-quick]').forEach(b=>b.onclick=()=>{
    const y=b.dataset.quick;$('#d-start').value=`${y}-01-01`;$('#d-end').value=`${y}-12-31`;});
  $('#d-apply-range').onclick=()=>{
    const s=$('#d-start').value,e=$('#d-end').value;
    if(!s||!e){toast('請選擇起訖日期');return;}
    STATE.detail.custom=true;STATE.detail.start=s;STATE.detail.end=e;loadDetail();
  };
}
const TF_LABELS={'時':1,'天':1,'月':1,'六個月':1,'年':1};
function openDetail(sym,name){
  STATE.prevPage=STATE.page==='detail'?STATE.prevPage:STATE.page;
  STATE.detail.sym=sym;STATE.detail.name=name||sym;STATE.detail.autoAi=true;
  $('#d-sym').textContent=sym;$('#d-name').textContent=name||'';
  setAiBadge('');$('#ai-out').style.display='none';
  renderDetailHeader();   // 先清價格 header,避免殘留上一個標的的價格
  syncDetailControls();showPage('detail');loadDetail();
}
// 依當前標的的報價更新右上價格/漲跌 header;缺報價一律顯示「—」,永不殘留舊值。
function renderDetailHeader(){
  const q=STATE.quotes[STATE.detail.sym]||{},el=$('#d-price'),ce=$('#d-chg');
  if(!el||!ce)return;
  if(q.price!=null){const dir=q.change>0?'up':q.change<0?'down':'flat',ar=dir==='up'?'▲':dir==='down'?'▼':'—';
    el.textContent=fmt(q.price);el.className='p '+dir;
    ce.className='c '+dir;ce.textContent=q.change==null?'':`${ar} ${fmt(Math.abs(q.change))} (${fmt(Math.abs(q.changePct))}%)`;
  }else{el.textContent='—';el.className='p flat';ce.textContent='';ce.className='c flat';}
}
// 非觀察名單標的:STATE.quotes 尚無報價時補抓一次以更新 header(帶競態防護)。
function ensureDetailQuote(sym){
  const q=STATE.quotes[sym];
  if(q&&q.price!=null){renderDetailHeader();return;}
  api().get_quotes([sym]).then(res=>{
    if(STATE.detail.sym!==sym)return;   // 已切到別的標的,丟棄
    Object.assign(STATE.quotes,res||{});
    renderDetailHeader();
  }).catch(()=>{});
}
function setAiBadge(text){
  const el=$('#d-aibadge');
  const rec=text?((text.match(/建議[:：]?\s*(買入|觀望|賣出)/)||[])[1]||''):'';
  const buy=text?((text.match(/買入目標價[:：]?\s*\$?\s*([\d,\.]+)/)||[])[1]||''):'';
  if(!rec&&!buy){el.className='d-aibadge';el.innerHTML='';return;}
  el.className='d-aibadge show '+(rec==='買入'?'buy':rec==='賣出'?'sell':'');
  el.innerHTML=`🤖 AI:${rec||'—'}${buy?` <span class="tgt">買入目標 $${esc(buy)}</span>`:''}`;
}
function maybeAutoAi(){
  const provider=$('#ai-provider').value,key=(STATE.aicfg.keys||{})[provider];
  if(provider!=='none'&&key)runAi(false); // 進頁自動評估:當天已評估過會用快取,不重複燒額度
}
function syncDetailControls(){
  const cu=STATE.detail.custom;
  $('#d-timeframe').querySelectorAll('button').forEach(b=>b.classList.toggle('on',!cu&&b.dataset.tf===STATE.detail.timeframe));
  $('#d-custom-toggle').classList.toggle('on',cu);
  $('#d-charttype').querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.ct===STATE.detail.chartType));
  $('#d-overlays').querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',STATE.detail.overlays.includes(c.dataset.ov)));
  [0,1].forEach(s=>{
    const sel = $('#d-panel-'+s);
    if(sel) {
      sel.value=STATE.detail.panels[s]||'';
      syncCustomSelect(sel);
    }
  });
}
async function loadDetail(){
  const d=STATE.detail;if(!d.sym)return;const sym=d.sym;syncDetailControls();hideCross();
  d.loading=true;$('#d-price-chart').innerHTML='<div class="chart-msg">載入中…</div>';
  ensureDetailQuote(sym);   // 補抓非觀察名單標的的報價,更新右上 header
  const panels=d.panels.filter(Boolean);
  const st=d.custom?d.start:null,en=d.custom?d.end:null;
  let data;
  try{data=await api().get_chart_detail(d.sym,d.timeframe,d.overlays.slice(),panels,st,en);}
  catch(e){data={error:String(e)};}
  // STATE.detail 是同一參照(openDetail 就地改 .sym),必須比對進入時擷取的 sym 字串,
  // 否則快速切換標的時,舊標的的慢回應會覆蓋新標的畫面。
  if(STATE.detail.sym!==sym)return; // 已切換到別的標的,丟棄這個過期回應
  d.data=data;d.loading=false;
  renderDetail();
  if(STATE.detail.autoAi){STATE.detail.autoAi=false;maybeAutoAi();}
}
function renderSignals(sigs){
  if(!sigs||!sigs.length)return '<span class="sig-empty">目前無明顯技術訊號</span>';
  const arrow=dir=>dir==='bullish'?'▲':dir==='bearish'?'▼':'•';
  return sigs.map(s=>`<span class="sig-badge ${esc(s.dir)}">${arrow(s.dir)} ${esc(s.label)}<span class="n">· ${esc(s.note)}</span></span>`).join('');
}
function renderDetail(){
  const d=STATE.detail,data=d.data;
  STATE.detail.charts=[];hideCross();
  renderDetailHeader();
  if(!data||data.error){$('#d-price-chart').innerHTML=`<div class="chart-msg">無法載入資料 ${data&&data.error?'· '+esc(data.error):''}</div>`;
    $('#d-panel-chart-0').innerHTML='';$('#d-panel-chart-1').innerHTML='';$('#d-signals').innerHTML='';return;}
  $('#d-signals').innerHTML=renderSignals(data.signals);
  // price chart:線 or K 棒,均線疊圖皆以線繪於上層
  const overlayLines=[];
  OVERLAYS.forEach(o=>{if(data.overlays[o.id])overlayLines.push({name:o.label,color:o.color,values:data.overlays[o.id]});});
  const ovLegend=overlayLines.map(l=>({name:l.name,color:l.color,val:lastVal(l.values)}));
  const candle=STATE.detail.chartType==='candle'&&data.open;
  let opts,legend;
  if(candle){
    legend=[{name:'K 棒',color:'#9aa0b0',val:lastVal(data.close)}].concat(ovLegend);
    opts={height:250,labels:data.labels,candles:{open:data.open,high:data.high,low:data.low,close:data.close},lines:overlayLines,fmtY:v=>v.toFixed(2)};
  }else{
    legend=[{name:'收盤',color:'#e8c37a',val:lastVal(data.close)}].concat(ovLegend);
    opts={height:250,labels:data.labels,lines:[{name:'收盤',color:'#e8c37a',values:data.close,w:1.8}].concat(overlayLines),fmtY:v=>v.toFixed(2)};
  }
  $('#d-price-legend').innerHTML=legendHTML(legend);
  mountChart($('#d-price-chart'),opts);
  // panels
  [0,1].forEach(slot=>{
    const name=d.panels[slot],box=$('#d-panel-chart-'+slot);
    if(!name){box.innerHTML='<div class="chart-msg">未選擇指標</div>';return;}
    const pd=data.panels[name];
    if(!pd){box.innerHTML='<div class="chart-msg">此範圍資料不足</div>';return;}
    const r=buildPanelOpts(name,pd,data.labels);
    box.innerHTML=`<div class="ch-h"><div class="legend2">${r.legend}</div></div><div class="pchart"></div>`;
    mountChart(box.querySelector('.pchart'),r.opts);
  });
}
function buildPanelOpts(name,pd,labels){
  if(name==='volume'){
    const colors=pd.values.map((v,i)=>pd.up[i]?upColor():downColor());
    const lines=pd.ma?[{name:'均量20',color:'#e8c37a',values:pd.ma,w:1.4}]:[];
    const legend=legendHTML([{name:'成交量',color:'#7a8090'}].concat(pd.ma?[{name:'均量20',color:'#e8c37a',val:lastVal(pd.ma,fmtVol)}]:[]));
    return {legend,opts:{height:150,labels,bars:{values:pd.values,colors,baseline:'bottom'},lines,
      fmtY:fmtVol,barName:'成交量',barFmt:fmtVol}};
  }
  if(name==='macd'){
    const hist=pd.hist,colors=hist.map(v=>v==null?'#666':v>=0?upColor():downColor());
    const lines=[{name:'MACD',color:SERIES_COLOR.MACD,values:pd.series.MACD},{name:'Signal',color:SERIES_COLOR.Signal,values:pd.series.Signal}];
    const legend=legendHTML([{name:'MACD',color:SERIES_COLOR.MACD,val:lastVal(pd.series.MACD)},{name:'Signal',color:SERIES_COLOR.Signal,val:lastVal(pd.series.Signal)}]);
    return {legend,opts:{height:160,labels,bars:{values:hist,colors,baseline:'zero'},lines,zeroLine:true,
      fmtY:v=>v.toFixed(2),barName:'柱',barFmt:v=>v.toFixed(3)}};
  }
  const _udBand={'上軌':downColor(),'下軌':upColor()};   // 布林上/下軌跟隨漲跌慣例
  const lines=Object.entries(pd.series).map(([nm,vals])=>({name:nm,color:_udBand[nm]||SERIES_COLOR[nm]||'#e8c37a',values:vals}));
  const leg=lines.map(l=>({name:l.name,color:l.color,val:lastVal(l.values,name==='obv'?fmtVol:null)}));
  return {legend:legendHTML(leg),opts:{height:name==='bollinger'?200:150,labels,lines,guides:pd.guides||[],
    zeroLine:name==='obv',fmtY:name==='obv'?fmtVol:v=>v.toFixed(name==='kd'||name==='rsi'?0:2)}};
}

/* ---------- pie chart ---------- */
function svgPie(items){
  const total=items.reduce((s,x)=>s+x.value,0);
  if(total<=0)return '<div class="empty">尚無持倉市值</div>';
  const R=70,cx=80,cy=80;let a=-Math.PI/2,arcs='';
  items.forEach(it=>{
    const frac=it.value/total,a2=a+frac*2*Math.PI;
    if(items.length===1){arcs=`<circle cx="${cx}" cy="${cy}" r="${R}" fill="${it.color}"/>`;}
    else{const x1=cx+R*Math.cos(a),y1=cy+R*Math.sin(a),x2=cx+R*Math.cos(a2),y2=cy+R*Math.sin(a2),large=frac>0.5?1:0;
      arcs+=`<path d="M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${large} 1 ${x2.toFixed(2)},${y2.toFixed(2)} Z" fill="${it.color}"/>`;}
    a=a2;
  });
  const legend=items.map(it=>`<div><i style="background:${it.color}"></i>${esc(it.label)} <span style="color:var(--muted)">${(it.value/total*100).toFixed(1)}%</span></div>`).join('');
  return `<div class="pie-wrap"><svg width="160" height="160" viewBox="0 0 160 160">${arcs}<circle cx="${cx}" cy="${cy}" r="34" fill="#12131a"/></svg><div class="pie-legend">${legend}</div></div>`;
}

/* ---------- wallet ---------- */
async function loadWallet(){
  const w=STATE.wallet;if(w.loading)return;w.loading=true;
  if(!w.data)$('#wallet-summary').innerHTML='<div class="qcard"><div class="nm">載入中…</div></div>';  // 僅首次顯示;已有資料時靜默更新
  try{w.data=await api().wallet_holdings();}catch(e){w.data=null;}
  renderWallet();
  try{w.history=await api().wallet_history();}catch(e){w.history=null;}
  renderWalletCharts();
  w.loading=false;
}
function money(n,ccy,dec){
  if(n==null||isNaN(n))return'—';
  // 台股 tick 最小 0.01,TWD 顯示與 USD 一致取 2 位;呼叫端可用 dec 覆寫。
  const s=ccy==='TWD'?'NT$':'$',d=dec!=null?dec:2;
  return s+Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
}
function signMoney(n,ccy){
  if(n==null||isNaN(n))return'—';
  const s=ccy==='TWD'?'NT$':'$',d=2;
  return (n>=0?'+':'-')+s+Number(Math.abs(n)).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
}
// 碎股數量:最多 6 位小數、去尾零(券商碎股 5-6 位),整數不顯示小數點。
function qtyFmt(n){if(n==null||isNaN(n))return'—';return Number(n).toLocaleString('en-US',{maximumFractionDigits:6,minimumFractionDigits:0});}
// 兩段式刪除確認:首次點擊只把按鈕變成「確認刪除?」(紅色,3 秒後自動還原),
// 再點一次才真正執行 onConfirm。避免單擊即永久刪除(不用 window.confirm)。
function armDelete(btn,onConfirm){
  if(btn.dataset.armed){clearTimeout(+btn.dataset.armT);delete btn.dataset.armed;onConfirm();return;}
  const orig=btn.textContent;
  btn.dataset.armed='1';btn.classList.add('confirm');btn.textContent='確認刪除?';
  btn.dataset.armT=String(setTimeout(()=>{
    if(!btn.isConnected)return;
    delete btn.dataset.armed;btn.classList.remove('confirm');btn.textContent=orig;
  },3000));
}
const _dcls=v=>v>0?'up':v<0?'down':'flat',_arr=v=>v>0?'▲':v<0?'▼':'—';
/* 讓「目前持倉」框的高度對齊左側「持股比例」框 (窄螢幕堆疊時取消對齊) */
function syncHoldingsHeight(){
  const pie=document.querySelector('.pie-panel'),hs=$('#wallet-holdings');
  if(!pie||!hs)return;
  const panel=hs.closest('.panel');if(!panel)return;
  if(window.innerWidth<=1000){panel.style.height='';return;}
  panel.style.height=pie.offsetHeight+'px';
}
function renderWalletPie(sel,holdings,ccy){
  const items=(holdings||[]).filter(h=>h.market_value!=null&&h.market_value>0)
    .map((h,i)=>({label:h.symbol,value:h.market_value,color:PIE_COLORS[i%PIE_COLORS.length]}));
  $(sel).innerHTML=items.length?svgPie(items):`<div class="empty">尚無${ccy==='TWD'?'台股':'美股'}持倉市值</div>`;
}
function renderWallet(){
  const d=STATE.wallet.data;
  if(!d||!d.ccy){$('#wallet-summary').innerHTML='<div class="qcard"><div class="nm">無法載入</div></div>';return;}
  // 記錄三個清單的捲動位置,重建 innerHTML 後還原(避免 auto-refresh 把使用者捲回頂端)。
  const _scrollIds=['#wallet-holdings','#wallet-tx','#wallet-deposits'],_scroll={};
  _scrollIds.forEach(id=>{const el=$(id);if(el)_scroll[id]=el.scrollTop;});
  const U=d.ccy.USD,T=d.ccy.TWD,fx=d.fx;   // fx = 1 USD = fx TWD
  const ccy=STATE.wallet.ccy,b=d.ccy[ccy];
  // ----- 頂列「總計」兩張卡:依所選幣別換算 (美金→美金 / 台幣→台幣) -----
  // 能否換算跨幣別總計:有匯率,或另一幣別根本沒有資產;否則不硬折成 0(避免總資產靜默縮水)
  const otherEmpty=ccy==='USD'?(T.total_deposits===0&&T.portfolio_value===0)
                              :(U.total_deposits===0&&U.portfolio_value===0);
  const combinable=!!fx||otherEmpty;
  let totDep=null,totPv=null;
  if(combinable){
    if(ccy==='USD'){const k=fx?1/fx:0;totDep=U.total_deposits+T.total_deposits*k;totPv=U.portfolio_value+T.portfolio_value*k;}
    else{const k=fx||0;totDep=T.total_deposits+U.total_deposits*k;totPv=T.portfolio_value+U.portfolio_value*k;}
  }
  const totRet=(combinable&&totDep>0)?(totPv-totDep)/totDep*100:0;
  const totDep$=combinable?money(totDep,ccy):'—',totPv$=combinable?money(totPv,ccy):'—';
  const convLabel=ccy==='TWD'?'折合台幣':'折合美金';
  const fxNote=fx?(' · 匯率 1 USD≈'+fmt(fx,3)+' TWD'):(combinable?'':' · ⚠ 匯率無法取得,暫不換算');
  // ----- 頂列:當日損益 (依所選幣別 = 美股/台股) + 總計 + 美金 + 台幣 -----
  const dc=b.day_change||0,dcp=b.day_change_pct||0,dcMkt=ccy==='TWD'?'台股':'美股';
  const dcDateNote=b.day_date?(`交易日 ${b.day_date}${b.prev_date?' · 較 '+b.prev_date+' 收盤':''}`):'當日持倉市值變動';
  // 現金餘額 = 投入資金 − 持倉成本 + 已實現損益 = portfolio_value − total_value
  const usdCash=U.portfolio_value-U.total_value,twdCash=T.portfolio_value-T.total_value,selCash=b.portfolio_value-b.total_value;
  markNoAnim($('#wallet-hero-grid'));
  $('#wallet-hero-grid').innerHTML=`
    <div class="qcard hero daychange"><div class="nm">當日損益 Day Change · ${dcMkt}</div><div class="row"><div class="price ${_dcls(dc)}">${signMoney(dc,ccy)}</div><div class="chg ${_dcls(dc)}" style="white-space:nowrap;flex-shrink:0">${_arr(dcp)} ${fmt(Math.abs(dcp))}%</div></div><div class="ccy-sub">${dcDateNote}</div></div>
    <div class="qcard hero"><div class="nm">總投入資金</div><div class="row"><div class="price">${totDep$}</div></div><div class="ccy-sub">${convLabel}</div></div>
    <div class="qcard hero"><div class="nm">持有總錢包價值</div><div class="row"><div class="price ${_dcls(totRet)}">${totPv$}</div>${combinable?`<div class="chg ${_dcls(totRet)}" style="white-space:nowrap;flex-shrink:0">${_arr(totRet)} ${fmt(Math.abs(totRet||0))}%</div>`:''}</div><div class="ccy-sub">${convLabel}${fxNote}</div></div>`;
  markNoAnim($('#wallet-ccy-grid'));
  $('#wallet-ccy-grid').innerHTML=`
    <div class="qcard"><div class="nm">💵 美金投入資金</div><div class="row"><div class="price">${money(U.total_deposits,'USD')}</div></div></div>
    <div class="qcard"><div class="nm">💵 持有美金錢包價值</div><div class="row"><div class="price ${_dcls(U.portfolio_return_pct)}">${money(U.portfolio_value,'USD')}</div><div class="chg ${_dcls(U.portfolio_return_pct)}">${_arr(U.portfolio_return_pct)} ${fmt(Math.abs(U.portfolio_return_pct||0))}%</div></div></div>
    <div class="qcard"><div class="nm">🇹🇼 台幣投入資金</div><div class="row"><div class="price">${money(T.total_deposits,'TWD')}</div></div></div>
    <div class="qcard"><div class="nm">🇹🇼 持有台幣錢包價值</div><div class="row"><div class="price ${_dcls(T.portfolio_return_pct)}">${money(T.portfolio_value,'TWD')}</div><div class="chg ${_dcls(T.portfolio_return_pct)}">${_arr(T.portfolio_return_pct)} ${fmt(Math.abs(T.portfolio_return_pct||0))}%</div></div></div>`;
  // 收合列(捲動時顯示):當日/總投入/總價值/現金 + 幣別
  $('#wallet-hero-compact').innerHTML=`
    <span class="hc-item"><span class="hc-l">當日</span><span class="hc-v ${_dcls(dc)}">${signMoney(dc,ccy)}</span></span>
    <span class="hc-item"><span class="hc-l">總投入</span><span class="hc-v">${totDep$}</span></span>
    <span class="hc-item"><span class="hc-l">總價值</span><span class="hc-v ${_dcls(totRet)}">${totPv$}</span></span>
    <span class="hc-item"><span class="hc-l">現金</span><span class="hc-v">${money(selCash,ccy)}</span></span>
    <span class="hc-ccy">${ccy==='TWD'?'台幣':'美金'}</span>`;
  // ----- 持股比例:美股 / 台股 兩個圓餅 + 佔總錢包比例 -----
  renderWalletPie('#wallet-pie-usd',U.holdings,'USD');
  renderWalletPie('#wallet-pie-twd',T.holdings,'TWD');
  // 佔比 = 各幣別「持有錢包價值」折同一幣別後 / 總計 (美股% + 台股% = 100%)
  const pvU=U.portfolio_value,pvT=(fx?T.portfolio_value/fx:0),pvSum=pvU+pvT;
  const canShare=pvSum>0&&(fx||T.portfolio_value===0);
  $('#pie-usd-share').textContent=canShare?fmt(pvU/pvSum*100,1)+'%':'—';
  $('#pie-twd-share').textContent=canShare?fmt(pvT/pvSum*100,1)+'%':'—';
  // ----- 以下依所選幣別呈現 -----
  $('#wallet-ccy-label').textContent=ccy==='TWD'?'台幣 TWD':'美金 USD';
  const pnl=b.total_pnl,pct=b.total_cost?pnl/b.total_cost*100:0,rp=b.total_realized_pnl||0;
  markNoAnim($('#wallet-summary'));
  $('#wallet-summary').innerHTML=`
    <div class="qcard"><div class="nm">總市值</div><div class="row"><div class="price">${money(b.total_value,ccy)}</div></div></div>
    <div class="qcard" title="= 投入資金 − 持倉成本 + 已實現損益"><div class="nm">現金餘額</div><div class="row"><div class="price">${money(selCash,ccy)}</div></div></div>
    <div class="qcard"><div class="nm">總成本</div><div class="row"><div class="price">${money(b.total_cost,ccy)}</div></div></div>
    <div class="qcard"><div class="nm">未實現損益</div><div class="row"><div class="price ${_dcls(pnl)}">${signMoney(pnl,ccy)}</div><div class="chg ${_dcls(pnl)}">${_arr(pnl)} ${fmt(Math.abs(pct))}%</div></div></div>
    <div class="qcard clk" data-rpnl tabindex="0" role="button"><div class="nm">已實現損益 ›</div><div class="row"><div class="price ${_dcls(rp)}">${signMoney(rp,ccy)}</div></div></div>
    <div class="qcard"><div class="nm">持有檔數</div><div class="row"><div class="price">${b.holdings.length}</div></div></div>`;
  $('#wallet-hcount').textContent=`${b.holdings.length} 檔`;
  const hb=$('#wallet-holdings');
  if(!b.holdings.length)hb.innerHTML=`<div class="empty">尚無${ccy==='TWD'?'台股':'美股'}持倉 · 於下方新增交易</div>`;
  else{hb.innerHTML=b.holdings.map(h=>{
    const p=h.pnl,dr=p==null?'flat':_dcls(p),a=p>0?'▲':p<0?'▼':'';
    const rpl=h.realized_pnl||0;
    return `<div class="hrow clk" data-open="${esc(h.symbol)}" data-name="${esc(h.name)}">
      <span class="k">${esc(h.symbol)}</span>
      <span class="sub">${qtyFmt(h.qty)} 股 · 均價 ${money(h.avg_cost,ccy)}</span>
      <span class="mv">市值<br>${h.market_value==null?'—':money(h.market_value,ccy)}</span>
      <span class="pnl ${dr}">${p==null?'—':signMoney(p,ccy)}<br><span style="font-size:11px">${h.pnl_pct==null?'':a+' '+fmt(Math.abs(h.pnl_pct))+'%'}</span></span>
      <span class="rpnl ${_dcls(rpl)}" title="已實現損益">${rpl===0?'—':signMoney(rpl,ccy)}</span></div>`;
  }).join('');
  hb.querySelectorAll('.hrow[data-open]').forEach(r=>{r.onclick=()=>openDetail(r.dataset.open,r.dataset.name);keyActivatable(r);});}
  // 錢包資金紀錄 (所選幣別)
  const deps=(d.deposits||[]).filter(x=>(x.currency||'USD')===ccy);
  $('#wallet-depcount').textContent=`${deps.length} 筆`;
  const db=$('#wallet-deposits');
  if(!deps.length)db.innerHTML='<div class="empty">尚無資金紀錄</div>';
  else{db.innerHTML=deps.map(dep=>{const isDep=dep.amount>=0;
    return `<div class="txrow">
      <span class="side ${isDep?'buy':'sell'}">${isDep?'投入':'收回'}</span>
      <span class="g" style="min-width:120px">${money(Math.abs(dep.amount),ccy)}</span>
      <span class="g">${esc(dep.date)}</span>
      <span class="g" style="flex:1">${esc(dep.note||'')}</span>
      <span class="del" data-deldep="${dep.id}">🗑 刪除</span></div>`;}).join('');
    db.querySelectorAll('[data-deldep]').forEach(bn=>bn.onclick=()=>armDelete(bn,async()=>{await api().deposit_delete(+bn.dataset.deldep);loadWallet();}));}
  // 交易紀錄 (所選幣別,依日期分組)
  const txs=(d.transactions||[]).filter(t=>(t.currency||'USD')===ccy);
  $('#wallet-txcount').textContent=`${txs.length} 筆`;
  const tb=$('#wallet-tx');
  if(!txs.length)tb.innerHTML='<div class="empty">尚無交易紀錄</div>';
  else{
    const groups=[],gi={};
    txs.forEach(t=>{const dt=t.date||'—';if(!(dt in gi)){gi[dt]=groups.length;groups.push({date:dt,items:[]});}groups[gi[dt]].items.push(t);});
    tb.innerHTML=groups.map(gp=>{
      const rows=gp.items.map(t=>{const buy=t.side?t.side==='buy':t.quantity>=0;
        return `<div class="txrow"><span class="side ${buy?'buy':'sell'}">${buy?'買':'賣'}</span>
          <span style="min-width:56px;font-weight:800">${esc(t.symbol)}</span>
          <span class="g">${qtyFmt(Math.abs(t.quantity))} 股 @ ${money(t.price,ccy)}</span>
          <span class="del" data-del="${t.id}">🗑 刪除</span></div>`;}).join('');
      return `<div class="txgroup"><div class="txgroup-head"><span class="txgroup-date">${esc(gp.date)}</span><span class="txgroup-count">${gp.items.length} 筆</span></div><div class="txgroup-body">${rows}</div></div>`;
    }).join('');
    tb.querySelectorAll('.del').forEach(bn=>bn.onclick=()=>armDelete(bn,async()=>{await api().wallet_delete(+bn.dataset.del);loadWallet();}));}
  _scrollIds.forEach(id=>{const el=$(id);if(el&&_scroll[id]!=null)el.scrollTop=_scroll[id];});
  requestAnimationFrame(syncHoldingsHeight);
}
function renderWalletCharts(){
  const ccy=STATE.wallet.ccy,label=ccy==='TWD'?'台幣':'美金';
  const hAll=STATE.wallet.history,h=hAll?hAll[ccy]:null;
  const vc=$('#wallet-value-chart'),pc=$('#wallet-pnl-chart');
  $('#wv-title').textContent=`歷史${label}錢包價值`;
  $('#wpnl-title').textContent=`歷史${label}每日交易損益(按市值計)`;
  STATE.wallet.charts=[];
  if(!h||!h.dates||!h.dates.length){vc.innerHTML='<div class="chart-msg">尚無資料</div>';pc.innerHTML='<div class="chart-msg">尚無資料</div>';return;}
  const labels=h.dates.map(x=>x.slice(2)),color=ccy==='TWD'?'#5bc0de':'#e8c37a';
  mountWalletChart(vc,{height:200,labels,lines:[{name:`持有${label}錢包價值`,color,values:h.portfolio_value,w:1.8}],fmtY:fmtVol});
  $('#wv-legend').innerHTML=legendHTML([{name:`持有${label}錢包價值`,color,val:fmtVol(lastVal(h.portfolio_value))}]);
  const colors=h.daily_pnl.map(v=>v>=0?upColor():downColor());
  drawStaticChart(pc,{height:180,labels,bars:{values:h.daily_pnl,colors,baseline:'zero'},zeroLine:true,fmtY:fmtVol});
}
function drawStaticChart(box,o){
  const g=chartGeo(o,box.clientWidth);
  if(!g){box.innerHTML='<div class="chart-msg">資料不足</div>';return;}
  box.innerHTML=`<div class="chartwrap" style="height:${o.height}px">${chartSVG(o,g)}</div>`;
}
function mountWalletChart(boxEl,o){
  const g=chartGeo(o,boxEl.clientWidth);
  if(!g){boxEl.innerHTML='<div class="chart-msg">此範圍資料不足以計算</div>';return null;}
  boxEl.innerHTML=`<div class="chartwrap" style="height:${o.height}px">${chartSVG(o,g)}<div class="cross-v"></div></div>`;
  const wrap=boxEl.querySelector('.chartwrap');
  const lines=o.lines||[];
  const dots=lines.map(sr=>{const d=document.createElement('div');d.className='cross-dot';d.style.background=sr.color;wrap.appendChild(d);return d;});
  const model={wrap,g,lines,labels:o.labels,dots,fmtY:o.fmtY};
  STATE.wallet.charts.push(model);
  return model;
}
// 視窗尺寸改變時,以新的容器寬重繪當前頁圖表(debounce 200ms),避免文字被拉伸。
function redrawCurrentCharts(){
  if(STATE.page==='detail'){if(STATE.detail.sym&&STATE.detail.data)renderDetail();}
  else if(STATE.page==='wallet'){if(STATE.wallet.history)renderWalletCharts();}
}
let _chartResizeTimer=null;
window.addEventListener('resize',()=>{clearTimeout(_chartResizeTimer);_chartResizeTimer=setTimeout(redrawCurrentCharts,200);});
function hideWalletCross(){
  STATE.wallet.charts.forEach(m=>{const v=m.wrap.querySelector('.cross-v');if(v)v.style.display='none';m.dots.forEach(d=>d.style.display='none');});
  const tip=$('#cross-tip');if(tip)tip.classList.remove('show');
}
function initWalletCrosshair(){
  const page=$('#page-wallet');
  page.addEventListener('mousemove',e=>{
    const ms=STATE.wallet.charts;if(!ms.length)return;
    const hov=ms.find(m=>{const r=m.wrap.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;});
    if(!hov){hideWalletCross();return;}
    const r=hov.wrap.getBoundingClientRect();
    const vx=(e.clientX-r.left)/r.width*hov.g.W;
    let i=Math.round((vx-hov.g.PL)/hov.g.plotW*(hov.g.n-1));
    i=Math.max(0,Math.min(hov.g.n-1,i));
    ms.forEach(m=>drawCross(m,i));
    showCrossTip(ms,i,e);
  });
  page.addEventListener('mouseleave',hideWalletCross);
}
/* 錢包幣別切換 (美金 / 台幣) */
function applyWalletCcyUI(){
  const sw=$('#wallet-ccy-switch');if(!sw)return;
  sw.dataset.ccy=STATE.wallet.ccy;
  sw.querySelectorAll('.ms-btn').forEach(b=>b.classList.toggle('on',b.dataset.ccy===STATE.wallet.ccy));
}
function setWalletCcy(c){
  if((c!=='USD'&&c!=='TWD')||c===STATE.wallet.ccy)return;
  STATE.wallet.ccy=c;
  try{localStorage.setItem('walletCcy',c);}catch(e){}
  applyWalletCcyUI();
  if(STATE.wallet.data)renderWallet();
  renderWalletCharts();
  // 反向同步全域市場:USD→us, TWD→tw
  if(!_syncing){
    _syncing=true;
    const m=c==='TWD'?'tw':'us';
    if(m!==STATE.market) setMarket(m);
    _syncing=false;
  }
}
function initWalletCcySwitch(){
  // 從全域 market 衍生幣別,確保啟動時三顆按鈕一致
  STATE.wallet.ccy=STATE.market==='tw'?'TWD':'USD';
  applyWalletCcyUI();
  $('#wallet-ccy-switch')?.querySelectorAll('.ms-btn').forEach(b=>b.onclick=()=>setWalletCcy(b.dataset.ccy));
}
/* 新增交易:代號搜尋下拉 (模仿主頁面搜尋,方便確認代號正確) */
let wSymTimer=null;
function initWalletSymSearch(){
  const inp=$('#w-sym'),res=$('#w-results');if(!inp||!res)return;
  inp.addEventListener('input',()=>{
    STATE.wallet.symName='';
    clearTimeout(wSymTimer);const q=inp.value.trim();
    if(q.length<1){res.classList.remove('show');return;}
    wSymTimer=setTimeout(async()=>{
      const list=await api().search_symbol(q);
      if(!list.length){res.innerHTML='<div class="rrow"><span class="rn">查無結果</span></div>';res.classList.add('show');return;}
      res.innerHTML=list.map(r=>`<div class="rrow" data-sym="${esc(r.sym)}" data-name="${esc(r.name)}">
        <span class="rs">${esc(r.sym)}</span><span class="rn">${esc(r.name)}</span>
        <span class="re">${esc(r.exch||r.type||'')}</span><span class="radd">＋</span></div>`).join('');
      res.classList.add('show');
      res.querySelectorAll('.rrow[data-sym]').forEach(row=>{row.onclick=()=>{
        inp.value=row.dataset.sym;STATE.wallet.symName=row.dataset.name||'';
        res.classList.remove('show');$('#w-qty').focus();
      };keyActivatable(row);});
    },260);
  });
  document.addEventListener('click',e=>{if(!e.target.closest('.w-sym-wrap'))res.classList.remove('show');});
}
// 已實現損益明細 modal(沿用 #ai-modal 的 .modal-bg/.show 模式)。
function openRealizedModal(){
  const b=STATE.wallet.data&&STATE.wallet.data.ccy&&STATE.wallet.data.ccy[STATE.wallet.ccy];
  const detail=(b&&b.realized_detail)||[],ccy=STATE.wallet.ccy,box=$('#rpnl-list');
  if(!detail.length)box.innerHTML='<div class="empty">尚無已實現損益</div>';
  else box.innerHTML=detail.map(d=>`<div class="rpnl-row">
      <span class="rp-sym">${esc(d.symbol)}</span>
      <span class="rp-nm">${esc(d.name||'')}${d.closed?'<span class="rp-closed">已平倉</span>':''}</span>
      <span class="rp-val ${_dcls(d.realized_pnl)}">${signMoney(d.realized_pnl,ccy)}</span>
    </div>`).join('');
  $('#rpnl-modal').classList.add('show');
}
function closeRealizedModal(){$('#rpnl-modal').classList.remove('show');}
// 錢包資金概況 sticky:捲動超過門檻收合成緊湊摘要,騰出內容區(向上捲回展開)。
function initWalletSticky(){
  const main=document.querySelector('.main'),sticky=$('#wallet-sticky');
  if(!main||!sticky)return;
  main.addEventListener('scroll',()=>{
    if(STATE.page!=='wallet')return;
    sticky.classList.toggle('collapsed',main.scrollTop>200);
  });
}
function initWalletForm(){
  initWalletCcySwitch();
  initWalletSymSearch();
  initWalletSticky();
  // 已實現損益卡點擊 → 明細 modal(委派於穩定容器 #wallet-summary,免每次重繪重綁)。
  $('#wallet-summary').addEventListener('click',e=>{if(e.target.closest('[data-rpnl]'))openRealizedModal();});
  $('#wallet-summary').addEventListener('keydown',e=>{
    if((e.key==='Enter'||e.key===' ')&&e.target.closest('[data-rpnl]')){e.preventDefault();openRealizedModal();}});
  $('#rpnl-close').onclick=closeRealizedModal;
  $('#rpnl-modal').onclick=e=>{if(e.target.id==='rpnl-modal')closeRealizedModal();};   // 點背景關閉
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#rpnl-modal').classList.contains('show'))closeRealizedModal();});
  window.addEventListener('resize',()=>{if(STATE.page==='wallet')syncHoldingsHeight();});
  $('#w-date').value=(STATE.today||new Date().toISOString().slice(0,10));
  $('#w-add').onclick=async()=>{
    const sym=$('#w-sym').value.trim(),qty=$('#w-qty').value,price=$('#w-price').value,dt=$('#w-date').value;
    const side=$('#w-side').value;
    if(!sym||qty===''||price===''||!dt){toast('請填寫完整');return;}
    const name=(STATE.wallet.symName&&STATE.wallet.symName)||'';
    const r=await api().wallet_add(sym,name,qty,price,dt,side);
    if(!r.ok){toast(r.error||'新增失敗');return;}
    $('#w-sym').value='';$('#w-qty').value='';$('#w-price').value='';STATE.wallet.symName='';
    // 自動切換到該標的所屬幣別,方便立即檢視
    setWalletCcy(/\.TWO?$/i.test(sym.toUpperCase())?'TWD':'USD');
    toast('已新增交易');loadWallet();
  };
  $('#dep-date').value=(STATE.today||new Date().toISOString().slice(0,10));
  const depCcySel=$('#dep-ccy');if(depCcySel){depCcySel.value=STATE.wallet.ccy;syncCustomSelect&&syncCustomSelect(depCcySel);}
  $('#dep-add').onclick=async()=>{
    const side=$('#dep-side').value,ccy=$('#dep-ccy').value,amt=$('#dep-amt').value,dt=$('#dep-date').value,note=$('#dep-note').value;
    if(amt===''||!dt){toast('請填寫金額與日期');return;}
    const r=await api().deposit_add(amt,dt,note,side,ccy);
    if(!r.ok){toast(r.error||'新增失敗');return;}
    $('#dep-amt').value='';$('#dep-note').value='';
    setWalletCcy(ccy);
    toast('已新增紀錄');loadWallet();
  };
  const isCollapsed=localStorage.getItem('walletTxCollapsed')==='1';
  const txBody=$('#tx-body'),txArrow=$('#tx-arrow');
  if(isCollapsed){txBody.classList.add('collapsed');txArrow.style.transform='rotate(-90deg)';}
  $('#tx-toggle').onclick=()=>{
    const willCollapse=!txBody.classList.contains('collapsed');
    txBody.classList.toggle('collapsed',willCollapse);
    txArrow.style.transform=willCollapse?'rotate(-90deg)':'rotate(0deg)';
    localStorage.setItem('walletTxCollapsed',willCollapse?'1':'0');
  };
  const depCollapsed=localStorage.getItem('walletDepCollapsed')==='1';
  const depBody=$('#dep-body'),depArrow=$('#dep-arrow');
  if(depCollapsed){depBody.classList.add('collapsed');depArrow.style.transform='rotate(-90deg)';}
  $('#dep-toggle').onclick=()=>{
    const willCollapse=!depBody.classList.contains('collapsed');
    depBody.classList.toggle('collapsed',willCollapse);
    depArrow.style.transform=willCollapse?'rotate(-90deg)':'rotate(0deg)';
    localStorage.setItem('walletDepCollapsed',willCollapse?'1':'0');
  };
}

/* ---------- settings ---------- */
const PROVIDERS=[{id:'claude',label:'Claude (Anthropic)'},{id:'openai',label:'OpenAI'},{id:'gemini',label:'Gemini (Google)'}];
function renderSettingsKeys(){
  const keys=STATE.aicfg.keys||{};
  $('#set-keys').innerHTML=PROVIDERS.map(p=>`
    <div class="set-krow">
      <span class="plabel">${p.label}</span>
      <input type="password" id="sk-${p.id}" placeholder="${keys[p.id]?'●●●● 已設定 · 輸入可覆蓋':'貼上 API Key'}" value="">
      <button class="btn gold" data-save="${p.id}" style="padding:8px 14px">儲存</button>
      <button class="btn" data-clear="${p.id}" style="padding:8px 14px">刪除</button>
    </div>`).join('');
  $('#set-keys').querySelectorAll('[data-save]').forEach(b=>b.onclick=()=>{
    const id=b.dataset.save,val=$('#sk-'+id).value.trim();
    if(!val){toast('請先輸入金鑰');return;}
    STATE.aicfg.keys={...(STATE.aicfg.keys||{}),[id]:val};persistAi();renderSettingsKeys();updateAiRunState();
    toast(PROVIDERS.find(p=>p.id===id).label+' 金鑰已儲存');
  });
  $('#set-keys').querySelectorAll('[data-clear]').forEach(b=>b.onclick=()=>{
    const id=b.dataset.clear,k={...(STATE.aicfg.keys||{})};delete k[id];STATE.aicfg.keys=k;persistAi();renderSettingsKeys();updateAiRunState();toast('已刪除金鑰');
  });
}
function loadSettings(){renderSettingsKeys();}
/* ---------- Tick flash: price change highlight ---------- */
let _prevPrices={};
function snapshotPrices(){_prevPrices={};for(const[s,q]of Object.entries(STATE.quotes)){if(q.price!=null)_prevPrices[s]=q.price;}}
function flashTicks(){
  document.querySelectorAll('.qcard[data-sym]').forEach(card=>{
    const sym=card.dataset.sym,oldP=_prevPrices[sym],newP=(STATE.quotes[sym]||{}).price;
    if(oldP!=null&&newP!=null&&oldP!==newP){
      card.classList.add(newP>oldP?'tick-up':'tick-down');
      setTimeout(()=>card.classList.remove('tick-up','tick-down'),650);
    }
  });
}
/* ---------- Performance mode ---------- */
function initPerfMode(){
  const prefersReduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const stored=localStorage.getItem('perfLow');
  const low=stored!=null?(stored==='1'):prefersReduced;
  document.documentElement.dataset.perf=low?'low':'';
  const cb=$('#perf-toggle');if(cb){cb.checked=low;cb.onchange=()=>{
    const v=cb.checked;document.documentElement.dataset.perf=v?'low':'';
    try{localStorage.setItem('perfLow',v?'1':'0');}catch(e){}
  };}
}
function initSettings(){
  const tsel=$('#theme-sel');
  if(tsel){
    tsel.value=localStorage.getItem('theme')||'system';
    tsel.onchange=()=>{
      localStorage.setItem('theme',tsel.value);
      initTheme();
    };
  }
  const usel=$('#updown-sel');
  if(usel){
    usel.value=localStorage.getItem('updown')==='tw'?'tw':'us';
    usel.onchange=()=>{
      localStorage.setItem('updown',usel.value);
      initUpDown();
      // 重繪跟隨漲跌色的畫面(卡片/圖表由硬著色處讀新色)
      renderIndices();renderWatchlist();renderGoldPrices();
      if(STATE.page==='detail'&&STATE.detail.sym)renderDetail();
      if(STATE.page==='wallet'&&STATE.wallet.data){renderWallet();renderWalletCharts();}
    };
  }
  // 勾選「API 金鑰」時提示備份檔含明文金鑰(切換即時反映)。
  const keysChk=$('#io-checks').querySelector('input[value="keys"]'),keysWarn=$('#io-keys-warn');
  if(keysChk&&keysWarn){const syncKeysWarn=()=>keysWarn.style.display=keysChk.checked?'block':'none';keysChk.onchange=syncKeysWarn;syncKeysWarn();}
  $('#export-btn').onclick=async()=>{
    const secs=[...$('#io-checks').querySelectorAll('input:checked')].map(c=>c.value);
    if(!secs.length){toast('請至少勾選一項');return;}
    $('#io-status').textContent='匯出中…';
    let r;try{r=await api().export_data(secs);}catch(e){r={ok:false,error:String(e)};}
    $('#io-status').textContent=r.ok?('已匯出:'+r.path):('匯出:'+(r.error||'失敗'));
  };
  $('#import-btn').onclick=async()=>{
    const secs=[...$('#io-checks').querySelectorAll('input:checked')].map(c=>c.value);
    if(!secs.length){toast('請至少勾選一項');return;}
    $('#io-status').textContent='匯入中…';
    let r;try{r=await api().import_data(secs);}catch(e){r={ok:false,error:String(e)};}
    if(!r.ok){$('#io-status').textContent='匯入:'+(r.error||'失敗');return;}
    $('#io-status').textContent='已匯入:'+((r.applied||[]).join('、')||'(無對應項目)');
    STATE.watchlists.us=await api().get_watchlist('us');STATE.aicfg=await api().get_ai_config();
    renderWatchlist();renderSettingsKeys();updateAiRunState();refreshEarnings();
    if(STATE.wallet.data)loadWallet();
    toast('已匯入，App 已更新');
  };
  const btnClearTemp = $('#btn-clear-temp');
  if(btnClearTemp){
    btnClearTemp.onclick = async ()=>{
      if(!confirm('這將清除所有的快取檔案與介面個人化設定 (需重新啟動)，確定要清除嗎？')) return;
      localStorage.clear();
      sessionStorage.clear();
      await api().clear_temp();
      toast('暫存檔已清除！系統將於 3 秒後重新啟動');
      setTimeout(()=> location.reload(), 3000);
    };
  }
}

/* ---------- AI 分析 ---------- */
async function initAi(){
  const cfg=await api().get_ai_config();STATE.aicfg=cfg;
  $('#ai-provider').value=cfg.provider||'none';
  $('#ai-prompt').value=cfg.prompt||'';
  $('#ai-provider').onchange=()=>{STATE.aicfg.provider=$('#ai-provider').value;persistAi();updateAiRunState();};
  $('#ai-prompt').addEventListener('change',()=>{STATE.aicfg.prompt=$('#ai-prompt').value;persistAi();});
  $('#ai-settings-btn').onclick=openAiModal;
  $('#ai-modal-cancel').onclick=()=>$('#ai-modal').classList.remove('show');
  $('#ai-modal-save').onclick=saveAiModal;
  $('#ai-run').onclick=()=>runAi(false);
  $('#ai-refresh').onclick=()=>runAi(true);
  updateAiRunState();
}
// 不回存 models,避免把當下的預設代號釘死在設定檔;model 由程式最新預設決定,
// 進階使用者仍可手動編輯 ai_config.json 的 models 欄位覆寫(已淘汰代號會被忽略)。
function persistAi(){api().save_ai_config({provider:STATE.aicfg.provider,prompt:STATE.aicfg.prompt,
  keys:STATE.aicfg.keys||{}});}
function updateAiRunState(){
  const on=$('#ai-provider').value!=='none';
  $('#ai-run').disabled=!on;$('#ai-refresh').disabled=!on;
  $('#ai-status').textContent=on?'':'選單為 None 時不輸出';
}
function openAiModal(){
  const k=STATE.aicfg.keys||{};
  $('#k-claude').value=k.claude||'';$('#k-openai').value=k.openai||'';$('#k-gemini').value=k.gemini||'';
  $('#ai-modal').classList.add('show');
}
function saveAiModal(){
  STATE.aicfg.keys={claude:$('#k-claude').value.trim(),openai:$('#k-openai').value.trim(),gemini:$('#k-gemini').value.trim()};
  persistAi();$('#ai-modal').classList.remove('show');toast('API 金鑰已儲存(僅存本機)');
}
// force=false:當天若已評估過會回傳快取(不呼叫 API);force=true:強制重新評估。
async function runAi(force){
  const d=STATE.detail,provider=$('#ai-provider').value;
  if(provider==='none'){toast('請先選擇 AI 供應商');return;}
  if(!d.sym)return;
  const prompt=$('#ai-prompt').value;STATE.aicfg.prompt=prompt;persistAi();
  $('#ai-status').innerHTML='<span class="spin">⟳</span> 分析中…';
  $('#ai-run').disabled=true;$('#ai-refresh').disabled=true;
  const out=$('#ai-out');out.style.display='none';out.className='ai-out';
  const st=d.custom?d.start:null,en=d.custom?d.end:null;
  let res;
  try{res=await api().ai_analyze(provider,prompt,d.sym,d.timeframe,st,en,!!force);}
  catch(e){res={ok:false,error:String(e)};}
  $('#ai-run').disabled=false;$('#ai-refresh').disabled=false;
  out.style.display='block';
  if(!res||!res.ok){out.textContent='⚠ '+((res&&res.error)||'分析失敗');setAiBadge('');$('#ai-status').textContent='';return;}
  out.textContent=res.text||'(無輸出)';
  const t=res.text||'';
  if(/建議[:：]?\s*買入/.test(t))out.classList.add('buy');
  else if(/建議[:：]?\s*賣出/.test(t))out.classList.add('sell');
  setAiBadge(t);
  const modelTxt=res.model?('模型 '+res.model):'';
  $('#ai-status').textContent=res.cached?('今日已評估 · 點「↻ 重新評估」可更新　'+modelTxt):modelTxt;
}

/* ---------- router ---------- */
function showPage(id){
  STATE.page=id;
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+id));
  document.querySelectorAll('.nav-item[data-page]').forEach(n=>n.classList.toggle('on',n.dataset.page===id));
  $('#pg-title').textContent=PAGE_META[id].t;$('#pg-desc').textContent=PAGE_META[id].d;
  window.scrollTo?.(0,0);$('.main')?.scrollTo?.(0,0);
  if(id==='wallet')loadWallet();
  else if(id==='settings')loadSettings();
}
function initNav(){
  document.querySelectorAll('.nav-item[data-page]').forEach(n=>n.onclick=()=>showPage(n.dataset.page));
}

/* ---------- data flow ---------- */
async function loadStatic(){
  const ev=await api().get_events('us');STATE.events=ev.events;STATE.today=ev.today;
  const evtw=await api().get_events('tw');STATE.twEvents=evtw.events;
  STATE.alerts=await api().get_alerts();
  STATE.watchlists.us=await api().get_watchlist('us');
  STATE.watchlists.tw=await api().get_watchlist('tw');
  renderIndices();renderWatchlist();renderGoldPrices();
  renderEvents();renderAlerts();
  renderDashEvents();renderFullCalendar();renderCustomEvents();
  refreshEarnings();
}
async function refreshEarnings(){
  const syms=activeWatchlist().map(w=>w.sym);
  if(!syms.length){STATE.earnings={};renderDashEvents();renderFullCalendar();return;}
  api().get_earnings(syms).then(res=>{STATE.earnings=res;renderDashEvents();renderFullCalendar();});
}
// 目前需要追蹤的報價標的(大盤 + 黃金 + 觀察名單,合併去重)。
function quoteSymbols(){return [...new Set([...activeIndices().map(i=>i.sym),...GOLD_SYMS,...activeWatchlist().map(w=>w.sym)])];}
// 報價背景推送:後端抓好寫入快取後以 evaluate_js 呼叫本函式;前端只讀快取渲染(永不等網路)。
window.onQuotesPush=async function(){
  snapshotPrices();
  let q;try{q=await api().get_quotes_cached();}catch(e){q=null;}
  if(q)STATE.quotes=q;
  renderIndices();renderWatchlist();renderGoldPrices();renderAlerts();flashTicks();
  if(STATE.page==='detail'&&STATE.detail.sym)renderDetail();
  if(STATE.page==='wallet'&&!STATE.wallet.loading)loadWallet();
  const t=new Date();
  $('#updated').innerHTML=`延遲報價 · 更新<br>${t.toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
  _refreshDone();
};
let _refreshPending=false,_refreshSafety=null;
function _refreshDone(){_refreshPending=false;clearTimeout(_refreshSafety);const icon=$('#ricon');if(icon)icon.classList.remove('spin');$('#refresh').disabled=false;}
// 首次載入:把當前標的交給背景刷新器(集合由空→有值即觸發第一輪抓取+推送)。
function startQuotes(){try{api().set_quote_symbols(quoteSymbols());}catch(e){}}
// 手動 ↻:標的沒變,只要求立即刷新一次(不再連發 set_quote_symbols,避免雙重推送)。重入防護。
async function refreshAll(){
  if(_refreshPending)return;
  _refreshPending=true;
  const icon=$('#ricon');if(icon)icon.classList.add('spin');$('#refresh').disabled=true;
  clearTimeout(_refreshSafety);_refreshSafety=setTimeout(_refreshDone,8000);   // 推播萬一沒到的保險
  try{await api().request_refresh_now();}
  catch(e){_refreshDone();}
}

function initSidebar(){
  const app=$('.app'),btn=$('#collapse-btn');
  const apply=c=>{app.classList.toggle('collapsed',c);btn.textContent=c?'›':'‹';};
  apply(localStorage.getItem('sidebarCollapsed')==='1');
  btn.onclick=()=>{const c=!app.classList.contains('collapsed');apply(c);
    try{localStorage.setItem('sidebarCollapsed',c?'1':'0');}catch(e){}};
}
/* ---------- 美股 / 台股 切換 ---------- */
// 用 .market-switch[data-market] 選取主畫面與黃金頁的市場切換鈕,
// 錢包的 #wallet-ccy-switch (data-ccy USD/TWD) 也透過 setMarket↔setWalletCcy 雙向同步,
// 三顆切換鈕共同反映全域 STATE.market (us/tw) 與 STATE.wallet.ccy (USD/TWD)。
function marketSwitches(){return document.querySelectorAll('.market-switch[data-market]');}
function applyMarketUI(){
  marketSwitches().forEach(sw=>{
    sw.dataset.market=STATE.market;
    sw.querySelectorAll('.ms-btn').forEach(b=>b.classList.toggle('on',b.dataset.market===STATE.market));
  });
}
let _syncing=false; // 防止 setMarket ↔ setWalletCcy 循環呼叫
function setMarket(m){
  if(m===STATE.market||(m!=='us'&&m!=='tw'))return;
  STATE.market=m;
  try{localStorage.setItem('market',m);}catch(e){}
  applyMarketUI();
  // 同步錢包幣別:us→USD, tw→TWD
  if(!_syncing){
    _syncing=true;
    const ccy=m==='tw'?'TWD':'USD';
    if(ccy!==STATE.wallet.ccy){
      STATE.wallet.ccy=ccy;
      try{localStorage.setItem('walletCcy',ccy);}catch(e){}
      applyWalletCcyUI();
      if(STATE.wallet.data)renderWallet();
      renderWalletCharts();
    }
    _syncing=false;
  }
  renderIndices();renderWatchlist();renderDashEvents();renderFullCalendar();renderCustomEvents();
  renderGoldPrices();refreshAlertSymbols();renderAlerts();
  // 只更新背景刷新器的標的(集合變更即自動觸發一輪刷新+推送);不再連發 request 避免雙重推送
  api().set_quote_symbols(quoteSymbols());
  refreshEarnings();
}
function initMarketSwitch(){
  STATE.market=localStorage.getItem('market')==='tw'?'tw':'us';
  applyMarketUI();
  marketSwitches().forEach(sw=>sw.querySelectorAll('.ms-btn').forEach(b=>b.onclick=()=>setMarket(b.dataset.market)));
}
/* ---------- 命令面板 (Ctrl/⌘+K) ---------- */
const PALETTE_PAGES=[
  {id:'dashboard',label:'主畫面',ic:'🏠'},{id:'wallet',label:'我的錢包',ic:'💼'},
  {id:'gold',label:'黃金訊號',ic:'🪙'},{id:'calendar',label:'重大事件',ic:'📅'},
  {id:'settings',label:'設定',ic:'⚙️'},
];
function paletteLocalSymbols(){
  const seen=new Set(),out=[];
  const add=(sym,name)=>{if(sym&&!seen.has(sym)){seen.add(sym);out.push({sym,name:name||sym});}};
  flattenWatchlist(STATE.watchlists.us).forEach(w=>add(w.sym,w.name));
  flattenWatchlist(STATE.watchlists.tw).forEach(w=>add(w.sym,w.name));
  [...GOLD_US,...GOLD_TW].forEach(g=>add(g.sym,g.name));
  return out;
}
function openPalette(){STATE.palette.open=true;$('#cmdk-bg').classList.add('show');
  const inp=$('#cmdk-input');inp.value='';inp.focus();buildPalette('');}
function closePalette(){STATE.palette.open=false;$('#cmdk-bg').classList.remove('show');}
function buildPalette(q){
  q=q.trim();STATE.palette.q=q;const ql=q.toLowerCase();
  const pages=PALETTE_PAGES.filter(p=>!q||p.label.toLowerCase().includes(ql)||p.id.includes(ql))
    .map(p=>({type:'page',id:p.id,ic:p.ic,label:p.label,sub:'前往頁面'}));
  const locals=(q?paletteLocalSymbols().filter(s=>s.sym.toLowerCase().includes(ql)||(s.name||'').toLowerCase().includes(ql)):[])
    .slice(0,6).map(s=>({type:'symbol',sym:s.sym,name:s.name,ic:'📈',label:s.sym,sub:s.name||'標的'}));
  STATE.palette.base=[...pages,...locals];STATE.palette.items=STATE.palette.base.slice();
  STATE.palette.sel=0;renderPalette();
  clearTimeout(STATE.palette.timer);
  if(q.length>=1){STATE.palette.timer=setTimeout(async()=>{
    let list;try{list=await api().search_symbol(q);}catch(e){return;}
    if(!STATE.palette.open||STATE.palette.q!==q)return;
    const have=new Set(STATE.palette.base.filter(i=>i.type==='symbol').map(i=>i.sym));
    const remote=(list||[]).filter(r=>!have.has(r.sym)).slice(0,8)
      .map(r=>({type:'symbol',sym:r.sym,name:r.name,ic:'🔍',label:r.sym,sub:`${r.name||''} · ${r.exch||r.type||''}`}));
    STATE.palette.items=STATE.palette.base.concat(remote);renderPalette();
  },260);}
}
function renderPalette(){
  const box=$('#cmdk-list'),items=STATE.palette.items;
  if(!items.length){box.innerHTML='<div class="cmdk-empty">找不到符合的頁面或標的</div>';return;}
  box.innerHTML=items.map((it,i)=>`<div class="cmdk-item${i===STATE.palette.sel?' sel':''}" data-i="${i}">
    <span class="cmdk-ic">${it.ic}</span><span class="cmdk-lb">${esc(it.label)}<span class="cmdk-sub">${esc(it.sub||'')}</span></span></div>`).join('');
  box.querySelectorAll('.cmdk-item').forEach(el=>{
    el.onmousemove=()=>{STATE.palette.sel=+el.dataset.i;highlightPalette();};
    el.onclick=()=>choosePalette(+el.dataset.i);});
}
function highlightPalette(){$('#cmdk-list').querySelectorAll('.cmdk-item').forEach((el,i)=>el.classList.toggle('sel',i===STATE.palette.sel));
  const sel=$('#cmdk-list').querySelector('.cmdk-item.sel');if(sel)sel.scrollIntoView({block:'nearest'});}
function choosePalette(i){const it=STATE.palette.items[i];if(!it)return;closePalette();
  if(it.type==='page')showPage(it.id);else openDetail(it.sym,it.name);}
function initPalette(){
  const inp=$('#cmdk-input');
  inp.oninput=()=>buildPalette(inp.value);
  inp.onkeydown=e=>{const n=STATE.palette.items.length;
    if(e.key==='ArrowDown'){e.preventDefault();if(n)STATE.palette.sel=(STATE.palette.sel+1)%n;highlightPalette();}
    else if(e.key==='ArrowUp'){e.preventDefault();if(n)STATE.palette.sel=(STATE.palette.sel-1+n)%n;highlightPalette();}
    else if(e.key==='Enter'){e.preventDefault();choosePalette(STATE.palette.sel);}
    else if(e.key==='Escape'){closePalette();}};
  $('#cmdk-bg').onclick=e=>{if(e.target.id==='cmdk-bg')closePalette();};
  $('#cmdk-open')&&($('#cmdk-open').onclick=openPalette);
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&(e.key==='k'||e.key==='K')){e.preventDefault();STATE.palette.open?closePalette():openPalette();}
    else if(e.key==='/'&&!STATE.palette.open&&!/^(input|textarea|select)$/i.test(e.target.tagName||'')){e.preventDefault();openPalette();}
  });
}
function boot(){
  initTheme();
  initUpDown();
  initSidebar();
  initMarketSwitch();
  initNav();initSearch();initAlertForm();initDetail();initCrosshair();initWalletCrosshair();initAi();initWalletForm();initCustomEventsForm();initSettings();initWatchlistView();initPalette();initPerfMode();
  document.querySelectorAll('select').forEach(createCustomSelect);
  $('#refresh').onclick=refreshAll;
  document.addEventListener('click',e=>{
    const card=e.target.closest('.qcard[data-open]');
    if(card&&!e.target.closest('.rm'))openDetail(card.dataset.open,card.dataset.name);
  });
  // qcard 以委派處理點擊,鍵盤(Enter/Space)同樣委派:聚焦卡片按鍵即開啟詳細頁。
  document.addEventListener('keydown',e=>{
    if(e.key!=='Enter'&&e.key!==' ')return;
    const card=e.target.closest&&e.target.closest('.qcard[data-open]');
    if(card&&!e.target.closest('.rm')){e.preventDefault();openDetail(card.dataset.open,card.dataset.name);}
  });
  renderIndices();renderGoldPrices();
  // 初次載入後把標的交給後端 QuoteRefresher(空→有值即觸發首輪抓取+推送);
  // 週期性刷新(每 120 秒)由後端排程,不再用前端 setInterval。
  loadStatic().then(startQuotes);
}
if(window.pywebview) boot();
else window.addEventListener('pywebviewready',boot);

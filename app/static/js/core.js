// Finance Hub — core.js
// Shared utilities, state, navigation, data loaders

const $=id=>document.getElementById(id);
const fmt=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
const fmtDate=s=>s?s.slice(0,10):'—';
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});if(!r.ok)throw new Error(await r.text());return r.json();}
function esc(s){if(s==null)return'';const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}

function closeModal(id){$(id).classList.remove('open');if(!document.querySelector('.modal-bg.open'))document.body.style.overflow='';}
function openModal(id){$(id).classList.add('open');document.body.style.overflow='hidden';}

// ── Toast notifications (replaces alert()) ──
function toast(msg,type='info'){const c=$('toast-container');if(!c)return;const t=document.createElement('div');t.className='toast toast-'+type;t.textContent=msg;c.appendChild(t);setTimeout(()=>{if(t.parentNode)t.remove();},3200);}

// ── Custom confirm (replaces confirm()) ──
function customConfirm(msg,onOk,okLabel,okClass){
  const bg=$('confirm-dialog'),m=$('confirm-msg'),ok=$('confirm-ok'),cn=$('confirm-cancel');
  m.textContent=msg;
  ok.textContent=okLabel||'Confirm';
  ok.className=okClass||'btn btn-danger';
  bg.classList.add('open');
  document.body.style.overflow='hidden';
  function cleanup(){bg.classList.remove('open');if(!document.querySelector('.modal-bg.open'))document.body.style.overflow='';ok.onclick=null;cn.onclick=null;bg.onclick=null;}
  ok.onclick=function(){cleanup();onOk();};
  cn.onclick=function(){cleanup();};
  bg.onclick=function(e){if(e.target===bg)cleanup();};
}

// ── Navigation ──
// Only bind top nav links (not bottom-nav, which uses its own handler)
document.querySelectorAll('nav:first-of-type a[data-page]').forEach(a=>{a.addEventListener('click',()=>showPage(a.dataset.page));});

// Pages reachable from the "More" menu (not in bottom nav)
const MORE_PAGES = new Set(['merchants','forecast','review','rules','subscriptions','imports','reconcile','goals','bills','compare','flow','insights','history']);

function showPage(name){
  // Close More overlay if open
  var mo=$('more-overlay');if(mo)mo.classList.remove('open');

  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  // Top nav active state
  document.querySelectorAll('nav:first-of-type a[data-page]').forEach(a=>a.classList.remove('active'));
  var topLink=document.querySelector('nav:first-of-type a[data-page="'+name+'"]');
  if(topLink)topLink.classList.add('active');

  // Sidebar active state
  document.querySelectorAll('.sidebar a[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===name));
  $('page-'+name).classList.add('active');

  // Bottom nav active state
  document.querySelectorAll('.bottom-nav a[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===name));
  // Highlight "More" tab when on a secondary page
  var moreTab=$('more-tab');
  if(moreTab)moreTab.classList.toggle('active',MORE_PAGES.has(name));

  // Page loaders
  if(name==='dashboard'){loadDashboard();loadSankey();if(typeof loadGoalsDashboard==='function')loadGoalsDashboard();if(typeof loadReviewCounts==='function')loadReviewCounts();}
  if(name==='spending')loadSpending();
  if(name==='transactions'){loadCategories();loadAccounts();loadTxns();loadBulkDropdowns();}
  if(name==='rules'){loadRules();loadCategories();}
  if(name==='settings'){loadAccountsSettings();loadCategoriesSettings();loadBudgetSettings();loadHoldingsSettings();}
  if(name==='subscriptions')loadSubscriptions();
  if(name==='imports'){loadImportsPage();loadCsvAccounts();}
  if(name==='reconcile'){loadReconAccounts();loadReconHistory();}
  if(name==='forecast')loadForecastPage();
  if(name==='merchants')loadMerchantsPage();
  if(name==='compare')loadComparePage();
  if(name==='review')loadReviewPage();
  if(name==='bills')loadBillsPage();
  if(name==='goals')loadGoalsPage();
  if(name==='flow')loadFlowPage();
  if(name==='insights')loadInsights();
  if(name==='history')loadHistory();

  // Push browser history (skip if this was triggered by popstate)
  if(!window._isPopState){
    var url='/#/'+name;
    if(window.location.hash!=='#/'+name){
      history.pushState({page:name},name,url);
    }
  }
  window._isPopState=false;
}

// ── More menu ──
function toggleMoreMenu(e){
  if(e)e.preventDefault();
  var mo=$('more-overlay');
  if(mo)mo.classList.toggle('open');
}
function closeMoreMenu(e){
  // Close when tapping the backdrop
  if(e&&e.target.id==='more-overlay')$('more-overlay').classList.remove('open');
}
function moreNav(page){
  $('more-overlay').classList.remove('open');
  showPage(page);
}

// ── Filter active indicator (mobile) ──
function updateFilterBadge(){
  const btn=$('filter-toggle-btn');if(!btn)return;
  const s=$('t-search')?.value||$('t-search-m')?.value||'';
  const a=$('t-account')?.value;
  const c=$('t-category')?.value;
  const f=$('t-from')?.value;
  const t=$('t-to')?.value;
  let count=0;
  if(s)count++;if(a)count++;if(c)count++;if(f)count++;if(t)count++;
  const existing=btn.querySelector('.filter-badge');
  if(existing)existing.remove();
  if(count>0){
    const badge=document.createElement('span');
    badge.className='filter-badge';
    badge.textContent=count;
    btn.appendChild(badge);
    btn.innerHTML=btn.innerHTML.replace(/🔍 Filter|✕ Close/,count+' active');
  } else {
    const panel=$('filter-panel');
    btn.textContent=panel&&panel.classList.contains('open')?'✕ Close':'🔍 Filter';
  }
}

// ── Shared state ──
let syncPollTimer=null;
let categories=[];
let accounts=[];

// ── Categories ──
async function loadCategories(){categories=await api('/api/categories');const opts='<option value="">Uncategorized</option>'+categories.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');['mt-category','mr-category'].forEach(id=>{if($(id))$(id).innerHTML=opts;});const fo='<option value="">All categories</option><option value="none">Uncategorized</option>'+categories.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');if($('t-category'))$('t-category').innerHTML=fo;}
function catById(id){return categories.find(c=>c.id===id);}
function catBadge(id,name){if(!id||!name)return'<span style="color:#475569;font-size:.75rem">—</span>';const c=catById(id);const col=c?.color||'#475569';return`<span class="badge" style="background:${col}22;color:${col}">${esc(name)}</span>`;}

// ── Accounts ──
async function loadAccounts(){accounts=await api('/api/accounts');const opts='<option value="">All accounts</option>'+accounts.map(a=>`<option value="${a.id}">${a.org?a.org+' – ':''}${a.name}</option>`).join('');if($('t-account'))$('t-account').innerHTML=opts;}

// ── Bottom nav ──
(function(){
  var bn=document.getElementById('bottom-nav');
  if(!bn)return;
  bn.addEventListener('click',function(e){
    var a=e.target.closest('a[data-page]');
    if(!a)return;
    e.preventDefault();
    showPage(a.dataset.page);
  });
})();

// ── Set default date range for spending page ──
(function(){const now=new Date(),y=now.getFullYear(),m=now.getMonth();$('sp-from').value=new Date(y,m,1).toISOString().slice(0,10);$('sp-to').value=new Date(y,m+1,0).toISOString().slice(0,10);})();

// ── Browser history (back/forward button support) ──
window.addEventListener('popstate',function(e){
  var page=(e.state&&e.state.page)?e.state.page:null;
  if(!page){
    // Try hash
    var h=window.location.hash.replace('#/','');
    if(h&&document.getElementById('page-'+h))page=h;
  }
  if(page){
    window._isPopState=true;
    showPage(page);
  }
});

// ── Tags for filter ──
async function loadTagFilter(){
  try{
    var tags=await api('/api/tags');
    var sel=$('t-tag');
    if(sel)sel.innerHTML='<option value="">All tags</option>'+tags.map(function(t){return'<option value="'+t.id+'">'+t.name+(t.count?' ('+t.count+')':'')+' </option>';}).join('');
  }catch(e){console.error('Tag filter:',e);}
}

// ── Bulk edit dropdowns ──
function loadBulkDropdowns(){
  var catSel=$('bulk-category');
  if(catSel&&categories.length){
    catSel.innerHTML='<option value="">Clear category</option>'+categories.map(function(c){return'<option value="'+c.id+'">'+c.name+'</option>';}).join('');
  }
  var tagSel=$('bulk-tag');
  if(tagSel&&typeof _allTags!=='undefined'&&_allTags.length){
    tagSel.innerHTML='<option value="">Select tag</option>'+_allTags.map(function(t){return'<option value="'+t.id+'">'+t.name+'</option>';}).join('');
  }
}

// ── Boot ──
loadCategories();loadTagFilter();
// Load page from URL hash or default to dashboard
(function(){
  var hash=window.location.hash.replace('#/','');
  if(hash&&document.getElementById('page-'+hash)){
    showPage(hash);
    history.replaceState({page:hash},hash,'/#/'+hash);
  }else{
    history.replaceState({page:'dashboard'},'dashboard','/#/dashboard');
    // Sync sidebar
    document.querySelectorAll('.sidebar a[data-page]').forEach(function(a){
      a.classList.toggle('active',a.dataset.page==='dashboard');
    });
  }
})();

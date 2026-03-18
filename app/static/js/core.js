// Finance Hub — core.js
// Shared utilities, state, navigation, data loaders

const $=id=>document.getElementById(id);
const fmt=n=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
const fmtDate=s=>s?s.slice(0,10):'—';
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});if(!r.ok)throw new Error(await r.text());return r.json();}
function esc(s){if(s==null)return'';const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}

function closeModal(id){$(id).classList.remove('open');}
function openModal(id){$(id).classList.add('open');}

// ── Navigation ──
document.querySelectorAll('nav a[data-page]').forEach(a=>{a.addEventListener('click',()=>showPage(a.dataset.page));});
function showPage(name){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('nav a[data-page]').forEach(a=>a.classList.remove('active'));$(`page-${name}`).classList.add('active');document.querySelector(`nav a[data-page="${name}"]`)?.classList.add('active');
document.querySelectorAll('.bottom-nav a').forEach(a=>a.classList.toggle('active',a.dataset.page===name));if(name==='dashboard'){loadDashboard();loadSankey();}if(name==='spending')loadSpending();if(name==='transactions'){loadCategories();loadAccounts();loadTxns();}if(name==='rules'){loadRules();loadCategories();}if(name==='settings'){loadAccountsSettings();loadCategoriesSettings();loadBudgetSettings();}if(name==='subscriptions')loadSubscriptions();if(name==='imports'){loadImportsPage();loadCsvAccounts();}if(name==='reconcile'){loadReconAccounts();loadReconHistory();}}

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
    e.preventDefault();
    var a=e.target.closest('a[data-page]');
    if(a&&a.dataset.page)showPage(a.dataset.page);
  });
})();

// ── Set default date range for spending page ──
(function(){const now=new Date(),y=now.getFullYear(),m=now.getMonth();$('sp-from').value=new Date(y,m,1).toISOString().slice(0,10);$('sp-to').value=new Date(y,m+1,0).toISOString().slice(0,10);})();

// ── Boot (no forward refs — loadCategories defined above) ──
loadCategories();

// Finance Hub — transactions.js
// Transaction list, filters, modal, transfer toggle, drill-down

let txnOffset=0,txnTotal=0;
const TXN_LIMIT=100;
let editingTxnId=null,_txnList=[];

// ── Mobile helpers ──
function toggleFilters(){const p=$('filter-panel');p.classList.toggle('open');const b=$('filter-toggle-btn');b.textContent=p.classList.contains('open')?'✕ Close':'🔍 Filter';}
function syncSearch(src){const d=$('t-search'),m=$('t-search-m');if(src===m&&d)d.value=m.value;if(src===d&&m)m.value=d.value;}

function clearTxnFilters(){window._drillType=null;['t-search','t-from','t-to','t-search-m'].forEach(id=>{if($(id))$(id).value='';});$('t-account').value='';$('t-category').value='';if($('t-recurring'))$('t-recurring').checked=false;txnOffset=0;loadTxns();}
function txnPage(dir){txnOffset=Math.max(0,Math.min(txnTotal-TXN_LIMIT,txnOffset+dir*TXN_LIMIT));loadTxns();}
async function loadTxns(){const params=new URLSearchParams({limit:TXN_LIMIT,offset:txnOffset});if(window._drillType){params.set('txn_type',window._drillType);params.set('exclude_transfers','true');}const search=$('t-search')?.value,account=$('t-account')?.value;const catVal=$('t-category')?.value,from=$('t-from')?.value,to=$('t-to')?.value;if(search)params.set('search',search);if(account)params.set('account_id',account);if(catVal==='none')params.set('category_id','none');else if(catVal)params.set('category_id',catVal);if(from)params.set('start_date',from);if(to)params.set('end_date',to);const recur=$('t-recurring')?.checked;if(recur)params.set('recurring','true');const tagVal=$('t-tag')?.value;if(tagVal)params.set('tag_id',tagVal);const data=await api('/api/transactions?'+params);txnTotal=data.total;const txns=data.transactions;_txnList=txns;const pages=Math.max(1,Math.ceil(txnTotal/TXN_LIMIT));const page=Math.floor(txnOffset/TXN_LIMIT)+1;const showBal=data.has_balance;document.querySelectorAll('.bal-col').forEach(el=>{el.style.display=showBal?'':'none';});
  $('txn-summary').textContent=`${txnTotal.toLocaleString()} transactions`;$('t-page-lbl').textContent=`${page} / ${pages}`;$('t-prev').disabled=txnOffset===0;$('t-next').disabled=txnOffset+TXN_LIMIT>=txnTotal;if(typeof updateFilterBadge==='function')updateFilterBadge();if(!txns.length){$('txn-tbody').innerHTML=`<tr><td colspan="6" class="empty">No transactions match</td></tr>`;return;}$('txn-tbody').innerHTML=txns.map(t=>{const tb=t.is_transfer?`<span class="badge-transfer" onclick="toggleTransfer('${t.id}')" title="Click to unmark">↔ transfer</span> `:'';const sb=t.source==='manual'?'<span class="badge" style="background:#312e81;color:#a5b4fc;font-size:.6rem;margin-right:.3rem">manual</span>':t.source==='csv'?'<span class="badge" style="background:#1e3a5f;color:#7dd3fc;font-size:.6rem;margin-right:.3rem">csv</span>':'';
    const srcBadge=t.source==='manual'?'<span class="badge" style="background:#1e3a5f;color:#7dd3fc;font-size:.62rem;margin-right:.3rem" title="Manually entered">✎ manual</span> ':t.source==='csv'?'<span class="badge" style="background:#3b1f0b;color:#fde68a;font-size:.62rem;margin-right:.3rem" title="CSV import">⬆ csv</span> ':'';
    const pendingBadge=t.pending?'<span class="badge" style="background:#713f12;color:#fde68a;font-size:.62rem;margin-right:.3rem;animation:pulse 2s ease-in-out infinite" title="Pending — not yet posted">⏳ pending</span> ':'';
    const lockBadge=t.reconciled_at?'<span class="badge" style="background:#14532d;color:#86efac;font-size:.62rem;margin-right:.3rem" title="Reconciled">🔒</span> ':'';
    const splitBadge=t.has_splits?'<span class="badge" style="background:#4c1d95;color:#c4b5fd;font-size:.62rem;margin-right:.3rem;cursor:pointer" title="Split transaction — click to edit" onclick="event.stopPropagation();openSplitModal(\''+t.id+'\')">✂ split</span> ':'';return`<tr style="${t.is_transfer?'opacity:0.5':t.pending?'opacity:0.6;font-style:italic':''}" onclick="openTxnModal('${t.id}')"><td class="tc-date" style="white-space:nowrap;color:#64748b">${fmtDate(t.posted)}</td><td class="tc-desc"><div style="font-size:.83rem">${t.recurring?'<span style="color:#c084fc;font-size:.68rem;margin-right:.3rem" title="Recurring">↻</span>':''}${srcBadge}${sb}${tb}${esc(t.payee||t.description||'—')}</div>${t.payee&&t.description!==t.payee?`<div style="font-size:.72rem;color:#475569">${esc(t.description)}</div>`:''}</td><td class="tc-acct" style="font-size:.75rem;color:#475569">${esc(t.account_name||'')}</td><td class="tc-cat">${catBadge(t.category_id,t.category)}</td><td class="tc-amt ${t.amount<0?'amt-neg':'amt-pos'}" style="text-align:right">${fmt(t.amount)}</td><td class="tc-bal bal-col ${t.running_balance!=null?(t.running_balance<0?'amt-neg':'amt-pos'):''}" style="text-align:right;display:none">${t.running_balance!=null?fmt(t.running_balance):''}</td><td class="tc-edit"><button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openTxnModal('${t.id}')">Edit</button></td></tr>`;}).join('');
  // Append total row
  const totalAmt=data.total_amount||0;
  const amtClass=totalAmt<0?'amt-neg':'amt-pos';
  $('txn-tbody').innerHTML+=`<tr style="border-top:2px solid #1e2530;background:#0a0d14"><td class="tc-date"></td><td class="tc-desc" style="font-weight:600;font-size:.82rem;color:#94a3b8">Total</td><td class="tc-acct"></td><td class="tc-cat"></td><td class="tc-amt ${amtClass}" style="text-align:right;font-weight:700;font-size:.92rem">${fmt(totalAmt)}</td><td class="tc-bal bal-col" style="display:none"></td><td class="tc-edit"></td></tr>`;}
function openTxnModal(id){
  const t=_txnList.find(x=>x.id===id);if(!t)return;
  editingTxnId=id;
  $('mt-desc-display').textContent=t.description||t.payee||'Unknown';
  $('mt-date-display').textContent=t.posted?t.posted.slice(0,10):'—';
  $('mt-acct-display').textContent=t.account_name||'';
  const ad=$('mt-amt-display');ad.textContent=fmt(t.amount);ad.className=t.amount<0?'amt-neg':'amt-pos';
  $('mt-is-transfer').checked=!!t.is_transfer;
  // Show delete button for manual txns
  const delBtn=$('mt-delete-btn');
  if(delBtn)delBtn.style.display=t.source==='manual'?'inline-flex':'none';
  // Show transfer pair info
  const pairInfo=$('mt-pair-info');
  if(pairInfo){
    if(t.transfer_pair_id){
      const pair=_txnList.find(x=>x.transfer_pair_id===t.transfer_pair_id&&x.id!==t.id);
      if(pair){
        pairInfo.innerHTML='<div style="font-size:.75rem;color:#7dd3fc;background:#1e3a5f22;padding:.4rem .6rem;border-radius:6px;margin-bottom:.5rem">↔ Linked to: '+esc(pair.payee||pair.description)+' ('+esc(pair.account_name)+') '+fmt(pair.amount)+'</div>';
      } else {
        pairInfo.innerHTML='<div style="font-size:.75rem;color:#7dd3fc;margin-bottom:.3rem">↔ Pair ID: '+t.transfer_pair_id+'</div>';
      }
    } else {
      pairInfo.innerHTML='';
    }
  }
  $('mt-payee').value=t.payee||'';
  $('mt-category').value=t.category_id||'';
  $('mt-notes').value=t.notes||'';
  $('mt-make-rule').checked=false;
  $('mt-recurring').checked=!!t.recurring;
  openModal('modal-txn');
  showDeleteIfManual();
}
function showDeleteIfManual(){
  const t=_txnList.find(x=>x.id===editingTxnId);
  const delBtn=$('mt-delete-btn');
  if(delBtn) delBtn.style.display=(t&&t.source==='manual')?'inline-flex':'none';
  const srcEl=$('mt-source-display');
  if(srcEl&&t){const labels={manual:'✎ Manual entry',csv:'⬆ CSV import',sync:'⚡ SimpleFIN sync'};srcEl.textContent=labels[t.source]||t.source||'sync';srcEl.style.display='block';}
}
async function saveTxn(){
  const body={payee:$('mt-payee').value||null,category_id:$('mt-category').value?parseInt($('mt-category').value):null,notes:$('mt-notes').value||null,recurring:$('mt-recurring').checked};
  await api('/api/transactions/'+editingTxnId,{method:'PATCH',body:JSON.stringify(body)});
  const t=_txnList.find(x=>x.id===editingTxnId);
  const wantTransfer=$('mt-is-transfer').checked;
  if(t&&!!t.is_transfer!==wantTransfer){await api('/api/transactions/'+editingTxnId+'/transfer',{method:'PATCH'});}
  if($('mt-make-rule').checked&&body.payee){const desc=$('mt-desc-display').textContent||body.payee;const pattern=desc.toLowerCase().slice(0,40);await api('/api/payee-rules',{method:'POST',body:JSON.stringify({match_pattern:pattern,payee_name:body.payee,category_id:body.category_id,priority:0})});}
  closeModal('modal-txn');loadTxns();loadDashboard();
}
function exportCsv(){const p=new URLSearchParams();const s=$('t-search')?.value,a=$('t-account')?.value,c=$('t-category')?.value,f=$('t-from')?.value,t=$('t-to')?.value;if(s)p.set('search',s);if(a)p.set('account_id',a);if(c&&c!=='none')p.set('category_id',c);if(f)p.set('start_date',f);if(t)p.set('end_date',t);window.location.href='/api/transactions/export?'+p;}
async function toggleTransfer(txnId){try{await api(`/api/transactions/${txnId}/transfer`,{method:'PATCH'});loadTxns();loadDashboard();}catch(e){alert('Error: '+e.message);}}
function drillDown(opts){
  const now=new Date(),y=now.getFullYear(),m=now.getMonth();
  const ms=`${y}-${String(m+1).padStart(2,'0')}-01`;
  const me=`${y}-${String(m+1).padStart(2,'0')}-${String(new Date(y,m+1,0).getDate()).padStart(2,'0')}`;
  $('t-from').value=opts.from||ms;
  $('t-to').value=opts.to||me;
  $('t-category').selectedIndex=0;
  $('t-account').selectedIndex=0;
  if(opts.category){const sel=$('t-category');for(let i=0;i<sel.options.length;i++){if(sel.options[i].value===String(opts.category)){sel.selectedIndex=i;break;}}}
  window._drillType=opts.type||null;
  txnOffset=0;
  showPage('transactions');
}

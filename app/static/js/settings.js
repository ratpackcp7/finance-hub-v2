// Finance Hub — settings.js
// Accounts, categories, budgets management

let _acctEditMode=false;

function toggleAcctEdit(){_acctEditMode=!_acctEditMode;loadAccountsSettings();}
async function patchAccount(id,at){try{await api('/api/accounts/'+id,{method:'PATCH',body:JSON.stringify({account_type:at})});}catch(e){toast('Error: '+e.message,'error');}}
async function toggleAccountBudget(id,val){try{await api('/api/accounts/'+id,{method:'PATCH',body:JSON.stringify({on_budget:val})});toast(val?'Included in net worth':'Excluded from net worth','success');}catch(e){toast('Error: '+e.message,'error');}}

async function loadAccountsSettings(){const accts=await api('/api/accounts');if(!accts.length){$('accounts-list').innerHTML='<p class="empty">No accounts synced yet.</p>';return;}const typeOpts=['checking','savings','credit','investment','retirement','529','utma','hsa','brokerage','loan','mortgage','other'];const dis=_acctEditMode?'':'disabled';const selStyle=_acctEditMode?'font-size:.75rem;padding:.2rem .3rem;min-width:90px':'font-size:.75rem;padding:.2rem .3rem;min-width:90px;opacity:.6;pointer-events:none';$('accounts-list').innerHTML=`<div style="display:flex;justify-content:flex-end;margin-bottom:.6rem"><button class="btn ${_acctEditMode?'btn-success':'btn-ghost'} btn-sm" onclick="toggleAcctEdit()">${_acctEditMode?'✓ Done Editing':'✏ Edit Types'}</button></div><table><thead><tr><th>Institution</th><th>Account</th><th>Type</th><th>Balance</th><th>Net Worth</th></tr></thead><tbody>${accts.map(a=>`<tr><td style="color:#64748b;font-size:.78rem">${esc(a.org||'—')}</td><td><a style="color:#60a5fa;cursor:pointer;text-decoration:none" onclick="openAcctDetail('${a.id}')">${esc(a.name)}</a></td><td><select style="${selStyle}" ${dis} onchange="patchAccount('${a.id}',this.value)">${typeOpts.map(t=>`<option value="${t}"${t===(a.account_type||'checking')?' selected':''}>${t}</option>`).join('')}</select></td><td class="${a.balance<0?'amt-neg':'amt-pos'}">${fmt(a.balance)}</td><td style="text-align:center"><input type="checkbox" ${a.on_budget?'checked':''} ${_acctEditMode?'':'disabled'} onchange="toggleAccountBudget('${a.id}',this.checked)" title="Include in net worth" style="${_acctEditMode?'cursor:pointer':'opacity:.5;pointer-events:none'}"></td></tr>`).join('')}</tbody></table>`;}
async function loadCategoriesSettings(){const cats=await api('/api/categories');$('cat-list').innerHTML=`<table><thead><tr><th>Category</th><th>Group</th><th></th></tr></thead><tbody>${cats.map(c=>`<tr><td><span class="cat-dot" style="background:${c.color}"></span>${esc(c.name)}</td><td style="color:#64748b;font-size:.78rem">${esc(c.group||'\u2014')}</td><td>${c.name!=='Uncategorized'?`<button class="btn btn-ghost btn-sm" style="margin-right:.3rem" onclick="openEditCatModal(${c.id})">Edit</button><button class="btn btn-danger btn-sm" onclick='deleteCat(${c.id}, ${JSON.stringify(c.name)})'>\u00d7</button>`:''}</td></tr>`).join('')}</tbody></table>`;}
function openCatModal(){$('mc-name').value='';$('mc-group').value='';$('mc-color').value='#64748b';openModal('modal-cat');}
async function saveCat(){await api('/api/categories',{method:'POST',body:JSON.stringify({name:$('mc-name').value.trim(),group_name:$('mc-group').value.trim()||null,color:$('mc-color').value})});closeModal('modal-cat');loadCategoriesSettings();loadCategories();}
async function deleteCat(id,name){customConfirm('Delete "'+name+'"?',async function(){await api('/api/categories/'+id,{method:'DELETE'});loadCategoriesSettings();loadCategories();});}
let _editCatData=null;
function openEditCatModal(id){
  const cat=categories.find(c=>c.id===id);
  if(!cat)return;
  _editCatData=cat;
  $('mec-name').value=cat.name;
  $('mec-color').value=cat.color||'#64748b';
  $('mec-group').value=cat.group||'';
  openModal('modal-edit-cat');
  setTimeout(()=>$('mec-name').select(),50);
}
async function saveEditCat(){
  if(!_editCatData)return;
  const name=$('mec-name').value.trim();
  const color=$('mec-color').value;
  const group=$('mec-group').value.trim();
  if(!name)return toast('Name is required','error');
  const body={};
  if(name!==_editCatData.name)body.name=name;
  if(color!==(_editCatData.color||'#64748b'))body.color=color;
  if(group!==(_editCatData.group||''))body.group_name=group||null;
  if(!Object.keys(body).length){closeModal('modal-edit-cat');return;}
  try{
    await api('/api/categories/'+_editCatData.id,{method:'PATCH',body:JSON.stringify(body)});
    closeModal('modal-edit-cat');
    loadCategoriesSettings();loadCategories();
  }catch(e){toast('Error: '+e.message,'error');}
}
async function loadBudgetSettings(){const budgets=await api('/api/budgets');if(!budgets.length){$('budget-list').innerHTML='<p class="empty">No budgets set yet.</p>';return;}$('budget-list').innerHTML=`<table><thead><tr><th>Category</th><th style="text-align:right">Monthly Target</th><th></th></tr></thead><tbody>${budgets.map(b=>`<tr><td><span class="cat-dot" style="background:${b.color}"></span>${b.category}</td><td style="text-align:right;font-variant-numeric:tabular-nums">${fmt(b.monthly_amount)}</td><td><button class="btn btn-danger btn-sm" onclick="deleteBudget(${b.id})">×</button></td></tr>`).join('')}</tbody></table>`;}
function openBudgetModal(){$('mb-category').innerHTML=categories.filter(c=>c.name!=='Uncategorized'&&!c.is_income).map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');$('mb-amount').value='';openModal('modal-budget');}
async function saveBudget(){const catId=parseInt($('mb-category').value);const amount=parseFloat($('mb-amount').value);if(!catId||!amount||amount<=0)return toast('Select a category and enter an amount','error');await api('/api/budgets',{method:'POST',body:JSON.stringify({category_id:catId,monthly_amount:amount})});closeModal('modal-budget');loadBudgetSettings();}
async function deleteBudget(id){customConfirm('Remove this budget?',async function(){await api('/api/budgets/'+id,{method:'DELETE'});loadBudgetSettings();});}


// ── Holdings Management ──
async function loadHoldingsSettings() {
  var data = await api('/api/holdings');
  var accts = await api('/api/accounts');
  var invAccts = accts.filter(function(a) { return ['investment','retirement','brokerage'].indexOf(a.account_type) >= 0; });

  // Populate account dropdown
  var sel = $('hld-account');
  if (sel) {
    sel.innerHTML = '<option value="">Select account</option>';
    invAccts.forEach(function(a) {
      var short = a.name.length > 35 ? a.name.slice(0, 32) + '...' : a.name;
      sel.innerHTML += '<option value="' + a.id + '">' + short + '</option>';
    });
  }

  var el = $('holdings-manage');
  if (!data.holdings.length) { el.innerHTML = '<p class="empty">No holdings. Add one below.</p>'; return; }

  var html = '<div style="overflow-x:auto"><table style="font-size:.78rem"><thead><tr>'
    + '<th>Ticker</th><th>Name</th><th>Account</th><th style="text-align:right">Shares</th>'
    + '<th style="text-align:right">Cost/Share</th><th style="text-align:right">Price</th><th></th></tr></thead><tbody>';
  data.holdings.forEach(function(h) {
    var shortAcct = h.account_name.length > 20 ? h.account_name.slice(0, 17) + '...' : h.account_name;
    html += '<tr><td style="color:#818cf8;font-weight:600">' + h.ticker + '</td>'
      + '<td>' + h.name + '</td>'
      + '<td style="color:#64748b;font-size:.72rem">' + shortAcct + '</td>'
      + '<td style="text-align:right"><input type="number" step="0.01" value="' + h.shares + '" style="width:80px;font-size:.75rem;text-align:right;padding:.2rem .3rem" onchange="updateHolding(' + h.id + ',{shares:parseFloat(this.value)})"></td>'
      + '<td style="text-align:right"><input type="number" step="0.01" value="' + (h.cost_basis || 0) + '" style="width:80px;font-size:.75rem;text-align:right;padding:.2rem .3rem" onchange="updateHolding(' + h.id + ',{cost_basis:parseFloat(this.value)})"></td>'
      + '<td style="text-align:right;color:#64748b">' + (h.last_price ? '$' + h.last_price.toFixed(2) : '—') + '</td>'
      + '<td><button class="btn btn-ghost btn-sm" style="color:#ef4444;font-size:.7rem" onclick="deleteHolding(' + h.id + ')">✕</button></td></tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

async function addHolding() {
  var acctId = $('hld-account').value;
  var ticker = $('hld-ticker').value.trim().toUpperCase();
  var name = $('hld-name').value.trim();
  var shares = parseFloat($('hld-shares').value) || 0;
  var basis = parseFloat($('hld-basis').value) || null;
  if (!acctId || !ticker || !name) { toast('Fill account, ticker, and name', 'error'); return; }
  try {
    await api('/api/holdings', { method: 'POST', body: JSON.stringify({ account_id: acctId, ticker: ticker, name: name, shares: shares, cost_basis: basis }) });
    toast('Added ' + ticker, 'success');
    $('hld-ticker').value = ''; $('hld-name').value = ''; $('hld-shares').value = ''; $('hld-basis').value = '';
    loadHoldingsSettings();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function updateHolding(id, data) {
  try {
    await api('/api/holdings/' + id, { method: 'PATCH', body: JSON.stringify(data) });
    toast('Updated', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function deleteHolding(id) {
  customConfirm('Delete this holding?', async function() {
    try {
      await api('/api/holdings/' + id, { method: 'DELETE' });
      toast('Deleted', 'success');
      loadHoldingsSettings();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

// Finance Hub — settings.js
// Accounts, categories, budgets management

let _acctEditMode=false;

function toggleAcctEdit(){_acctEditMode=!_acctEditMode;loadAccountsSettings();}
async function patchAccount(id,at){try{await api('/api/accounts/'+id,{method:'PATCH',body:JSON.stringify({account_type:at})});}catch(e){toast('Error: '+e.message,'error');}}
async function toggleAccountBudget(id,val){try{await api('/api/accounts/'+id,{method:'PATCH',body:JSON.stringify({on_budget:val})});toast(val?'Included in net worth':'Excluded from net worth','success');}catch(e){toast('Error: '+e.message,'error');}}

async function loadAccountsSettings(){const accts=await api('/api/accounts');if(!accts.length){$('accounts-list').innerHTML='<p class="empty">No accounts synced yet.</p>';return;}const typeOpts=['checking','savings','credit','investment','retirement','529','utma','hsa','brokerage','loan','mortgage','other'];const dis=_acctEditMode?'':'disabled';const selStyle=_acctEditMode?'font-size:.75rem;padding:.2rem .3rem;min-width:90px':'font-size:.75rem;padding:.2rem .3rem;min-width:90px;opacity:.6;pointer-events:none';$('accounts-list').innerHTML=`<div style="display:flex;justify-content:flex-end;margin-bottom:.6rem"><button class="btn ${_acctEditMode?'btn-success':'btn-ghost'} btn-sm" onclick="toggleAcctEdit()">${_acctEditMode?'✓ Done Editing':'✏ Edit Types'}</button></div><table><thead><tr><th>Institution</th><th>Account</th><th>Type</th><th>Balance</th><th>Net Worth</th></tr></thead><tbody>${accts.map(a=>`<tr><td style="color:#64748b;font-size:.78rem">${esc(a.org||'—')}</td><td>${esc(a.name)}</td><td><select style="${selStyle}" ${dis} onchange="patchAccount('${a.id}',this.value)">${typeOpts.map(t=>`<option value="${t}"${t===(a.account_type||'checking')?' selected':''}>${t}</option>`).join('')}</select></td><td class="${a.balance<0?'amt-neg':'amt-pos'}">${fmt(a.balance)}</td><td style="text-align:center"><input type="checkbox" ${a.on_budget?'checked':''} onchange="toggleAccountBudget('${a.id}',this.checked)" title="Include in net worth"></td></tr>`).join('')}</tbody></table>`;}
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

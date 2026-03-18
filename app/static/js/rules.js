// Finance Hub — rules.js
// Auto-split from index.html

async function loadRules(){const rules=await api('/api/payee-rules');if(!rules.length){$('rules-tbody').innerHTML=`<tr><td colspan="5" class="empty">No rules yet.</td></tr>`;return;}$('rules-tbody').innerHTML=rules.map(r=>`<tr><td><code style="background:#1e2530;padding:.1rem .4rem;border-radius:4px;font-size:.8rem">${esc(r.pattern)}</code></td><td style="color:#94a3b8">${esc(r.payee_name||'—')}</td><td>${catBadge(r.category_id,r.category)}</td><td style="color:#64748b">${r.priority}</td><td><button class="btn btn-danger btn-sm" onclick="deleteRule(${r.id})">Delete</button></td></tr>`).join('');}
function openRuleModal(p=''){$('mr-pattern').value=p;$('mr-payee').value='';$('mr-category').value='';$('mr-priority').value=0;openModal('modal-rule');}
async function saveRule(){const body={match_pattern:$('mr-pattern').value.trim(),payee_name:$('mr-payee').value.trim()||null,category_id:$('mr-category').value?parseInt($('mr-category').value):null,priority:parseInt($('mr-priority').value)||0};if(!body.match_pattern)return alert('Pattern required');await api('/api/payee-rules',{method:'POST',body:JSON.stringify(body)});closeModal('modal-rule');loadRules();}
async function deleteRule(id){if(!confirm('Delete this rule?'))return;await api(`/api/payee-rules/${id}`,{method:'DELETE'});loadRules();}

#!/usr/bin/env python3
"""Patch index.html: add CSV import UI to Imports page + Reconciliation page."""
import re

PATH = "/home/chris/docker/finance-hub-v2/app/static/index.html"

with open(PATH, "r") as f:
    html = f.read()

# ═══ 1. Add CSV Import section to Imports page (before closing </div> of page-imports) ═══
csv_import_section = '''
  <div class="card" id="csv-import-card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <div class="card-title" style="margin:0">CSV Import</div>
    </div>
    <p style="font-size:.8rem;color:#64748b;margin-bottom:1rem">Upload a CSV from Chase, Discover, Citi, or any bank. Auto-detects format by headers.</p>
    <div style="display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap;margin-bottom:1rem">
      <div class="field" style="flex:1;min-width:180px"><label>Account</label><select id="csv-account" style="min-width:180px"><option value="">Select account…</option></select></div>
      <div class="field" style="flex:1;min-width:200px"><label>CSV File</label><input type="file" id="csv-file" accept=".csv" style="font-size:.8rem"></div>
      <button class="btn btn-primary" onclick="csvPreview()" id="csv-preview-btn">Preview</button>
    </div>
    <div id="csv-preview-area" style="display:none">
      <div id="csv-detected" style="font-size:.82rem;margin-bottom:.75rem"></div>
      <div style="max-height:400px;overflow-y:auto;margin-bottom:.75rem"><table><thead><tr><th>Row</th><th>Date</th><th>Description</th><th style="text-align:right">Amount</th><th>CSV Category</th></tr></thead><tbody id="csv-preview-tbody"></tbody></table></div>
      <div style="display:flex;gap:.5rem;justify-content:flex-end"><button class="btn btn-ghost" onclick="csvReset()">Cancel</button><button class="btn btn-primary" onclick="csvApply()" id="csv-apply-btn">Import Transactions</button></div>
      <div id="csv-result" style="font-size:.82rem;margin-top:.5rem"></div>
    </div>
  </div>
'''

# Insert before the closing of page-imports (the last </div> before next page)
# Find the Import History card's closing </div>\n</div> which closes page-imports
old_imports_end = '''  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
      <div class="card-title" style="margin:0">Import History</div>
      <button class="btn btn-ghost btn-sm" onclick="loadBatches()">↻ Refresh</button>
    </div>
    <div id="batch-list"><p class="empty">Loading...</p></div>
  </div>
</div>'''

new_imports_end = old_imports_end.replace('</div>\n</div>', '</div>\n' + csv_import_section + '</div>')

if old_imports_end in html:
    html = html.replace(old_imports_end, new_imports_end)
    print("✓ CSV import section added to Imports page")
else:
    print("✗ Could not find Imports page end marker")

# ═══ 2. Add Reconcile page ═══
reconcile_page = '''<div class="page" id="page-reconcile">
  <div class="grid-2" style="margin-bottom:1rem">
    <div class="card">
      <div class="card-title">Start Reconciliation</div>
      <div class="field"><label>Account</label><select id="recon-account" style="min-width:180px"><option value="">Select account…</option></select></div>
      <div class="field"><label>Statement Date</label><input type="date" id="recon-date"></div>
      <div class="field"><label>Statement Balance ($)</label><input type="number" id="recon-balance" step="0.01" placeholder="e.g. 1234.56"></div>
      <button class="btn btn-primary" onclick="startRecon()" style="margin-top:.5rem">Start Session</button>
    </div>
    <div class="card">
      <div class="card-title">Past Sessions</div>
      <div id="recon-history"><p class="empty">Loading…</p></div>
    </div>
  </div>
  <div class="card" id="recon-active-card" style="display:none">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem;flex-wrap:wrap;gap:.5rem">
      <div>
        <div style="font-size:.95rem;font-weight:600" id="recon-title"></div>
        <div style="font-size:.8rem;color:#64748b" id="recon-subtitle"></div>
      </div>
      <div style="display:flex;gap:.5rem">
        <button class="btn btn-ghost btn-sm" onclick="refreshRecon()">↻ Refresh</button>
        <button class="btn btn-danger btn-sm" onclick="abandonRecon()">Abandon</button>
        <button class="btn btn-success" onclick="completeRecon()" id="recon-complete-btn" disabled>✓ Complete</button>
      </div>
    </div>
    <div class="grid-4" style="margin-bottom:1rem">
      <div class="stat"><div class="stat-label">Statement Balance</div><div class="stat-value" id="recon-stmt-bal">—</div></div>
      <div class="stat"><div class="stat-label">Cleared Balance</div><div class="stat-value" id="recon-cleared-bal">—</div></div>
      <div class="stat"><div class="stat-label">Difference</div><div class="stat-value" id="recon-diff">—</div></div>
      <div class="stat"><div class="stat-label">Cleared Txns</div><div class="stat-value" id="recon-cleared-ct">0</div></div>
    </div>
    <div style="margin-bottom:.5rem;display:flex;gap:.5rem"><button class="btn btn-ghost btn-sm" onclick="reconSelectAll(true)">Select All</button><button class="btn btn-ghost btn-sm" onclick="reconSelectAll(false)">Deselect All</button></div>
    <div style="max-height:500px;overflow-y:auto"><table><thead><tr><th style="width:36px">✓</th><th>Date</th><th>Description</th><th>Category</th><th style="text-align:right">Amount</th></tr></thead><tbody id="recon-txn-tbody"></tbody></table></div>
  </div>
</div>
'''

# Insert reconcile page before the modals section
modal_marker = '<!-- Modals -->'
if modal_marker in html:
    html = html.replace(modal_marker, reconcile_page + '\n' + modal_marker)
    print("✓ Reconcile page added")
else:
    # Try before the first modal
    modal_marker2 = '<div class="modal-bg" id="modal-txn">'
    if modal_marker2 in html:
        html = html.replace(modal_marker2, reconcile_page + '\n' + modal_marker2)
        print("✓ Reconcile page added (before modal-txn)")
    else:
        print("✗ Could not find modal insertion point")

# ═══ 3. Add nav links ═══
# Desktop nav: add Reconcile after Imports
old_nav_imports = '<a data-page="imports">Imports</a>'
new_nav_imports = '<a data-page="imports">Imports</a>\n  <a data-page="reconcile">Reconcile</a>'
if old_nav_imports in html:
    html = html.replace(old_nav_imports, new_nav_imports)
    print("✓ Desktop nav: Reconcile link added")

# Bottom nav: add Reconcile (replace Subs with a combined item or add 8th - add it, mobile will scroll)
# Actually, add it between Import and the closing </nav> of bottom-nav
old_bottom_import = '''  <a data-page="imports"><span class="bnav-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></span><span>Import</span></a>
</nav>'''

new_bottom_import = '''  <a data-page="imports"><span class="bnav-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></span><span>Import</span></a>
  <a data-page="reconcile"><span class="bnav-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></span><span>Recon</span></a>
</nav>'''

if old_bottom_import in html:
    html = html.replace(old_bottom_import, new_bottom_import)
    print("✓ Bottom nav: Reconcile link added")

# ═══ 4. Add showPage handler for reconcile + csv ═══
old_showpage_imports = "if(name==='imports')loadImportsPage();"
new_showpage = "if(name==='imports'){loadImportsPage();loadCsvAccounts();}if(name==='reconcile'){loadReconAccounts();loadReconHistory();}"
if old_showpage_imports in html:
    html = html.replace(old_showpage_imports, new_showpage)
    print("✓ showPage handler updated")

# ═══ 5. Add JS functions ═══
js_functions = '''
/* ── CSV Import UI ── */
async function loadCsvAccounts(){const accts=await api('/api/accounts');$('csv-account').innerHTML='<option value="">Select account…</option>'+accts.map(a=>`<option value="${a.id}">${a.org?a.org+' – ':''}${a.name}</option>`).join('');}
let _csvFile=null,_csvMapping=null;
async function csvPreview(){const acctId=$('csv-account').value;const fileInput=$('csv-file');if(!acctId){alert('Select an account first');return;}if(!fileInput.files.length){alert('Select a CSV file');return;}_csvFile=fileInput.files[0];const fd=new FormData();fd.append('file',_csvFile);fd.append('account_id',acctId);$('csv-preview-btn').disabled=true;$('csv-preview-btn').innerHTML='<span class="spinner"></span>';try{const r=await fetch('/api/csv-import/preview',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const data=await r.json();_csvMapping=data.detected_mapping;$('csv-preview-area').style.display='block';$('csv-detected').innerHTML=_csvMapping?`<span class="badge" style="background:#14532d;color:#86efac">✓ Detected: ${_csvMapping.name}</span> <span style="color:#64748b">${data.total_rows} rows</span>`:`<span class="badge" style="background:#713f12;color:#fde68a">⚠ Unknown format</span> <span style="color:#64748b">${data.total_rows} rows — manual mapping needed</span>`;$('csv-preview-tbody').innerHTML=(data.preview||[]).map(p=>`<tr><td style="color:#64748b">${p._row}</td><td>${p.date_parsed||'<span style="color:#ef4444">⚠</span>'}</td><td>${esc(p.description||'—')}</td><td class="${(p.amount||0)<0?'amt-neg':'amt-pos'}" style="text-align:right">${p.amount!=null?fmt(p.amount):'—'}</td><td style="color:#64748b;font-size:.75rem">${esc(p.csv_category||'')}</td></tr>`).join('');}catch(e){alert('Preview error: '+e.message);}finally{$('csv-preview-btn').disabled=false;$('csv-preview-btn').textContent='Preview';}}
async function csvApply(){if(!_csvFile){alert('No file loaded');return;}const acctId=$('csv-account').value;const cfg={account_id:acctId};if(_csvMapping)cfg.mapping_id=_csvMapping.mapping_id;const fd=new FormData();fd.append('file',_csvFile);fd.append('config',JSON.stringify(cfg));const btn=$('csv-apply-btn');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> Importing…';try{const r=await fetch('/api/csv-import/apply',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const data=await r.json();$('csv-result').innerHTML=`<span style="color:#86efac">✓ Imported ${data.added} transactions</span>`+(data.skipped?` <span style="color:#64748b">(${data.skipped} skipped as dupes)</span>`:'')+(data.errors?` <span style="color:#fca5a5">(${data.errors} parse errors)</span>`:'')+(data.auto_categorized?` <span style="color:#60a5fa">(${data.auto_categorized} auto-categorized)</span>`:'');btn.textContent='Done ✓';btn.className='btn btn-success';loadImportsPage();}catch(e){$('csv-result').innerHTML=`<span style="color:#fca5a5">Error: ${e.message}</span>`;btn.disabled=false;btn.textContent='Import Transactions';}}
function csvReset(){$('csv-preview-area').style.display='none';$('csv-file').value='';_csvFile=null;_csvMapping=null;$('csv-result').innerHTML='';}

/* ── Reconciliation UI ── */
let _reconSessionId=null;
async function loadReconAccounts(){const accts=await api('/api/accounts');$('recon-account').innerHTML='<option value="">Select account…</option>'+accts.map(a=>`<option value="${a.id}">${a.org?a.org+' – ':''}${a.name}</option>`).join('');}
async function loadReconHistory(){try{const sessions=await api('/api/reconcile/sessions?limit=10');if(!sessions.length){$('recon-history').innerHTML='<p class="empty">No reconciliation sessions yet.</p>';return;}$('recon-history').innerHTML=`<table><thead><tr><th>Account</th><th>Date</th><th>Status</th><th></th></tr></thead><tbody>${sessions.map(s=>{const sc=s.status==='completed'?'background:#14532d;color:#86efac':s.status==='abandoned'?'background:#450a0a;color:#fca5a5':'background:#1e3a5f;color:#7dd3fc';return`<tr><td style="font-size:.78rem">${esc(s.account_name)}</td><td style="font-size:.78rem;color:#64748b">${s.statement_date||'—'}</td><td><span class="badge" style="${sc}">${s.status}</span></td><td>${s.status==='open'?`<button class="btn btn-primary btn-sm" onclick="openRecon(${s.id})">Resume</button>`:''}</td></tr>`;}).join('')}</tbody></table>`;}catch(e){$('recon-history').innerHTML=`<p class="empty" style="color:#fca5a5">Error: ${e.message}</p>`;}}
async function startRecon(){const acctId=$('recon-account').value;const dt=$('recon-date').value;const bal=parseFloat($('recon-balance').value);if(!acctId||!dt||isNaN(bal)){alert('Fill in account, date, and balance');return;}try{const r=await api('/api/reconcile/sessions',{method:'POST',body:JSON.stringify({account_id:acctId,statement_date:dt,statement_balance:bal})});openRecon(r.id);}catch(e){alert('Error: '+(e.message||e));}}
async function openRecon(sessionId){_reconSessionId=sessionId;$('recon-active-card').style.display='block';await refreshRecon();}
async function refreshRecon(){if(!_reconSessionId)return;const s=await api('/api/reconcile/sessions/'+_reconSessionId);$('recon-title').textContent=`Reconciling: ${s.account_name}`;$('recon-subtitle').textContent=`Statement: ${s.statement_date} · Balance: ${fmt(s.statement_balance)}`;$('recon-stmt-bal').textContent=fmt(s.statement_balance);$('recon-cleared-bal').textContent=fmt(s.cleared_balance);const diff=s.difference;$('recon-diff').textContent=fmt(diff);$('recon-diff').style.color=Math.abs(diff)<0.01?'#86efac':'#fca5a5';$('recon-cleared-ct').textContent=s.cleared_count;$('recon-complete-btn').disabled=Math.abs(diff)>0.01;const txns=s.transactions||[];$('recon-txn-tbody').innerHTML=txns.map(t=>`<tr style="${t.cleared?'background:#0f2a1f':''}"><td><input type="checkbox" ${t.cleared?'checked':''} onchange="reconToggle('${t.id}',this.checked)"></td><td style="white-space:nowrap;color:#64748b;font-size:.78rem">${t.posted||'—'}</td><td><div style="font-size:.82rem">${esc(t.payee||t.description||'—')}</div></td><td>${t.category?`<span class="badge" style="background:#1e253066;color:#94a3b8">${esc(t.category)}</span>`:''}</td><td class="${t.amount<0?'amt-neg':'amt-pos'}" style="text-align:right">${fmt(t.amount)}</td></tr>`).join('');loadReconHistory();}
async function reconToggle(txnId,cleared){await api(`/api/reconcile/sessions/${_reconSessionId}/clear`,{method:'POST',body:JSON.stringify({txn_ids:[txnId],cleared})});refreshRecon();}
async function reconSelectAll(val){const cbs=document.querySelectorAll('#recon-txn-tbody input[type=checkbox]');const ids=[];cbs.forEach(cb=>{const tr=cb.closest('tr');const txnId=cb.getAttribute('onchange').match(/'([^']+)'/)[1];if(!!cb.checked!==val)ids.push(txnId);});if(ids.length)await api(`/api/reconcile/sessions/${_reconSessionId}/clear`,{method:'POST',body:JSON.stringify({txn_ids:ids,cleared:val})});refreshRecon();}
async function completeRecon(){if(!confirm('Complete this reconciliation? All cleared transactions will be marked as reconciled.'))return;try{await api(`/api/reconcile/sessions/${_reconSessionId}/complete`,{method:'POST',body:JSON.stringify({})});_reconSessionId=null;$('recon-active-card').style.display='none';loadReconHistory();}catch(e){alert('Error: '+(e.message||e));}}
async function abandonRecon(){if(!confirm('Abandon this session? All cleared marks will be removed.'))return;try{await api(`/api/reconcile/sessions/${_reconSessionId}/abandon`,{method:'POST',body:JSON.stringify({})});_reconSessionId=null;$('recon-active-card').style.display='none';loadReconHistory();}catch(e){alert('Error: '+(e.message||e));}}
'''

# Insert before the closing </script>
# Find the last </script> tag
last_script_close = html.rfind('</script>')
if last_script_close > 0:
    html = html[:last_script_close] + js_functions + '\n' + html[last_script_close:]
    print("✓ JS functions injected")
else:
    print("✗ Could not find </script> tag")

with open(PATH, "w") as f:
    f.write(html)

print("\n=== Patch complete ===")

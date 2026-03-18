// Finance Hub — imports.js
// Import batches, duplicate review, CSV import

let _csvFile=null,_csvMapping=null;

async function loadImportsPage() { loadDupeStats(); loadDupes(); loadBatches(); }

async function loadDupeStats() {
  try {
    const stats = await api('/api/duplicates/stats');
    $('imp-dupe-count').textContent = stats.pending || '0';
    $('imp-dupe-count').style.color = stats.pending > 0 ? '#fbbf24' : '#86efac';
  } catch(e) { console.error('Dupe stats:', e); }
  try {
    const batches = await api('/api/import-batches?limit=1');
    $('imp-batch-count').textContent = batches.length > 0 ? batches[0].id : '0';
  } catch(e) { console.error('Batch count:', e); }
}

async function loadDupes() {
  try {
    const dupes = await api('/api/duplicates?status=pending&limit=50');
    if (!dupes.length) {
      $('dupe-list').innerHTML = '<p class="empty" style="color:#86efac">No pending duplicates.</p>';
      return;
    }
    $('dupe-list').innerHTML = dupes.map(d => {
      const n = d.new_txn, e = d.existing_txn;
      return `<div style="border:1px solid #1e2530;border-radius:8px;padding:.8rem;margin-bottom:.6rem;background:#0f1117">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.5rem;flex-wrap:wrap;gap:.3rem">
          <span style="font-size:.72rem;color:#fbbf24;font-weight:500">\u26a0 Possible Duplicate</span>
          <span style="font-size:.7rem;color:#475569">Batch #${d.batch_id}</span>
        </div>
        <div class="dupe-compare" style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-bottom:.6rem">
          <div style="padding:.5rem;background:#161b27;border-radius:6px">
            <div style="font-size:.68rem;color:#475569;margin-bottom:.2rem">NEW (imported)</div>
            <div style="font-size:.82rem;color:#e2e8f0">${esc(n.payee||n.description||'\u2014')}</div>
            <div style="font-size:.75rem;color:#64748b">${n.account} \u00b7 ${n.posted||''}</div>
            <div class="${n.amount<0?'amt-neg':'amt-pos'}" style="font-size:.88rem;font-weight:600">${fmt(n.amount)}</div>
          </div>
          <div style="padding:.5rem;background:#161b27;border-radius:6px">
            <div style="font-size:.68rem;color:#475569;margin-bottom:.2rem">EXISTING</div>
            <div style="font-size:.82rem;color:#e2e8f0">${esc(e.payee||e.description||'\u2014')}</div>
            <div style="font-size:.75rem;color:#64748b">${e.account} \u00b7 ${e.posted||''}</div>
            <div class="${e.amount<0?'amt-neg':'amt-pos'}" style="font-size:.88rem;font-weight:600">${fmt(e.amount)}</div>
          </div>
        </div>
        <div style="font-size:.72rem;color:#475569;margin-bottom:.5rem">${d.reason}</div>
        <div style="display:flex;gap:.4rem;flex-wrap:wrap">
          <button class="btn btn-success btn-sm" onclick="resolveDupe(${d.id},'keep_both')">Keep Both</button>
          <button class="btn btn-danger btn-sm" onclick="resolveDupe(${d.id},'remove_new')">Remove New</button>
          <button class="btn btn-warning btn-sm" onclick="resolveDupe(${d.id},'remove_existing')">Remove Existing</button>
        </div>
      </div>`;
    }).join('');
  } catch(err) {
    $('dupe-list').innerHTML = `<p class="empty" style="color:#fca5a5">Error: ${err.message}</p>`;
  }
}

async function resolveDupe(flagId, action) {
  try {
    await api('/api/duplicates/' + flagId + '/resolve', {
      method: 'POST', body: JSON.stringify({ action })
    });
    loadDupes(); loadDupeStats();
  } catch(err) { toast('Error: ' + err.message,'error'); }
}

async function loadBatches() {
  try {
    const batches = await api('/api/import-batches?limit=20');
    if (!batches.length) {
      $('batch-list').innerHTML = '<p class="empty">No imports yet. Sync to create the first batch.</p>';
      return;
    }
    $('batch-list').innerHTML = `<table><thead><tr>
      <th>Batch</th><th>Time</th><th>Status</th><th>Accts</th><th>Added</th><th>Updated</th><th>Dupes</th><th>Error</th>
      </tr></thead><tbody>${batches.map(b => {
        const sc = b.status==='ok'?'background:#14532d;color:#86efac':b.status==='error'?'background:#450a0a;color:#fca5a5':'background:#1e2530;color:#94a3b8';
        const t = b.finished_at ? new Date(b.finished_at).toLocaleString() : '\u2014';
        return `<tr>
          <td style="font-weight:500">#${b.id}</td>
          <td style="font-size:.75rem;color:#64748b;white-space:nowrap">${t}</td>
          <td><span class="badge" style="${sc}">${b.status}</span></td>
          <td>${b.accounts_seen||0}</td>
          <td style="color:#86efac">${b.txns_added||0}</td>
          <td>${b.txns_updated||0}</td>
          <td style="${b.dupes_flagged>0?'color:#fbbf24;font-weight:600':'color:#64748b'}">${b.dupes_flagged||0}</td>
          <td style="font-size:.72rem;color:#ef4444;max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(b.error_message||'')}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
  } catch(err) {
    $('batch-list').innerHTML = `<p class="empty" style="color:#fca5a5">Error: ${err.message}</p>`;
  }
}

async function loadCsvAccounts(){const accts=await api('/api/accounts');$('csv-account').innerHTML='<option value="">Select account…</option>'+accts.map(a=>`<option value="${a.id}">${a.org?a.org+' – ':''}${a.name}</option>`).join('');}

async function csvPreview(){const acctId=$('csv-account').value;const fileInput=$('csv-file');if(!acctId){toast('Select an account first','error');return;}if(!fileInput.files.length){toast('Select a CSV file','error');return;}_csvFile=fileInput.files[0];const fd=new FormData();fd.append('file',_csvFile);fd.append('account_id',acctId);$('csv-preview-btn').disabled=true;$('csv-preview-btn').innerHTML='<span class="spinner"></span>';try{const r=await fetch('/api/csv-import/preview',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const data=await r.json();_csvMapping=data.detected_mapping;$('csv-preview-area').style.display='block';$('csv-detected').innerHTML=_csvMapping?`<span class="badge" style="background:#14532d;color:#86efac">✓ Detected: ${_csvMapping.name}</span> <span style="color:#64748b">${data.total_rows} rows</span>`:`<span class="badge" style="background:#713f12;color:#fde68a">⚠ Unknown format</span> <span style="color:#64748b">${data.total_rows} rows — manual mapping needed</span>`;$('csv-preview-tbody').innerHTML=(data.preview||[]).map(p=>`<tr><td style="color:#64748b">${p._row}</td><td>${p.date_parsed||'<span style="color:#ef4444">⚠</span>'}</td><td>${esc(p.description||'—')}</td><td class="${(p.amount||0)<0?'amt-neg':'amt-pos'}" style="text-align:right">${p.amount!=null?fmt(p.amount):'—'}</td><td style="color:#64748b;font-size:.75rem">${esc(p.csv_category||'')}</td></tr>`).join('');}catch(e){toast('Preview error: '+e.message,'error');}finally{$('csv-preview-btn').disabled=false;$('csv-preview-btn').textContent='Preview';}}
async function csvApply(){if(!_csvFile){alert('No file loaded');return;}const acctId=$('csv-account').value;const cfg={account_id:acctId};if(_csvMapping)cfg.mapping_id=_csvMapping.mapping_id;const fd=new FormData();fd.append('file',_csvFile);fd.append('config',JSON.stringify(cfg));const btn=$('csv-apply-btn');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> Importing…';try{const r=await fetch('/api/csv-import/apply',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const data=await r.json();$('csv-result').innerHTML=`<span style="color:#86efac">✓ Imported ${data.added} transactions</span>`+(data.skipped?` <span style="color:#64748b">(${data.skipped} skipped as dupes)</span>`:'')+(data.errors?` <span style="color:#fca5a5">(${data.errors} parse errors)</span>`:'')+(data.auto_categorized?` <span style="color:#60a5fa">(${data.auto_categorized} auto-categorized)</span>`:'');btn.textContent='Done ✓';btn.className='btn btn-success';loadImportsPage();}catch(e){$('csv-result').innerHTML=`<span style="color:#fca5a5">Error: ${e.message}</span>`;btn.disabled=false;btn.textContent='Import Transactions';}}
function csvReset(){$('csv-preview-area').style.display='none';$('csv-file').value='';_csvFile=null;_csvMapping=null;$('csv-result').innerHTML='';}

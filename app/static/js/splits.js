// Finance Hub — splits.js
// Split transaction modal

let _splitTxn = null;
let _splitRows = [];

async function openSplitModal(txnId) {
  const t = _txnList.find(x => x.id === txnId);
  if (!t) { toast('Transaction not found', 'error'); return; }
  _splitTxn = t;

  $('sp-txn-desc').textContent = t.payee || t.description || 'Unknown';
  $('sp-txn-amt').textContent = fmt(t.amount);
  $('sp-txn-amt').className = t.amount < 0 ? 'amt-neg' : 'amt-pos';

  // Load existing splits or create default 2-row split
  try {
    const existing = await api('/api/splits/' + txnId);
    if (existing.length >= 2) {
      _splitRows = existing.map(s => ({
        category_id: s.category_id || '',
        amount: s.amount,
        description: s.description || ''
      }));
    } else {
      _splitRows = [
        { category_id: t.category_id || '', amount: t.amount, description: '' },
        { category_id: '', amount: 0, description: '' }
      ];
    }
  } catch (e) {
    _splitRows = [
      { category_id: t.category_id || '', amount: t.amount, description: '' },
      { category_id: '', amount: 0, description: '' }
    ];
  }

  renderSplitRows();
  $('sp-save-result').innerHTML = '';
  openModal('modal-splits');
}

function renderSplitRows() {
  const catOpts = '<option value="">Uncategorized</option>' +
    categories.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');

  $('sp-rows').innerHTML = _splitRows.map((r, i) => `
    <div style="display:grid;grid-template-columns:1fr 100px 1fr 30px;gap:.4rem;align-items:end;margin-bottom:.4rem">
      <div class="field" style="margin:0">
        ${i === 0 ? '<label style="font-size:.68rem">Category</label>' : ''}
        <select onchange="_splitRows[${i}].category_id=this.value?parseInt(this.value):''" style="font-size:.78rem;padding:.35rem .5rem">
          ${catOpts.replace(`value="${r.category_id}"`, `value="${r.category_id}" selected`)}
        </select>
      </div>
      <div class="field" style="margin:0">
        ${i === 0 ? '<label style="font-size:.68rem">Amount</label>' : ''}
        <input type="number" step="0.01" value="${r.amount}" onchange="_splitRows[${i}].amount=parseFloat(this.value)||0;updateSplitRemaining()" style="font-size:.78rem;padding:.35rem .5rem;text-align:right">
      </div>
      <div class="field" style="margin:0">
        ${i === 0 ? '<label style="font-size:.68rem">Note</label>' : ''}
        <input type="text" value="${esc(r.description)}" onchange="_splitRows[${i}].description=this.value" placeholder="Optional" style="font-size:.78rem;padding:.35rem .5rem">
      </div>
      <div style="text-align:center;padding-bottom:2px">
        ${_splitRows.length > 2 ? `<button class="btn btn-ghost btn-sm" style="color:#ef4444;padding:.2rem .4rem" onclick="removeSplitRow(${i})">✕</button>` : ''}
      </div>
    </div>
  `).join('');

  updateSplitRemaining();
}

function addSplitRow() {
  _splitRows.push({ category_id: '', amount: 0, description: '' });
  renderSplitRows();
}

function removeSplitRow(idx) {
  _splitRows.splice(idx, 1);
  renderSplitRows();
}

function updateSplitRemaining() {
  if (!_splitTxn) return;
  const total = _splitTxn.amount;
  const sum = _splitRows.reduce((s, r) => s + (r.amount || 0), 0);
  const diff = total - sum;
  const el = $('sp-remaining');
  if (Math.abs(diff) < 0.01) {
    el.innerHTML = '<span style="color:#86efac">✓ Balanced</span>';
  } else {
    el.innerHTML = `<span style="color:#fca5a5">Remaining: ${fmt(diff)}</span>`;
  }
}

async function saveSplits() {
  if (!_splitTxn) return;
  const total = _splitTxn.amount;
  const sum = _splitRows.reduce((s, r) => s + (r.amount || 0), 0);
  if (Math.abs(sum - total) > 0.01) {
    toast('Splits must sum to ' + fmt(total), 'error');
    return;
  }

  try {
    await api('/api/splits', {
      method: 'POST',
      body: JSON.stringify({
        txn_id: _splitTxn.id,
        splits: _splitRows.map(r => ({
          category_id: r.category_id || null,
          amount: r.amount,
          description: r.description || null
        }))
      })
    });
    toast('Split saved', 'success');
    $('sp-save-result').innerHTML = '<span style="color:#86efac">✓ Saved</span>';
    setTimeout(() => closeModal('modal-splits'), 600);
    loadTxns();
  } catch (e) {
    $('sp-save-result').innerHTML = `<span style="color:#fca5a5">Error: ${e.message}</span>`;
  }
}

async function removeSplits() {
  if (!_splitTxn) return;
  try {
    await api('/api/splits/' + _splitTxn.id, { method: 'DELETE' });
    toast('Splits removed', 'success');
    closeModal('modal-splits');
    loadTxns();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// Finance Hub — tags.js
// Tag management + transaction tagging in edit modal

let _allTags = [];

async function loadAllTags() {
  try {
    _allTags = await api('/api/tags');
  } catch (e) { console.error('Tags load:', e); _allTags = []; }
}

function renderTagCheckboxes(txnTags) {
  const el = $('mt-tags');
  if (!el) return;
  if (!_allTags.length) { el.innerHTML = '<span style="color:#475569;font-size:.75rem">No tags defined</span>'; return; }
  const tagIds = new Set((txnTags || []).map(t => t.id));
  el.innerHTML = _allTags.map(t =>
    `<label style="display:inline-flex;align-items:center;gap:.3rem;cursor:pointer;margin-right:.6rem;font-size:.78rem;color:#e2e8f0">
      <input type="checkbox" data-tag-id="${t.id}" ${tagIds.has(t.id) ? 'checked' : ''}>
      <span class="badge" style="background:${t.color}22;color:${t.color}">${esc(t.name)}</span>
    </label>`
  ).join('');
}

async function loadTxnTags(txnId) {
  try {
    const tags = await api('/api/tags/transaction/' + txnId);
    return tags;
  } catch (e) { return []; }
}

async function saveTxnTags(txnId) {
  const el = $('mt-tags');
  if (!el) return;
  const checkboxes = el.querySelectorAll('input[data-tag-id]');
  const tagIds = [];
  checkboxes.forEach(cb => { if (cb.checked) tagIds.push(parseInt(cb.dataset.tagId)); });
  try {
    await api('/api/tags/assign', {
      method: 'POST',
      body: JSON.stringify({ txn_id: txnId, tag_ids: tagIds })
    });
  } catch (e) { console.error('Tag save:', e); }
}

// Tag badges in transaction list
function tagBadges(txnTags) {
  if (!txnTags || !txnTags.length) return '';
  return txnTags.map(t =>
    `<span class="badge" style="background:${t.color}22;color:${t.color};font-size:.58rem;margin-left:.2rem">${esc(t.name)}</span>`
  ).join('');
}

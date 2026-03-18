// Finance Hub — bulk.js
// Bulk selection mode for transactions: select, categorize, tag, review

let _bulkMode = false;
let _bulkSelected = new Set();

function toggleBulkMode() {
  _bulkMode = !_bulkMode;
  _bulkSelected.clear();
  var btn = $('bulk-toggle-btn');
  if (btn) {
    btn.textContent = _bulkMode ? '✕ Cancel' : '☑ Select';
    btn.className = _bulkMode ? 'btn btn-warning btn-sm' : 'btn btn-ghost btn-sm';
  }
  var bar = $('bulk-action-bar');
  if (bar) bar.style.display = _bulkMode ? 'flex' : 'none';
  updateBulkCount();
  // Re-render to show checkboxes
  loadTxns();
}

function toggleBulkItem(txnId, checkbox) {
  if (checkbox.checked) {
    _bulkSelected.add(txnId);
  } else {
    _bulkSelected.delete(txnId);
  }
  updateBulkCount();
}

function bulkSelectAll() {
  _txnList.forEach(function(t) { _bulkSelected.add(t.id); });
  document.querySelectorAll('.bulk-check').forEach(function(cb) { cb.checked = true; });
  updateBulkCount();
}

function bulkDeselectAll() {
  _bulkSelected.clear();
  document.querySelectorAll('.bulk-check').forEach(function(cb) { cb.checked = false; });
  updateBulkCount();
}

function updateBulkCount() {
  var el = $('bulk-count');
  if (el) el.textContent = _bulkSelected.size + ' selected';
  // Enable/disable action buttons
  var disabled = _bulkSelected.size === 0;
  document.querySelectorAll('.bulk-action-btn').forEach(function(b) { b.disabled = disabled; });
}

async function bulkCategorize() {
  if (!_bulkSelected.size) return;
  var catId = $('bulk-category').value;
  try {
    var result = await api('/api/bulk/categorize', {
      method: 'POST',
      body: JSON.stringify({
        txn_ids: Array.from(_bulkSelected),
        category_id: catId ? parseInt(catId) : null
      })
    });
    toast(result.updated + ' transactions categorized', 'success');
    _bulkSelected.clear();
    updateBulkCount();
    loadTxns();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function bulkTag() {
  if (!_bulkSelected.size) return;
  var tagId = $('bulk-tag').value;
  if (!tagId) return toast('Select a tag', 'error');
  try {
    var result = await api('/api/bulk/tag', {
      method: 'POST',
      body: JSON.stringify({
        txn_ids: Array.from(_bulkSelected),
        tag_id: parseInt(tagId),
        action: 'add'
      })
    });
    toast(result.affected + ' tags applied', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function bulkMarkReviewed() {
  if (!_bulkSelected.size) return;
  try {
    var result = await api('/api/bulk/mark-reviewed', {
      method: 'POST',
      body: JSON.stringify({ txn_ids: Array.from(_bulkSelected) })
    });
    toast(result.reviewed + ' marked reviewed', 'success');
    _bulkSelected.clear();
    updateBulkCount();
    loadTxns();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function bulkMarkTransfer(isTransfer) {
  if (!_bulkSelected.size) return;
  try {
    var result = await api('/api/bulk/transfer', {
      method: 'POST',
      body: JSON.stringify({
        txn_ids: Array.from(_bulkSelected),
        is_transfer: isTransfer
      })
    });
    toast(result.updated + ' updated', 'success');
    _bulkSelected.clear();
    updateBulkCount();
    loadTxns();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

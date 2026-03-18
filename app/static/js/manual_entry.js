// Finance Hub — manual_entry.js
// Manual transaction creation + deletion

async function openManualTxnModal() {
  // Load accounts and categories if not loaded
  if (!accounts.length) await loadAccounts();
  if (!categories.length) await loadCategories();

  // Populate account dropdown
  const acctSel = $('me-account');
  acctSel.innerHTML = '<option value="">Select account…</option>' +
    accounts.map(a => `<option value="${a.id}">${a.org ? a.org + ' – ' : ''}${a.name}</option>`).join('');

  // Populate category dropdown
  const catSel = $('me-category');
  catSel.innerHTML = '<option value="">No category</option>' +
    categories.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');

  // Reset form
  $('me-date').value = new Date().toISOString().slice(0, 10);
  $('me-payee').value = '';
  $('me-description').value = '';
  $('me-amount').value = '';
  $('me-notes').value = '';
  $('me-type').value = 'expense';
  $('me-is-transfer').checked = false;
  $('me-result').innerHTML = '';
  $('me-save-btn').disabled = false;
  $('me-save-btn').textContent = 'Save Transaction';
  $('me-save-btn').className = 'btn btn-primary';

  openModal('modal-manual-entry');
}

async function saveManualTxn() {
  const accountId = $('me-account').value;
  const posted = $('me-date').value;
  const rawAmount = parseFloat($('me-amount').value);
  const txnType = $('me-type').value;
  const description = $('me-description').value.trim();
  const payee = $('me-payee').value.trim();
  const categoryId = $('me-category').value ? parseInt($('me-category').value) : null;
  const notes = $('me-notes').value.trim();
  const isTransfer = $('me-is-transfer').checked;

  // Validation
  if (!accountId) { toast('Select an account', 'error'); return; }
  if (!posted) { toast('Enter a date', 'error'); return; }
  if (isNaN(rawAmount) || rawAmount === 0) { toast('Enter a valid amount', 'error'); return; }
  if (!description && !payee) { toast('Enter a description or payee', 'error'); return; }

  // Apply sign based on type
  const amount = txnType === 'expense' ? -Math.abs(rawAmount) : Math.abs(rawAmount);

  const btn = $('me-save-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Saving…';

  try {
    const result = await api('/api/transactions', {
      method: 'POST',
      body: JSON.stringify({
        account_id: accountId,
        posted: posted,
        amount: amount,
        description: description || payee,
        payee: payee || null,
        category_id: categoryId,
        notes: notes || null,
        is_transfer: isTransfer,
      })
    });

    $('me-result').innerHTML = `<span style="color:#86efac">✓ Transaction saved (${fmt(amount)})</span>`;
    btn.textContent = 'Saved ✓';
    btn.className = 'btn btn-success';
    toast('Manual transaction added', 'success');

    // Refresh transaction list
    loadTxns();
    if (typeof loadDashboard === 'function') loadDashboard();

    // Close after brief delay
    setTimeout(() => closeModal('modal-manual-entry'), 800);

  } catch (e) {
    $('me-result').innerHTML = `<span style="color:#fca5a5">Error: ${e.message}</span>`;
    btn.disabled = false;
    btn.textContent = 'Save Transaction';
    btn.className = 'btn btn-primary';
  }
}

async function deleteManualTxn(txnId) {
  customConfirm(
    'Delete this manually entered transaction? This cannot be undone.',
    async () => {
      try {
        await api('/api/transactions/' + txnId, { method: 'DELETE' });
        toast('Transaction deleted', 'success');
        closeModal('modal-txn');
        loadTxns();
        if (typeof loadDashboard === 'function') loadDashboard();
      } catch (e) {
        toast('Error: ' + e.message, 'error');
      }
    },
    'Delete',
    'btn btn-danger'
  );
}

// Finance Hub — account_detail.js
// Account detail modal for CC/loan metadata editing

let _detailAcct = null;

async function openAccountDetail(acctId) {
  const accts = await api('/api/accounts');
  _detailAcct = accts.find(a => a.id === acctId);
  if (!_detailAcct) { toast('Account not found', 'error'); return; }

  const a = _detailAcct;
  $('ad-title').textContent = a.name;
  $('ad-subtitle').textContent = (a.org || '') + ' · ' + (a.account_type || 'checking');
  $('ad-balance').textContent = fmt(a.balance);
  $('ad-balance').className = a.balance < 0 ? 'amt-neg' : 'amt-pos';

  // Show/hide CC vs Loan sections
  const isCC = a.account_type === 'credit';
  const isLoan = ['loan', 'mortgage'].includes(a.account_type);
  $('ad-cc-section').style.display = isCC ? 'block' : 'none';
  $('ad-loan-section').style.display = isLoan ? 'block' : 'none';
  $('ad-no-meta').style.display = (!isCC && !isLoan) ? 'block' : 'none';

  // Fill CC fields
  if (isCC) {
    $('ad-due-day').value = a.payment_due_day || '';
    $('ad-min-payment').value = a.minimum_payment || '';
    $('ad-apr').value = a.apr || '';
    $('ad-credit-limit').value = a.credit_limit || '';
    $('ad-autopay').checked = !!a.autopay_enabled;

    // Show utilization if we have limit
    const utilEl = $('ad-utilization');
    if (a.credit_limit && a.balance) {
      const util = Math.abs(a.balance) / a.credit_limit * 100;
      const color = util > 80 ? '#ef4444' : util > 50 ? '#f59e0b' : '#22c55e';
      utilEl.innerHTML = `<div style="font-size:.72rem;color:#475569;margin-bottom:.2rem">Utilization</div>`
        + `<div style="background:#1e2530;border-radius:4px;height:10px;overflow:hidden;margin-bottom:.2rem">`
        + `<div style="width:${Math.min(util, 100)}%;background:${color};height:100%;border-radius:4px"></div></div>`
        + `<div style="font-size:.8rem;font-weight:600;color:${color}">${util.toFixed(1)}%</div>`;
      utilEl.style.display = 'block';
    } else {
      utilEl.style.display = 'none';
    }
  }

  // Fill loan fields
  if (isLoan) {
    $('ad-loan-rate').value = a.loan_rate || '';
    $('ad-loan-term').value = a.loan_term_months || '';
    $('ad-loan-payment').value = a.loan_payment || '';
    $('ad-loan-maturity').value = a.loan_maturity_date || '';
  }

  $('ad-save-result').innerHTML = '';
  openModal('modal-account-detail');
}

async function saveAccountDetail() {
  if (!_detailAcct) return;
  const a = _detailAcct;
  const body = {};

  if (a.account_type === 'credit') {
    const dueDay = parseInt($('ad-due-day').value);
    if (dueDay && dueDay >= 1 && dueDay <= 31) body.payment_due_day = dueDay;
    const minPay = parseFloat($('ad-min-payment').value);
    if (!isNaN(minPay)) body.minimum_payment = minPay;
    const apr = parseFloat($('ad-apr').value);
    if (!isNaN(apr)) body.apr = apr;
    const limit = parseFloat($('ad-credit-limit').value);
    if (!isNaN(limit)) body.credit_limit = limit;
    body.autopay_enabled = $('ad-autopay').checked;
  }

  if (['loan', 'mortgage'].includes(a.account_type)) {
    const rate = parseFloat($('ad-loan-rate').value);
    if (!isNaN(rate)) body.loan_rate = rate;
    const term = parseInt($('ad-loan-term').value);
    if (term) body.loan_term_months = term;
    const payment = parseFloat($('ad-loan-payment').value);
    if (!isNaN(payment)) body.loan_payment = payment;
    const maturity = $('ad-loan-maturity').value;
    if (maturity) body.loan_maturity_date = maturity;
  }

  if (!Object.keys(body).length) {
    closeModal('modal-account-detail');
    return;
  }

  try {
    await api('/api/accounts/' + a.id, { method: 'PATCH', body: JSON.stringify(body) });
    toast('Account details saved', 'success');
    $('ad-save-result').innerHTML = '<span style="color:#86efac">✓ Saved</span>';
    setTimeout(() => closeModal('modal-account-detail'), 600);
    loadAccountsSettings();
  } catch (e) {
    $('ad-save-result').innerHTML = '<span style="color:#fca5a5">Error: ' + e.message + '</span>';
  }
}

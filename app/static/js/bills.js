// Finance Hub — bills.js
// Upcoming bills view + debt payoff calculator

async function loadBillsPage() {
  loadUpcomingBills();
  loadDebtPayoff();
}

async function loadUpcomingBills() {
  var el = $('bills-list');
  try {
    var data = await api('/api/bills/upcoming?days=45');
    if (!data.bills.length) {
      el.innerHTML = '<p class="empty">No upcoming bills detected. Set due dates on credit card accounts or mark transactions as recurring.</p>';
      $('bills-total').textContent = fmt(0);
      $('bills-count').textContent = '0';
      return;
    }
    $('bills-total').textContent = fmt(data.total_upcoming);
    $('bills-count').textContent = data.count;

    el.innerHTML = data.bills.map(function(b) {
      var urgent = b.days_until <= 3;
      var soon = b.days_until <= 7;
      var overdue = b.overdue;
      var borderColor = overdue ? '#ef4444' : urgent ? '#f59e0b' : soon ? '#fbbf24' : '#1e2530';
      var dueLabel = overdue ? '<span style="color:#ef4444;font-weight:600">OVERDUE</span>'
        : b.days_until === 0 ? '<span style="color:#f59e0b;font-weight:600">TODAY</span>'
        : b.days_until === 1 ? '<span style="color:#fbbf24">Tomorrow</span>'
        : b.days_until + ' days';
      var icon = b.source === 'account' ? '\uD83C\uDFE6' : '\u21BB';
      var autopayBadge = b.autopay ? '<span class="badge" style="background:#14532d;color:#86efac;font-size:.6rem;margin-left:.3rem">autopay</span>' : '';

      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.7rem .8rem;border:1px solid ' + borderColor + ';border-radius:8px;margin-bottom:.5rem;background:#0f1117">'
        + '<div>'
        + '<div style="font-size:.85rem;color:#e2e8f0">' + icon + ' ' + esc(b.name) + autopayBadge + '</div>'
        + '<div style="font-size:.72rem;color:#64748b">' + b.due_date + (b.account_name ? ' \u00b7 ' + esc(b.account_name) : '') + '</div>'
        + '</div>'
        + '<div style="text-align:right">'
        + '<div class="amt-neg" style="font-size:.88rem;font-weight:600">' + (b.amount ? fmt(b.amount) : '\u2014') + '</div>'
        + '<div style="font-size:.72rem">' + dueLabel + '</div>'
        + '</div></div>';
    }).join('');
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

async function loadDebtPayoff() {
  var extra = parseFloat($('dp-extra') ? $('dp-extra').value : '0') || 0;
  var strategy = $('dp-strategy') ? $('dp-strategy').value : 'avalanche';
  var el = $('debt-payoff-results');
  try {
    var data = await api('/api/debt/payoff?extra_monthly=' + extra + '&strategy=' + strategy);
    if (!data.debts || !data.debts.length) {
      if (!data.message) {
        el.innerHTML = '<p class="empty">No debt accounts found. Set account types to credit/loan/mortgage in Settings, then add rate + payment info.</p>';
        return;
      }
    }

    var html = '';
    if (data.message) {
      html += '<div style="padding:.6rem .8rem;background:#713f12;border:1px solid #92400e;border-radius:8px;margin-bottom:1rem;font-size:.82rem;color:#fde68a">'
        + '\u26a0 ' + data.message
        + ' \u2014 click Edit on any row below to add details.</div>';
    }
    html += '<div class="grid-4" style="margin-bottom:1rem">'
      + '<div class="stat"><div class="stat-label">Total Debt</div><div class="stat-value amt-neg">' + fmt(data.total_balance) + '</div></div>'
      + '<div class="stat"><div class="stat-label">Monthly Payments</div><div class="stat-value">' + fmt(data.total_min_payment) + '</div></div>'
      + '<div class="stat"><div class="stat-label">Debt-Free In</div><div class="stat-value" style="color:#22c55e">' + (data.months_to_payoff ? data.months_to_payoff + ' mo' : '\u2014') + '</div>'
      + (data.debt_free_date ? '<div class="stat-sub">' + data.debt_free_date + '</div>' : '') + '</div>'
      + '<div class="stat"><div class="stat-label">Total Interest</div><div class="stat-value" style="color:#f59e0b">' + fmt(data.total_interest) + '</div>'
      + (data.months_saved ? '<div class="stat-sub" style="color:#22c55e">' + data.months_saved + ' months saved vs minimum</div>' : '') + '</div>'
      + '</div>';

    // Card-style debt list instead of table
    html += '<div style="display:flex;flex-direction:column;gap:.5rem">';
    data.debts.forEach(function(d) {
      var dateStr = d.paid_off_date ? d.paid_off_date.slice(0, 7) : '';
      var moStr = d.paid_off_month ? d.paid_off_month + ' mo' : '\u2014';
      var needsData = !d.rate && !d.min_payment;
      var cardBorder = needsData ? '#92400e' : '#1e2530';

      html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;border:1px solid ' + cardBorder + ';border-radius:8px;background:#0f1117">'
        // Left: name + type
        + '<div style="flex:1;min-width:0">'
        + '<div style="font-size:.85rem;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(d.name) + '</div>'
        + '<div style="font-size:.72rem;color:#64748b">' + d.type
        + (d.rate ? ' \u00b7 ' + d.rate.toFixed(2) + '% APR' : '')
        + (d.min_payment ? ' \u00b7 ' + fmt(d.min_payment) + '/mo' : '')
        + '</div>'
        + '</div>'
        // Center: balance
        + '<div style="text-align:right;margin:0 1rem">'
        + '<div class="amt-neg" style="font-size:.92rem;font-weight:600">' + fmt(d.starting_balance) + '</div>'
        + (d.paid_off_month ? '<div style="font-size:.72rem;color:#86efac">' + moStr + '</div>' : '')
        + '</div>'
        // Right: edit button
        + (d.id && typeof openAccountDetail === 'function'
          ? '<button class="btn btn-primary" style="padding:.5rem 1rem;font-size:.82rem;min-width:70px" onclick="openAccountDetail(\'' + d.id + '\')">\u270f Edit</button>'
          : '')
        + '</div>';
    });
    html += '</div>';

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

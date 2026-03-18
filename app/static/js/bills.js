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

      var clickAction = b.account_id
        ? 'onclick="showPage(\'transactions\');$(\'t-account\').value=\'' + b.account_id + '\';loadTxns()"'
        : '';
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.7rem .8rem;border:1px solid ' + borderColor + ';border-radius:8px;margin-bottom:.5rem;background:#0f1117;cursor:pointer" ' + clickAction + '>'
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
      if (data.message) {
        // Has debts but no payment data — show table anyway with message
      } else {
        el.innerHTML = '<p class="empty">No debt accounts found. Set account types to credit/loan/mortgage in Settings, then add rate + payment info.</p>';
        return;
      }
      return;
    }

    var html = '';
    if (data.message) {
      html += '<div style="padding:.6rem .8rem;background:#713f12;border:1px solid #92400e;border-radius:8px;margin-bottom:1rem;font-size:.82rem;color:#fde68a">'
        + '⚠ ' + data.message
        + ' <span style="color:#fbbf24;cursor:pointer;text-decoration:underline" onclick="showPage(\'settings\')">Go to Settings →</span></div>';
    }
    html += '<div class="grid-4" style="margin-bottom:1rem">'
      + '<div class="stat"><div class="stat-label">Total Debt</div><div class="stat-value amt-neg">' + fmt(data.total_balance) + '</div></div>'
      + '<div class="stat"><div class="stat-label">Monthly Payments</div><div class="stat-value">' + fmt(data.total_min_payment) + '</div></div>'
      + '<div class="stat"><div class="stat-label">Debt-Free In</div><div class="stat-value" style="color:#22c55e">' + (data.months_to_payoff ? data.months_to_payoff + ' mo' : '\u2014') + '</div>'
      + (data.debt_free_date ? '<div class="stat-sub">' + data.debt_free_date + '</div>' : '') + '</div>'
      + '<div class="stat"><div class="stat-label">Total Interest</div><div class="stat-value" style="color:#f59e0b">' + fmt(data.total_interest) + '</div>'
      + (data.months_saved ? '<div class="stat-sub" style="color:#22c55e">' + data.months_saved + ' months saved vs minimum</div>' : '') + '</div>'
      + '</div>';

    html += '<table style="font-size:.8rem"><thead><tr><th>Account</th><th>Type</th><th style="text-align:right">Balance</th><th style="text-align:right">Rate</th><th style="text-align:right">Payment</th><th>Payoff</th></tr></thead><tbody>';
    data.debts.forEach(function(d) {
      var dateStr = d.paid_off_date ? d.paid_off_date.slice(0, 7) : '\u2014';
      var moStr = d.paid_off_month ? d.paid_off_month + ' mo' : '\u2014';
      var nameLink = typeof openAccountDetail === 'function' && d.id
        ? '<a href="#" onclick="event.preventDefault();openAccountDetail(\'' + d.id + '\')" style="color:#e2e8f0;text-decoration:none;border-bottom:1px dashed #475569">' + esc(d.name) + '</a>'
        : esc(d.name);
      html += '<tr><td>' + nameLink + '</td><td style="color:#64748b">' + d.type + '</td>'
        + '<td class="amt-neg" style="text-align:right">' + fmt(d.starting_balance) + '</td>'
        + '<td style="text-align:right;color:#f59e0b">' + (d.rate ? d.rate.toFixed(2) + '%' : '\u2014') + '</td>'
        + '<td style="text-align:right">' + fmt(d.min_payment) + '</td>'
        + '<td style="color:#86efac">' + moStr + '<span style="color:#64748b;font-size:.72rem;margin-left:.3rem">' + dateStr + '</span></td></tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

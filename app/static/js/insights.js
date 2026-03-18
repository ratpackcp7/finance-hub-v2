// Finance Hub — insights.js
// Financial Insights: NW breakdown, savings rate, cash flow, debt, investments, dividends

var _insNwPie = null, _insDebtChart = null, _insInvChart = null, _insDivChart = null;

var TYPE_COLORS = {
  checking: '#3b82f6', savings: '#22c55e', credit: '#ef4444',
  investment: '#a855f7', retirement: '#8b5cf6', brokerage: '#6366f1',
  loan: '#f97316', mortgage: '#fb923c', '529': '#14b8a6',
  hsa: '#06b6d4', utma: '#0ea5e9', other: '#64748b'
};

var TYPE_LABELS = {
  checking: 'Checking', savings: 'Savings', credit: 'Credit Cards',
  investment: 'Investment', retirement: 'Retirement', brokerage: 'Brokerage',
  loan: 'Loans', mortgage: 'Mortgage', '529': '529 Plans',
  hsa: 'HSA', utma: 'UTMA', other: 'Other'
};

async function loadInsights() {
  try {
    var results = await Promise.all([
      api('/api/net-worth/breakdown'),
      api('/api/spending/over-time?months=6'),
      api('/api/debt/summary'),
      api('/api/investments/history?months=12'),
      api('/api/dividends/summary')
    ]);
    var nwBreakdown = results[0], monthly = results[1], debt = results[2];
    var investments = results[3], dividends = results[4];

    renderSavingsRate(monthly);
    renderCashFlow(monthly);
    renderNwBreakdown(nwBreakdown);
    renderDebtTracker(debt);
    renderInvestmentChart(investments);
    renderDividends(dividends);

    // Holdings, activity, alerts
    try {
      var holdRes = await Promise.all([
        api('/api/holdings'),
        api('/api/holdings/activity?months=6'),
        api('/api/holdings/alerts')
      ]);
      renderHoldingsTable(holdRes[0]);
      renderActivity(holdRes[1]);
      renderAlerts(holdRes[2]);
    } catch (e) { console.error('Holdings error:', e); }
  } catch (e) {
    console.error('Insights error:', e);
  }
}

// ═══════════════════════════════════════
// 1. Savings Rate
// ═══════════════════════════════════════
function renderSavingsRate(monthly) {
  var el = $('ins-savings-rate');
  if (!monthly.length) { el.innerHTML = '<p class="empty">No data</p>'; return; }

  var html = '<div style="display:flex;flex-direction:column;gap:.6rem">';
  var rev = monthly.slice().reverse();
  rev.forEach(function(m) {
    var rate = m.income > 0 ? ((m.income - m.spending) / m.income * 100) : 0;
    var saved = m.income - m.spending;
    var color = rate >= 20 ? '#22c55e' : rate >= 10 ? '#f59e0b' : rate >= 0 ? '#fb923c' : '#ef4444';
    var barW = Math.min(100, Math.max(2, Math.abs(rate)));
    html += '<div style="display:flex;align-items:center;gap:.5rem;font-size:.8rem">'
      + '<span style="width:52px;color:#64748b;flex-shrink:0">' + m.month + '</span>'
      + '<div style="flex:1;background:#1e2530;border-radius:3px;height:18px;overflow:hidden">'
      + '<div style="width:' + barW + '%;background:' + color + ';height:100%;border-radius:3px"></div></div>'
      + '<span style="width:45px;text-align:right;font-weight:600;color:' + color + '">' + rate.toFixed(0) + '%</span>'
      + '<span style="width:75px;text-align:right;color:#94a3b8;font-size:.72rem">' + fmt(saved) + '</span>'
      + '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════
// 2. Monthly Cash Flow
// ═══════════════════════════════════════
function renderCashFlow(monthly) {
  var el = $('ins-cashflow');
  if (!monthly.length) { el.innerHTML = '<p class="empty">No data</p>'; return; }

  var rev = monthly.slice().reverse();
  var html = '<div style="overflow-x:auto"><table style="font-size:.78rem"><thead><tr>'
    + '<th>Month</th><th style="text-align:right">Income</th><th style="text-align:right">Spending</th>'
    + '<th style="text-align:right">Net</th></tr></thead><tbody>';
  rev.forEach(function(m) {
    var net = m.income - m.spending;
    var nc = net >= 0 ? '#86efac' : '#fca5a5';
    html += '<tr><td style="color:#64748b">' + m.month + '</td>'
      + '<td style="text-align:right;color:#86efac">' + fmt(m.income) + '</td>'
      + '<td style="text-align:right;color:#fca5a5">' + fmt(m.spending) + '</td>'
      + '<td style="text-align:right;color:' + nc + ';font-weight:600">' + fmt(net) + '</td></tr>';
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════
// 3. NW Breakdown Pie
// ═══════════════════════════════════════
function renderNwBreakdown(data) {
  var groups = data.groups.filter(function(g) { return Math.abs(g.total) > 1; });
  if (!groups.length) return;

  // Pie chart — show asset types as positive, liabilities negative
  var labels = groups.map(function(g) { return TYPE_LABELS[g.type] || g.type; });
  var values = groups.map(function(g) { return Math.abs(g.total); });
  var colors = groups.map(function(g) { return TYPE_COLORS[g.type] || '#64748b'; });

  var ctx = $('chart-nw-pie').getContext('2d');
  if (_insNwPie) _insNwPie.destroy();
  _insNwPie = new Chart(ctx, {
    type: 'doughnut',
    data: { labels: labels, datasets: [{ data: values, backgroundColor: colors.map(function(c) { return c + 'cc'; }), borderColor: colors, borderWidth: 1 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: function(ctx) { return ctx.label + ': ' + fmt(ctx.raw); } } }
      }
    }
  });

  // Detail table
  var tableEl = $('ins-nw-table');
  var total = groups.reduce(function(s, g) { return s + g.total; }, 0);
  var html = '<div style="font-size:.78rem">';
  groups.forEach(function(g) {
    var label = TYPE_LABELS[g.type] || g.type;
    var color = TYPE_COLORS[g.type] || '#64748b';
    var isDebt = g.total < 0;
    html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:.35rem 0;border-bottom:1px solid #1e2530">'
      + '<div><span class="cat-dot" style="background:' + color + '"></span><span style="color:#e2e8f0">' + label + '</span>'
      + ' <span style="color:#475569;font-size:.7rem">(' + g.accounts.length + ')</span></div>'
      + '<span style="color:' + (isDebt ? '#fca5a5' : '#86efac') + ';font-weight:600;font-variant-numeric:tabular-nums">' + fmt(g.total) + '</span></div>';
    // Show individual accounts
    g.accounts.forEach(function(a) {
      var shortName = a.name.length > 35 ? a.name.slice(0, 32) + '...' : a.name;
      html += '<div style="display:flex;justify-content:space-between;padding:.15rem 0 .15rem 1.2rem;font-size:.7rem;color:#64748b">'
        + '<span>' + shortName + '</span>'
        + '<span style="font-variant-numeric:tabular-nums">' + fmt(a.balance) + '</span></div>';
    });
  });
  html += '<div style="display:flex;justify-content:space-between;padding:.5rem 0 0;border-top:2px solid #1e2530;font-weight:700;color:#f8fafc">'
    + '<span>Net Worth</span><span style="font-variant-numeric:tabular-nums">' + fmt(total) + '</span></div>';
  html += '</div>';
  tableEl.innerHTML = html;
}

// ═══════════════════════════════════════
// 4. Debt Payoff Tracker
// ═══════════════════════════════════════
function renderDebtTracker(data) {
  if (!data.accounts.length) { $('ins-debt-table').innerHTML = '<p class="empty">No debt accounts</p>'; return; }

  var debtColors = ['#f97316', '#fb923c', '#fbbf24', '#ef4444'];

  // Chart: balance over time per account
  var datasets = data.accounts.map(function(a, i) {
    var hist = a.history || [];
    return {
      label: a.name.length > 25 ? a.name.slice(0, 22) + '...' : a.name,
      data: hist.map(function(h) { return Math.abs(h.balance); }),
      borderColor: debtColors[i % debtColors.length],
      backgroundColor: debtColors[i % debtColors.length] + '20',
      fill: true, tension: 0.3, pointRadius: 2
    };
  });
  var allDates = [];
  data.accounts.forEach(function(a) {
    (a.history || []).forEach(function(h) {
      if (allDates.indexOf(h.date) === -1) allDates.push(h.date);
    });
  });
  allDates.sort();

  var ctx = $('chart-debt').getContext('2d');
  if (_insDebtChart) _insDebtChart.destroy();
  _insDebtChart = new Chart(ctx, {
    type: 'line',
    data: { labels: allDates, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 10 } } },
        tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 10 } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });

  // Summary table
  var html = '<div style="overflow-x:auto"><table style="font-size:.78rem"><thead><tr>'
    + '<th>Account</th><th style="text-align:right">Balance</th><th style="text-align:right">Type</th></tr></thead><tbody>';
  data.accounts.forEach(function(a) {
    var shortName = a.name.length > 40 ? a.name.slice(0, 37) + '...' : a.name;
    html += '<tr><td>' + shortName + '</td>'
      + '<td style="text-align:right;color:#fca5a5;font-weight:600">' + fmt(Math.abs(a.balance)) + '</td>'
      + '<td style="text-align:right;color:#64748b">' + a.type + '</td></tr>';
  });
  html += '<tr style="border-top:2px solid #1e2530"><td style="font-weight:700">Total Debt</td>'
    + '<td style="text-align:right;font-weight:700;color:#fca5a5">' + fmt(data.total_debt) + '</td><td></td></tr>';
  html += '</tbody></table></div>';
  $('ins-debt-table').innerHTML = html;
}

// ═══════════════════════════════════════
// 5. Investment Balance Chart
// ═══════════════════════════════════════
function renderInvestmentChart(data) {
  if (!data.accounts.length) return;

  var invColors = ['#a855f7', '#8b5cf6', '#6366f1', '#3b82f6', '#06b6d4'];
  var datasets = [];
  var allDates = [];

  data.accounts.forEach(function(a, i) {
    if (a.history.length < 2) return;
    // Skip near-zero accounts
    var maxBal = Math.max.apply(null, a.history.map(function(h) { return Math.abs(h.balance); }));
    if (maxBal < 10) return;
    a.history.forEach(function(h) {
      if (allDates.indexOf(h.date) === -1) allDates.push(h.date);
    });
    var shortName = a.name.length > 30 ? a.name.slice(0, 27) + '...' : a.name;
    datasets.push({
      label: shortName,
      data: a.history.map(function(h) { return h.balance; }),
      borderColor: invColors[i % invColors.length],
      backgroundColor: invColors[i % invColors.length] + '15',
      fill: false, tension: 0.3, pointRadius: 2, borderWidth: 2
    });
  });
  allDates.sort();

  var ctx = $('chart-investments').getContext('2d');
  if (_insInvChart) _insInvChart.destroy();
  _insInvChart = new Chart(ctx, {
    type: 'line',
    data: { labels: allDates, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 10 } } },
        tooltip: { mode: 'index', intersect: false, callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 12 } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });
}

// ═══════════════════════════════════════
// 6. Dividend Income
// ═══════════════════════════════════════
function renderDividends(data) {
  var monthly = data.monthly_totals || [];
  if (!monthly.length) { $('ins-div-table').innerHTML = '<p class="empty">No dividend data</p>'; return; }

  // Bar chart
  var ctx = $('chart-dividends').getContext('2d');
  if (_insDivChart) _insDivChart.destroy();
  _insDivChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: monthly.map(function(m) { return m.month; }),
      datasets: [{
        label: 'Dividend Income',
        data: monthly.map(function(m) { return m.total; }),
        backgroundColor: '#a855f788', borderColor: '#a855f7', borderWidth: 1
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: function(ctx) { return fmt(ctx.raw); } } }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 } } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });

  // Detail table
  var entries = data.entries || [];
  var html = '<div style="overflow-x:auto"><table style="font-size:.78rem"><thead><tr>'
    + '<th>Month</th><th>Source</th><th>Account</th><th style="text-align:right">Amount</th></tr></thead><tbody>';
  entries.forEach(function(e) {
    var shortAcct = e.account.length > 25 ? e.account.slice(0, 22) + '...' : e.account;
    html += '<tr><td style="color:#64748b">' + e.month + '</td><td>' + e.payee + '</td>'
      + '<td style="color:#64748b;font-size:.72rem">' + shortAcct + '</td>'
      + '<td style="text-align:right;color:#a855f7;font-weight:600">' + fmt(e.amount) + '</td></tr>';
  });
  var totalDiv = monthly.reduce(function(s, m) { return s + m.total; }, 0);
  html += '<tr style="border-top:2px solid #1e2530"><td colspan="3" style="font-weight:700">Total Dividend Income</td>'
    + '<td style="text-align:right;font-weight:700;color:#a855f7">' + fmt(totalDiv) + '</td></tr>';
  html += '</tbody></table></div>';
  $('ins-div-table').innerHTML = html;
}


// ═══════════════════════════════════════
// 7. Portfolio Holdings Table
// ═══════════════════════════════════════
function renderHoldingsTable(data) {
  var el = $('ins-holdings-table');

  // Populate account dropdown for add form
  populateHoldingAccounts();

  if (!data.holdings.length) {
    el.innerHTML = '<p class="empty">No holdings tracked yet. Add one below.</p>';
    return;
  }

  var inputStyle = 'width:75px;font-size:.75rem;text-align:right;padding:.2rem .3rem;background:#0d1117;color:#e2e8f0;border:1px solid #1e2530;border-radius:3px';

  var html = '<div style="overflow-x:auto"><table style="font-size:.78rem"><thead><tr>'
    + '<th>Ticker</th><th>Name</th><th style="text-align:right">Shares</th>'
    + '<th style="text-align:right">Price</th><th style="text-align:right">Value</th>'
    + '<th style="text-align:right">Cost/Share</th><th style="text-align:right">Gain/Loss</th><th></th>'
    + '</tr></thead><tbody>';

  data.holdings.forEach(function(h) {
    var price = h.last_price ? fmt(h.last_price) : '\u2014';
    var val = h.market_value ? fmt(h.market_value) : '\u2014';
    var gainStr = '\u2014', gainColor = '#64748b';
    if (h.gain !== null) {
      gainColor = h.gain >= 0 ? '#86efac' : '#fca5a5';
      gainStr = fmt(h.gain) + (h.gain_pct !== null ? ' (' + h.gain_pct.toFixed(1) + '%)' : '');
    }
    html += '<tr>'
      + '<td style="font-weight:600;color:#818cf8">' + h.ticker + '</td>'
      + '<td style="font-size:.74rem">' + h.name + '</td>'
      + '<td style="text-align:right"><input type="number" step="0.01" value="' + h.shares.toFixed(4) + '" style="' + inputStyle + '" onchange="saveHolding(' + h.id + ',{shares:parseFloat(this.value)})"></td>'
      + '<td style="text-align:right;color:#64748b">' + price + '</td>'
      + '<td style="text-align:right;font-weight:600">' + val + '</td>'
      + '<td style="text-align:right"><input type="number" step="0.01" value="' + (h.cost_basis || 0) + '" style="' + inputStyle + '" onchange="saveHolding(' + h.id + ',{cost_basis:parseFloat(this.value)})"></td>'
      + '<td style="text-align:right;color:' + gainColor + '">' + gainStr + '</td>'
      + '<td><button class="btn btn-ghost btn-sm" style="color:#ef4444;font-size:.68rem;padding:.1rem .3rem" onclick="removeHolding(' + h.id + ')">\u2715</button></td></tr>';
  });

  html += '<tr style="border-top:2px solid #1e2530;font-weight:700"><td colspan="4">Total Portfolio</td>'
    + '<td style="text-align:right">' + fmt(data.total_value) + '</td>'
    + '<td style="text-align:right;color:#64748b">' + fmt(data.total_cost) + '</td>'
    + '<td style="text-align:right;color:' + ((data.total_gain||0) >= 0 ? '#86efac' : '#fca5a5') + '">'
    + (data.total_gain !== null ? fmt(data.total_gain) : '\u2014') + '</td><td></td></tr>';
  html += '</tbody></table></div>';
  el.innerHTML = html;
}

async function populateHoldingAccounts() {
  var sel = $('hld-account');
  if (!sel || sel.options.length > 1) return;
  try {
    var accts = await api('/api/accounts');
    var inv = accts.filter(function(a) { return ['investment','retirement','brokerage'].indexOf(a.account_type) >= 0; });
    inv.forEach(function(a) {
      var short = a.name.length > 35 ? a.name.slice(0, 32) + '...' : a.name;
      var opt = document.createElement('option');
      opt.value = a.id; opt.textContent = short;
      sel.appendChild(opt);
    });
  } catch(e) {}
}

async function saveHolding(id, data) {
  try {
    await api('/api/holdings/' + id, { method: 'PATCH', body: JSON.stringify(data) });
    toast('Updated', 'success');
    // Reload just the holdings part
    var hData = await api('/api/holdings');
    renderHoldingsTable(hData);
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function addHolding() {
  var acctId = $('hld-account').value;
  var ticker = ($('hld-ticker').value || '').trim().toUpperCase();
  var name = ($('hld-name').value || '').trim();
  var shares = parseFloat($('hld-shares').value) || 0;
  var basis = parseFloat($('hld-basis').value) || null;
  if (!acctId || !ticker || !name) { toast('Fill account, ticker, and name', 'error'); return; }
  try {
    await api('/api/holdings', { method: 'POST', body: JSON.stringify({
      account_id: acctId, ticker: ticker, name: name, shares: shares, cost_basis: basis
    })});
    toast('Added ' + ticker, 'success');
    $('hld-ticker').value = ''; $('hld-name').value = ''; $('hld-shares').value = ''; $('hld-basis').value = '';
    // Refresh prices for new ticker then reload
    await api('/api/holdings/refresh-prices', { method: 'POST', body: '{}' });
    var hData = await api('/api/holdings');
    renderHoldingsTable(hData);
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function removeHolding(id) {
  customConfirm('Delete this holding?', async function() {
    try {
      await api('/api/holdings/' + id, { method: 'DELETE' });
      toast('Deleted', 'success');
      var hData = await api('/api/holdings');
      renderHoldingsTable(hData);
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

async function refreshHoldingPrices() {
  try {
    toast('Refreshing prices...', 'info');
    var result = await api('/api/holdings/refresh-prices', { method: 'POST', body: '{}' });
    toast(result.updated + '/' + result.tickers + ' prices updated', 'success');
    loadInsights();
  } catch (e) { toast('Price refresh failed', 'error'); }
}

// ═══════════════════════════════════════
// 8. Alerts
// ═══════════════════════════════════════
function renderAlerts(data) {
  var card = $('ins-alerts-card');
  if (!data.alerts.length) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  var html = '';
  data.alerts.forEach(function(a) {
    var icon = a.severity === 'warning' ? '⚠️' : 'ℹ️';
    var bg = a.severity === 'warning' ? '#451a03' : '#0c1929';
    var border = a.severity === 'warning' ? '#f59e0b' : '#3b82f6';
    html += '<div style="padding:.6rem .8rem;margin-bottom:.5rem;border-radius:6px;background:' + bg + ';border-left:3px solid ' + border + ';font-size:.8rem">'
      + '<div style="font-weight:600">' + icon + ' ' + a.account + '</div>'
      + '<div style="color:#94a3b8;margin-top:.2rem">' + a.message + '</div></div>';
  });
  $('ins-alerts').innerHTML = html;
}

// ═══════════════════════════════════════
// 9. Investment Activity
// ═══════════════════════════════════════
function renderActivity(data) {
  var el = $('ins-activity');
  var totals = data.totals;
  var html = '<div style="display:flex;gap:1.5rem;margin-bottom:.75rem;font-size:.82rem">'
    + '<div><span style="color:#64748b">Dividends:</span> <span style="color:#86efac;font-weight:600">' + fmt(totals.dividend_income) + '</span></div>'
    + '<div><span style="color:#64748b">Reinvested:</span> <span style="color:#fca5a5;font-weight:600">' + fmt(Math.abs(totals.reinvested)) + '</span></div>'
    + '<div><span style="color:#64748b">Net retained:</span> <span style="color:#f8fafc;font-weight:600">' + fmt(totals.net) + '</span></div>'
    + '</div>';

  // Dividend summary by month/ticker
  if (data.dividend_summary.length) {
    html += '<div style="overflow-x:auto"><table style="font-size:.75rem"><thead><tr><th>Month</th><th>Ticker</th><th style="text-align:right">Dividends</th><th style="text-align:right">Txns</th></tr></thead><tbody>';
    data.dividend_summary.forEach(function(ds) {
      html += '<tr><td style="color:#64748b">' + ds.month + '</td><td style="color:#818cf8;font-weight:600">' + ds.ticker + '</td>'
        + '<td style="text-align:right;color:#86efac">' + fmt(ds.total) + '</td>'
        + '<td style="text-align:right;color:#64748b">' + ds.count + '</td></tr>';
    });
    html += '</tbody></table></div>';
  }

  // Unmatched transactions
  if (data.unmatched.length) {
    html += '<div style="margin-top:.75rem;padding-top:.5rem;border-top:1px solid #1e2530">'
      + '<div style="font-size:.78rem;color:#f59e0b;font-weight:600;margin-bottom:.3rem">⚠️ Unmatched Activity (' + data.unmatched.length + ')</div>';
    data.unmatched.slice(0, 10).forEach(function(u) {
      html += '<div style="font-size:.72rem;color:#94a3b8;padding:.15rem 0">'
        + u.date + ' — ' + u.payee + ' — ' + fmt(u.amount) + ' — ' + u.account_name + '</div>';
    });
    html += '</div>';
  }
  el.innerHTML = html;
}

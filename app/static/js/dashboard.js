// Finance Hub — dashboard.js
// Dashboard charts, stats, net worth, donut, bar chart

let donutChart = null, barChart = null, nwTrendChart = null;

// Main dashboard loader
async function loadDashboard() {
  var now = new Date();
  var y = now.getFullYear(), m = String(now.getMonth() + 1).padStart(2, '0');
  var start = y + '-' + m + '-01';
  var end = y + '-' + m + '-' + String(new Date(y, now.getMonth() + 1, 0).getDate()).padStart(2, '0');

  var results = await Promise.all([
    api('/api/spending/by-category?start_date=' + start + '&end_date=' + end),
    api('/api/spending/over-time?months=6'),
    api('/api/sync/log?limit=5'),
    api('/api/accounts'),
    api('/api/budgets/status?start_date=' + start + '&end_date=' + end),
    api('/api/accounts/net-worth')
  ]);
  var catSpend = results[0], monthly = results[1], syncLogs = results[2];
  var accts = results[3], budgetStatus = results[4], netWorth = results[5];

  // Stat cards
  var thisMonth = monthly.find(function(mo) { return mo.month === y + '-' + m; });
  $('ds-spending').textContent = fmt(thisMonth ? thisMonth.spending : 0);
  $('ds-income').textContent = fmt(thisMonth ? thisMonth.income : 0);
  $('ds-networth').textContent = fmt(netWorth.net_worth || 0);
  $('ds-acct-count').textContent = accts.length + ' accounts';
  var uncatSpend = catSpend.find(function(c) { return c.category === 'Uncategorized'; });
  // Review count loaded by loadReviewCounts() in review.js

  // Budget progress
  if (budgetStatus.budgets && budgetStatus.budgets.length > 0) {
    $('dash-budget-card').style.display = 'block';
    $('dash-budget-bars').innerHTML = budgetStatus.budgets.map(function(b) {
      var pct = Math.min(b.pct, 100);
      var over = b.pct > 100;
      var fc = over ? '#ef4444' : b.pct > 80 ? '#f59e0b' : (b.color || '#3b82f6');
      return '<div class="budget-row"><div class="bar-label"><span class="cat-dot" style="background:' + (b.color || '#475569') + '"></span>' + b.category + '</div><div class="budget-track"><div class="budget-fill" style="width:' + pct + '%;background:' + fc + '"></div></div><div class="bar-amount">' + fmt(b.spent) + ' / ' + fmt(b.budget) + '</div><div class="budget-pct" style="color:' + (over ? '#ef4444' : b.pct > 80 ? '#f59e0b' : '#64748b') + '">' + b.pct + '%</div></div>';
    }).join('');
    var t = budgetStatus.totals;
    $('dash-budget-total').innerHTML = '<span style="color:#94a3b8">Total: ' + fmt(t.spent) + ' / ' + fmt(t.budget) + '</span><span style="color:' + (t.pct > 100 ? '#ef4444' : t.pct > 80 ? '#f59e0b' : '#86efac') + ';font-weight:600">' + (t.remaining >= 0 ? fmt(t.remaining) + ' remaining' : fmt(-t.remaining) + ' over budget') + '</span>';
  } else {
    $('dash-budget-card').style.display = 'none';
  }

  // Render charts
  renderDonut(catSpend);
  renderBarChart(monthly);
  renderSyncLog(syncLogs);
  loadNwChart();
  loadDashBills();
}

// ── Donut chart: spending by category ──
var _donutStart = null, _donutEnd = null;

function setDonutRange(key, btn) {
  btn.parentElement.querySelectorAll('.quick-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  var now = new Date(), y = now.getFullYear(), mo = now.getMonth();
  var from, to, label;
  if (key === 'this-month') { from = new Date(y, mo, 1); to = new Date(y, mo + 1, 0); label = 'This Month'; }
  else if (key === 'last-month') { from = new Date(y, mo - 1, 1); to = new Date(y, mo, 0); label = 'Last Month'; }
  else if (key === '3-months') { from = new Date(y, mo - 2, 1); to = new Date(y, mo + 1, 0); label = '3 Months'; }
  else if (key === 'ytd') { from = new Date(y, 0, 1); to = new Date(y, mo + 1, 0); label = 'Year to Date'; }
  _donutStart = from.toISOString().slice(0, 10);
  _donutEnd = to.toISOString().slice(0, 10);
  var el = $('donut-title');
  if (el) el.textContent = 'Spending ' + label + ' \u2014 by Category';
  api('/api/spending/by-category?start_date=' + _donutStart + '&end_date=' + _donutEnd)
    .then(function(data) { renderDonut(data); })
    .catch(function(e) { console.error('Donut range error:', e); });
}

function renderDonut(catSpend) {
  var topCats = catSpend.filter(function(c) { return c.category !== 'Uncategorized'; }).slice(0, 10);
  window._donutCats = topCats;
  var donutCtx = $('chart-donut').getContext('2d');
  if (donutChart) donutChart.destroy();
  if (!topCats.length) { return; }
  $('chart-donut').style.cursor = 'pointer';
  donutChart = new Chart(donutCtx, {
    type: 'doughnut',
    data: {
      labels: topCats.map(function(c) { return c.category; }),
      datasets: [{
        data: topCats.map(function(c) { return c.total; }),
        backgroundColor: topCats.map(function(c) { return (c.color || '#475569') + 'cc'; }),
        borderColor: topCats.map(function(c) { return c.color || '#475569'; }),
        borderWidth: 1
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      onClick: function(evt, elements) {
        if (!elements.length) return;
        var idx = elements[0].index;
        var cat = window._donutCats[idx];
        if (!cat) return;
        // Find category ID from the loaded categories list
        var catObj = (typeof categories !== 'undefined' ? categories : []).find(function(c) { return c.name === cat.category; });
        var catId = catObj ? catObj.id : null;
        if (!catId) return;
        // Drill down to transactions with the donut's current date range
        var opts = { category: catId, type: 'spending' };
        if (_donutStart) { opts.from = _donutStart; opts.to = _donutEnd; }
        drillDown(opts);
      },
      plugins: {
        legend: {
          position: window.innerWidth < 768 ? 'bottom' : 'right',
          labels: { color: '#94a3b8', font: { size: window.innerWidth < 768 ? 10 : 11 }, boxWidth: 12, padding: window.innerWidth < 768 ? 6 : 10 }
        },
        tooltip: { callbacks: { label: function(ctx) { return ' ' + fmt(ctx.raw); } } }
      }
    }
  });
}

// ── Bar chart: monthly spending vs income ──
function renderBarChart(monthly) {
  var revM = monthly.slice().reverse();
  var barCtx = $('chart-bar').getContext('2d');
  if (barChart) barChart.destroy();
  barChart = new Chart(barCtx, {
    type: 'bar',
    data: {
      labels: revM.map(function(m) { return m.month; }),
      datasets: [
        { label: 'Spending', data: revM.map(function(m) { return m.spending; }), backgroundColor: '#ef444488', borderColor: '#ef4444', borderWidth: 1 },
        { label: 'Income', data: revM.map(function(m) { return m.income; }), backgroundColor: '#22c55e88', borderColor: '#22c55e', borderWidth: 1 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
        tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 11 } } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 11 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });
}

// ── Sync log table ──
function renderSyncLog(syncLogs) {
  if (!syncLogs.length) { $('sync-log-list').innerHTML = '<p class="empty">No syncs yet.</p>'; return; }
  $('sync-log-list').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr><th>Started</th><th>Status</th><th>Accounts</th><th>Added</th><th>Updated</th><th>Error</th></tr></thead><tbody>' +
    syncLogs.map(function(s) {
      var sc = s.status === 'ok' ? 'background:#14532d;color:#86efac' : s.status === 'error' ? 'background:#450a0a;color:#fca5a5' : 'background:#1e2530;color:#94a3b8';
      return '<tr><td>' + fmtDate(s.started_at) + '</td><td><span class="badge" style="' + sc + '">' + s.status + '</span></td><td>' + (s.accounts_seen || 0) + '</td><td>' + (s.txns_added || 0) + '</td><td>' + (s.txns_updated || 0) + '</td><td style="font-size:.75rem;color:#ef4444">' + esc(s.error_message || '') + '</td></tr>';
    }).join('') + '</tbody></table></div>';
}

// ── Net worth trend chart ──
var _nwMonths = 12;

function setNwRange(m, btn) {
  btn.parentElement.querySelectorAll('.quick-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  if (m === 0) { var now = new Date(); _nwMonths = now.getMonth() + 1; }
  else { _nwMonths = m; }
  loadNwChart();
}

async function loadNwChart() {
  try {
    var nwData = await api('/api/net-worth/history?months=' + _nwMonths);
    var hist = nwData.history || [];
    if (hist.length >= 2) {
      $('dash-nw-card').style.display = 'block';
      var nwCtx = $('chart-nw-trend').getContext('2d');
      if (nwTrendChart) nwTrendChart.destroy();
      nwTrendChart = new Chart(nwCtx, {
        type: 'line',
        data: {
          labels: hist.map(function(h) { return h.date; }),
          datasets: [{
            label: 'Net Worth',
            data: hist.map(function(h) { return h.net_worth; }),
            borderColor: '#3b82f6', backgroundColor: '#3b82f620',
            fill: true, tension: 0.3, pointRadius: 2, pointHoverRadius: 5
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: function(ctx) { return fmt(ctx.raw); } } }
          },
          scales: {
            x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 12 } },
            y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 11 }, callback: function(v) { return fmt(v); } } }
          }
        }
      });
    } else {
      $('dash-nw-card').style.display = 'none';
    }
  } catch (e) {
    console.error('NW history:', e);
    $('dash-nw-card').style.display = 'none';
  }
}

// ── Dashboard: upcoming bills widget ──
async function loadDashBills() {
  var card = $('dash-bills-card');
  if (!card) return;
  try {
    var data = await api('/api/bills/upcoming?days=7');
    if (!data.bills.length) { card.style.display = 'none'; return; }
    card.style.display = 'block';
    $('dash-bills').innerHTML = data.bills.slice(0, 5).map(function(b) {
      var urgent = b.days_until <= 2;
      var color = urgent ? '#fbbf24' : '#64748b';
      var label = b.days_until === 0 ? 'TODAY' : b.days_until === 1 ? 'Tomorrow' : b.days_until + 'd';
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.3rem 0;border-bottom:1px solid #0f1117;font-size:.78rem">'
        + '<span style="color:#e2e8f0">' + esc(b.name) + '</span>'
        + '<div style="display:flex;gap:.5rem;align-items:center">'
        + '<span class="amt-neg">' + (b.amount ? fmt(b.amount) : '') + '</span>'
        + '<span style="color:' + color + ';font-size:.7rem;font-weight:600;min-width:50px;text-align:right">' + label + '</span>'
        + '</div></div>';
    }).join('');
  } catch(e) { card.style.display = 'none'; }
}

// Boot
loadDashboard();

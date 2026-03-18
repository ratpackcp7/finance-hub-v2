// Finance Hub — history.js
// Investment History: growth chart, monthly returns, performance summary

var _histGrowthChart = null, _histReturnsChart = null, _histDepRetChart = null;
var _histMonths = 0;

function setHistRange(m, btn) {
  btn.parentElement.querySelectorAll('.quick-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  _histMonths = m;
  loadHistory();
}

async function loadHistory() {
  try {
    var url = '/api/investment/performance';
    if (_histMonths > 0) url += '?months=' + _histMonths;
    var data = await api(url);
    renderGrowthChart(data);
    renderReturnsChart(data);
    renderHistSummary(data);
    renderDepVsReturns(data);
    renderHistTable(data);
  } catch (e) {
    console.error('History error:', e);
  }
}

// ═══════════════════════════════════════
// 1. Portfolio Growth
// ═══════════════════════════════════════
function renderGrowthChart(data) {
  var records = data.records;
  var labels = records.map(function(r) { return r.month; });
  var balances = records.map(function(r) { return r.ending_balance; });
  var cumDeposits = [];
  var runningDep = 0;
  records.forEach(function(r) {
    runningDep += r.deposits;
    cumDeposits.push(runningDep);
  });

  var ctx = $('chart-hist-growth').getContext('2d');
  if (_histGrowthChart) _histGrowthChart.destroy();
  _histGrowthChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Portfolio Value',
          data: balances,
          borderColor: '#3b82f6',
          backgroundColor: '#3b82f620',
          fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2
        },
        {
          label: 'Total Invested',
          data: cumDeposits,
          borderColor: '#64748b',
          borderDash: [5, 5],
          fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); },
            afterBody: function(items) {
              var idx = items[0].dataIndex;
              var r = data.records[idx];
              return ['Returns: ' + fmt(r.cumulative_returns), 'Deposits: ' + fmt(r.deposits)];
            }
          }
        }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 9 }, maxTicksLimit: 20 } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });

  // Update title
  var title = $('hist-chart-title');
  if (title && records.length) {
    var start = fmt(records[0].beginning_balance);
    var end = fmt(records[records.length - 1].ending_balance);
    title.textContent = 'Portfolio Growth: ' + start + ' → ' + end;
  }
}

// ═══════════════════════════════════════
// 2. Monthly Returns Bar
// ═══════════════════════════════════════
function renderReturnsChart(data) {
  var records = data.records;
  var labels = records.map(function(r) { return r.month; });
  var returns = records.map(function(r) { return r.personal_returns; });
  var colors = returns.map(function(r) { return r >= 0 ? '#22c55e88' : '#ef444488'; });
  var borders = returns.map(function(r) { return r >= 0 ? '#22c55e' : '#ef4444'; });

  var ctx = $('chart-hist-returns').getContext('2d');
  if (_histReturnsChart) _histReturnsChart.destroy();
  _histReturnsChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Monthly Return',
        data: returns,
        backgroundColor: colors,
        borderColor: borders,
        borderWidth: 1
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: function(ctx) { return fmt(ctx.raw); } } }
      },
      scales: {
        x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 8 }, maxTicksLimit: 24 } },
        y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
      }
    }
  });
}

// ═══════════════════════════════════════
// 3. Performance Summary
// ═══════════════════════════════════════
function renderHistSummary(data) {
  var s = data.summary;
  var records = data.records;
  if (!records.length) { $('hist-summary').innerHTML = '<p class="empty">No data</p>'; return; }

  var first = records[0];
  var last = records[records.length - 1];

  // Best/worst months
  var sorted = records.slice().sort(function(a, b) { return b.personal_returns - a.personal_returns; });
  var best = sorted[0];
  var worst = sorted[sorted.length - 1];

  // Positive/negative months
  var pos = records.filter(function(r) { return r.personal_returns > 0; }).length;
  var neg = records.filter(function(r) { return r.personal_returns < 0; }).length;

  var html = '<div style="font-size:.8rem;display:flex;flex-direction:column;gap:.5rem">';

  function row(label, value, color) {
    return '<div style="display:flex;justify-content:space-between"><span style="color:#94a3b8">' + label + '</span><span style="color:' + (color || '#f8fafc') + ';font-weight:600;font-variant-numeric:tabular-nums">' + value + '</span></div>';
  }

  html += row('Date Range', s.start + ' → ' + s.end);
  html += row('Total Invested', fmt(s.total_deposits));
  html += row('Investment Returns', fmt(s.total_returns), s.total_returns >= 0 ? '#86efac' : '#fca5a5');
  html += row('Income/Dividends', fmt(s.total_income), '#a855f7');
  html += row('Rate of Return', s.rate_of_return + '%', '#86efac');
  html += '<div style="border-top:1px solid #1e2530;padding-top:.4rem"></div>';
  html += row('Best Month', best.month + ' (' + fmt(best.personal_returns) + ')', '#86efac');
  html += row('Worst Month', worst.month + ' (' + fmt(worst.personal_returns) + ')', '#fca5a5');
  html += row('Positive Months', pos + ' / ' + records.length + ' (' + (pos / records.length * 100).toFixed(0) + '%)');
  html += '</div>';
  $('hist-summary').innerHTML = html;
}

// ═══════════════════════════════════════
// 4. Deposits vs Returns Pie
// ═══════════════════════════════════════
function renderDepVsReturns(data) {
  var s = data.summary;
  var ctx = $('chart-hist-dep-vs-ret').getContext('2d');
  if (_histDepRetChart) _histDepRetChart.destroy();
  _histDepRetChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Deposits', 'Investment Returns'],
      datasets: [{
        data: [Math.max(0, s.total_deposits), Math.max(0, s.total_returns)],
        backgroundColor: ['#64748bcc', '#3b82f6cc'],
        borderColor: ['#64748b', '#3b82f6'],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
        tooltip: { callbacks: { label: function(ctx) { return ctx.label + ': ' + fmt(ctx.raw); } } }
      }
    }
  });
}

// ═══════════════════════════════════════
// 5. Monthly Detail Table
// ═══════════════════════════════════════
function renderHistTable(data) {
  var records = data.records.slice().reverse();
  var html = '<div style="overflow-x:auto"><table style="font-size:.72rem"><thead><tr>'
    + '<th>Month</th><th style="text-align:right">Balance</th><th style="text-align:right">Deposits</th>'
    + '<th style="text-align:right">Market</th><th style="text-align:right">Income</th>'
    + '<th style="text-align:right">Return</th><th style="text-align:right">Cumulative</th></tr></thead><tbody>';

  records.forEach(function(r) {
    var mc = r.market_gain_loss >= 0 ? '#86efac' : '#fca5a5';
    var rc = r.personal_returns >= 0 ? '#86efac' : '#fca5a5';
    html += '<tr>'
      + '<td style="color:#64748b">' + r.month + '</td>'
      + '<td style="text-align:right">' + fmt(r.ending_balance) + '</td>'
      + '<td style="text-align:right;color:#94a3b8">' + fmt(r.deposits) + '</td>'
      + '<td style="text-align:right;color:' + mc + '">' + fmt(r.market_gain_loss) + '</td>'
      + '<td style="text-align:right;color:#a855f7">' + fmt(r.income_returns) + '</td>'
      + '<td style="text-align:right;color:' + rc + ';font-weight:600">' + fmt(r.personal_returns) + '</td>'
      + '<td style="text-align:right;color:#3b82f6">' + fmt(r.cumulative_returns) + '</td>'
      + '</tr>';
  });
  html += '</tbody></table></div>';
  $('hist-table').innerHTML = html;
}

// Finance Hub — compare.js
// Period-over-period comparison

var _compareChart = null;

async function loadComparePage() {
  // Set defaults: this month vs last month
  var now = new Date(), y = now.getFullYear(), m = now.getMonth();
  var thisStart = new Date(y, m, 1);
  var thisEnd = new Date(y, m + 1, 0);
  var lastStart = new Date(y, m - 1, 1);
  var lastEnd = new Date(y, m, 0);

  $('cmp-a-start').value = thisStart.toISOString().slice(0, 10);
  $('cmp-a-end').value = thisEnd.toISOString().slice(0, 10);
  $('cmp-b-start').value = lastStart.toISOString().slice(0, 10);
  $('cmp-b-end').value = lastEnd.toISOString().slice(0, 10);

  runComparison();
}

function setComparePreset(preset) {
  var now = new Date(), y = now.getFullYear(), m = now.getMonth();
  if (preset === 'mom') {
    $('cmp-a-start').value = new Date(y, m, 1).toISOString().slice(0, 10);
    $('cmp-a-end').value = new Date(y, m + 1, 0).toISOString().slice(0, 10);
    $('cmp-b-start').value = new Date(y, m - 1, 1).toISOString().slice(0, 10);
    $('cmp-b-end').value = new Date(y, m, 0).toISOString().slice(0, 10);
  } else if (preset === 'yoy') {
    $('cmp-a-start').value = new Date(y, m, 1).toISOString().slice(0, 10);
    $('cmp-a-end').value = new Date(y, m + 1, 0).toISOString().slice(0, 10);
    $('cmp-b-start').value = new Date(y - 1, m, 1).toISOString().slice(0, 10);
    $('cmp-b-end').value = new Date(y - 1, m + 1, 0).toISOString().slice(0, 10);
  } else if (preset === 'qtd') {
    var qStart = new Date(y, Math.floor(m / 3) * 3, 1);
    $('cmp-a-start').value = qStart.toISOString().slice(0, 10);
    $('cmp-a-end').value = now.toISOString().slice(0, 10);
    var pqStart = new Date(y, Math.floor(m / 3) * 3 - 3, 1);
    var pqEnd = new Date(y, Math.floor(m / 3) * 3, 0);
    $('cmp-b-start').value = pqStart.toISOString().slice(0, 10);
    $('cmp-b-end').value = pqEnd.toISOString().slice(0, 10);
  }
  runComparison();
}

async function runComparison() {
  var params = 'start_a=' + $('cmp-a-start').value
    + '&end_a=' + $('cmp-a-end').value
    + '&start_b=' + $('cmp-b-start').value
    + '&end_b=' + $('cmp-b-end').value;

  $('cmp-results').innerHTML = '<p class="empty"><span class="spinner"></span> Comparing...</p>';

  try {
    var data = await api('/api/compare/periods?' + params);
    var a = data.period_a, b = data.period_b, d = data.deltas;

    // Summary cards
    var html = '<div class="grid-4" style="margin-bottom:1rem">';
    html += _cmpStat('Income', a.income, b.income, d.income);
    html += _cmpStat('Spending', a.spending, b.spending, d.spending);
    html += _cmpStat('Net', a.net, b.net, d.net);
    html += _cmpStat('Transactions', a.txn_count, b.txn_count, a.txn_count - b.txn_count);
    html += '</div>';

    // Category comparison chart
    var cats = data.category_comparison.slice(0, 12);
    html += '<div class="card" style="margin-bottom:1rem"><div class="card-title">Spending by Category</div>'
      + '<div style="height:300px"><canvas id="chart-compare"></canvas></div></div>';

    // Category delta table
    html += '<div class="card"><div class="card-title">Category Breakdown</div>'
      + '<table style="font-size:.8rem"><thead><tr><th>Category</th>'
      + '<th style="text-align:right">Period A</th><th style="text-align:right">Period B</th>'
      + '<th style="text-align:right">Change</th><th style="text-align:right">%</th></tr></thead><tbody>';
    data.category_comparison.forEach(function(c) {
      var color = c.delta > 0 ? '#fca5a5' : c.delta < 0 ? '#86efac' : '#64748b';
      var arrow = c.delta > 0 ? '\u25b2' : c.delta < 0 ? '\u25bc' : '';
      html += '<tr><td><span class="cat-dot" style="background:' + c.color + '"></span>' + esc(c.category) + '</td>'
        + '<td style="text-align:right">' + fmt(c.period_a) + '</td>'
        + '<td style="text-align:right">' + fmt(c.period_b) + '</td>'
        + '<td style="text-align:right;color:' + color + '">' + arrow + ' ' + fmt(Math.abs(c.delta)) + '</td>'
        + '<td style="text-align:right;color:' + color + '">' + (c.pct_change > 0 ? '+' : '') + c.pct_change + '%</td></tr>';
    });
    html += '</tbody></table></div>';

    $('cmp-results').innerHTML = html;

    // Render chart
    if (cats.length) {
      var ctx = $('chart-compare').getContext('2d');
      if (_compareChart) _compareChart.destroy();
      _compareChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: cats.map(function(c) { return c.category; }),
          datasets: [
            { label: 'Period A', data: cats.map(function(c) { return c.period_a; }),
              backgroundColor: '#3b82f688', borderColor: '#3b82f6', borderWidth: 1 },
            { label: 'Period B', data: cats.map(function(c) { return c.period_b; }),
              backgroundColor: '#f59e0b88', borderColor: '#f59e0b', borderWidth: 1 }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
            tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } } },
          scales: {
            x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, maxRotation: 45 } },
            y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 }, callback: function(v) { return fmt(v); } } }
          }
        }
      });
    }
  } catch (e) {
    $('cmp-results').innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

function _cmpStat(label, valA, valB, delta) {
  var isCount = typeof valA === 'number' && valA === Math.floor(valA) && Math.abs(valA) > 100 === false;
  var fmtFn = (label === 'Transactions') ? function(v) { return v.toLocaleString(); } : fmt;
  var color = delta > 0 ? (label === 'Net' || label === 'Income' ? '#86efac' : '#fca5a5')
    : delta < 0 ? (label === 'Net' || label === 'Income' ? '#fca5a5' : '#86efac') : '#64748b';
  var arrow = delta > 0 ? '\u25b2' : delta < 0 ? '\u25bc' : '';

  return '<div class="stat"><div class="stat-label">' + label + '</div>'
    + '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:.5rem">'
    + '<div style="font-size:1.1rem;font-weight:700;color:#f8fafc">' + fmtFn(valA) + '</div>'
    + '<div style="font-size:.82rem;color:#64748b">vs ' + fmtFn(valB) + '</div></div>'
    + '<div style="font-size:.75rem;color:' + color + ';margin-top:.2rem">' + arrow + ' '
    + (label === 'Transactions' ? Math.abs(delta).toLocaleString() : fmt(Math.abs(delta))) + '</div></div>';
}

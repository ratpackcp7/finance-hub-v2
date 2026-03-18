// Finance Hub — forecast.js
// Cashflow projection, category forecast, what-if scenarios

var _forecastChart = null;
var _whatIfChart = null;

async function loadForecastPage() {
  loadCashflowForecast();
  loadCategoryForecast();
}

async function loadCashflowForecast() {
  try {
    var data = await api('/api/forecast/cashflow?months_ahead=6');
    var a = data.averages;

    // Summary cards
    $('fc-avg-income').textContent = fmt(a.income);
    $('fc-avg-spending').textContent = fmt(a.spending);
    $('fc-avg-net').textContent = fmt(a.net);
    $('fc-avg-net').style.color = a.net >= 0 ? '#86efac' : '#fca5a5';
    $('fc-savings-rate').textContent = a.savings_rate + '%';
    $('fc-savings-rate').style.color = a.savings_rate >= 20 ? '#86efac' : a.savings_rate >= 0 ? '#fbbf24' : '#fca5a5';

    // NW projection
    if (data.projections.length) {
      var last = data.projections[data.projections.length - 1];
      $('fc-nw-projection').textContent = fmt(last.projected_nw);
      $('fc-nw-label').textContent = 'Net worth in ' + data.projections.length + ' months';
    }

    // Chart: actuals + projections
    var series = data.actuals.concat(data.projections);
    var ctx = $('chart-forecast').getContext('2d');
    if (_forecastChart) _forecastChart.destroy();

    var labels = series.map(function(s) { return s.month; });
    var incomeData = series.map(function(s) { return s.income; });
    var spendingData = series.map(function(s) { return s.spending; });
    var netData = series.map(function(s) { return s.net; });
    var splitIdx = data.actuals.length;

    _forecastChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Income', data: incomeData,
            borderColor: '#86efac', backgroundColor: '#86efac22',
            borderWidth: 2, fill: false, tension: 0.3,
            borderDash: series.map(function(s,i) { return i >= splitIdx ? [5,5] : []; })[0] ? [] : [],
            segment: { borderDash: function(ctx) { return ctx.p0DataIndex >= splitIdx - 1 ? [5,5] : []; } }
          },
          { label: 'Spending', data: spendingData,
            borderColor: '#fca5a5', backgroundColor: '#fca5a522',
            borderWidth: 2, fill: false, tension: 0.3,
            segment: { borderDash: function(ctx) { return ctx.p0DataIndex >= splitIdx - 1 ? [5,5] : []; } }
          },
          { label: 'Net', data: netData,
            borderColor: '#3b82f6', backgroundColor: '#3b82f622',
            borderWidth: 2, fill: true, tension: 0.3,
            segment: { borderDash: function(ctx) { return ctx.p0DataIndex >= splitIdx - 1 ? [5,5] : []; } }
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
          tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } },
          annotation: splitIdx > 0 ? {
            annotations: { divider: { type: 'line', xMin: splitIdx - 0.5, xMax: splitIdx - 0.5,
              borderColor: '#475569', borderWidth: 1, borderDash: [3,3] } }
          } : undefined
        },
        scales: {
          x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 } } },
          y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 },
            callback: function(v) { return fmt(v); } } }
        }
      }
    });
  } catch (e) {
    $('fc-chart-wrap').innerHTML = '<p class="empty" style="color:#fca5a5">' + e.message + '</p>';
  }
}

async function loadCategoryForecast() {
  var el = $('fc-cat-table');
  try {
    var data = await api('/api/forecast/category');
    $('fc-pace').textContent = 'Day ' + data.days_elapsed + ' of ' + data.days_total;

    el.innerHTML = '<table style="font-size:.8rem"><thead><tr><th>Category</th>'
      + '<th style="text-align:right">Avg/Mo</th><th style="text-align:right">This Month</th>'
      + '<th style="text-align:right">Projected</th><th style="text-align:right">Budget</th>'
      + '<th>Trend</th></tr></thead><tbody>'
      + data.categories.slice(0, 15).map(function(c) {
        var trendIcon = c.trend === 'over' ? '<span style="color:#fca5a5">\u26a0 Over</span>'
          : c.trend === 'on_track' ? '<span style="color:#86efac">\u2713 OK</span>'
          : '<span style="color:#64748b">\u2014</span>';
        var projColor = c.budget && c.projected_month > c.budget ? '#fca5a5' : '#e2e8f0';
        return '<tr><td><span class="cat-dot" style="background:' + c.color + '"></span>' + esc(c.category) + '</td>'
          + '<td style="text-align:right;color:#64748b">' + fmt(c.avg_monthly) + '</td>'
          + '<td style="text-align:right">' + fmt(c.current_month) + '</td>'
          + '<td style="text-align:right;color:' + projColor + '">' + fmt(c.projected_month) + '</td>'
          + '<td style="text-align:right;color:#64748b">' + (c.budget ? fmt(c.budget) : '\u2014') + '</td>'
          + '<td>' + trendIcon + '</td></tr>';
      }).join('')
      + '</tbody></table>';
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">' + e.message + '</p>';
  }
}

async function runWhatIf() {
  var change = parseFloat($('wi-change').value) || 0;
  var extra = parseFloat($('wi-extra').value) || 0;
  var months = parseInt($('wi-months').value) || 12;

  try {
    var data = await api('/api/forecast/what-if?monthly_change=' + change + '&extra_savings=' + extra + '&months=' + months);

    $('wi-baseline-net').textContent = fmt(data.baseline.monthly_net);
    $('wi-adjusted-net').textContent = fmt(data.adjusted.monthly_net);
    $('wi-adjusted-net').style.color = data.adjusted.monthly_net >= 0 ? '#86efac' : '#fca5a5';
    $('wi-improvement').textContent = (data.impact.monthly_improvement >= 0 ? '+' : '') + fmt(data.impact.monthly_improvement) + '/mo';
    $('wi-improvement').style.color = data.impact.monthly_improvement >= 0 ? '#86efac' : '#fca5a5';
    $('wi-total').textContent = (data.impact.total_improvement >= 0 ? '+' : '') + fmt(data.impact.total_improvement) + ' over ' + months + ' months';
    $('wi-nw-base').textContent = fmt(data.baseline.nw_in_months);
    $('wi-nw-adj').textContent = fmt(data.adjusted.nw_in_months);

    // Chart
    var ctx = $('chart-whatif').getContext('2d');
    if (_whatIfChart) _whatIfChart.destroy();
    var labels = data.series_baseline.map(function(_, i) { return 'Mo ' + (i + 1); });
    _whatIfChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Baseline', data: data.series_baseline,
            borderColor: '#64748b', borderWidth: 2, borderDash: [5,5], fill: false, tension: 0.3 },
          { label: 'Adjusted', data: data.series_adjusted,
            borderColor: '#3b82f6', borderWidth: 2, fill: true, backgroundColor: '#3b82f622', tension: 0.3 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8' } },
          tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + fmt(ctx.raw); } } } },
        scales: {
          x: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', font: { size: 10 } } },
          y: { grid: { color: '#1e2530' }, ticks: { color: '#64748b', callback: function(v) { return fmt(v); } } }
        }
      }
    });

    $('wi-results').style.display = 'block';
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

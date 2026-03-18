// Finance Hub — sankey.js
// Full Money Flow page + dashboard mini Sankey

var _flowStart = null, _flowEnd = null;
var _flowData = null;

function setFlowRange(key, btn) {
  btn.parentElement.querySelectorAll('.quick-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  var now = new Date(), y = now.getFullYear(), mo = now.getMonth();
  var from, to, label;
  if (key === 'this-month') { from = new Date(y, mo, 1); to = new Date(y, mo + 1, 0); label = 'This Month'; }
  else if (key === 'last-month') { from = new Date(y, mo - 1, 1); to = new Date(y, mo, 0); label = 'Last Month'; }
  else if (key === '3-months') { from = new Date(y, mo - 2, 1); to = new Date(y, mo + 1, 0); label = '3 Months'; }
  else if (key === 'ytd') { from = new Date(y, 0, 1); to = new Date(y, mo + 1, 0); label = 'Year to Date'; }
  _flowStart = from.toISOString().slice(0, 10);
  _flowEnd = to.toISOString().slice(0, 10);
  var el = $('flow-title');
  if (el) el.textContent = label + ' (' + _flowStart + ' to ' + _flowEnd + ')';
  loadFlowPage();
}

async function loadFlowPage() {
  var now = new Date(), y = now.getFullYear(), m = now.getMonth();
  var start = _flowStart || (y + '-' + String(m + 1).padStart(2, '0') + '-01');
  var end = _flowEnd || (y + '-' + String(m + 1).padStart(2, '0') + '-' + String(new Date(y, m + 1, 0).getDate()).padStart(2, '0'));
  try {
    var d = await api('/api/spending/flow?start_date=' + start + '&end_date=' + end);
    _flowData = d;
    _flowData._start = start;
    _flowData._end = end;
    if (!d.income.length && !d.spending.length) {
      $('flow-wrap').innerHTML = '<p class="empty">No data for this period</p>';
      return;
    }
    renderFlowSankey(d, 'flow-wrap');
    renderFlowLists(d, start, end);
  } catch (e) {
    console.error('Flow error:', e);
    $('flow-wrap').innerHTML = '<p class="empty" style="color:#fca5a5">Error loading flow data</p>';
  }
}

function renderFlowLists(d, start, end) {
  // Income breakdown
  var incHtml = '<div class="bar-list">';
  var maxInc = d.income[0] ? d.income[0].amount : 1;
  d.income.forEach(function(i) {
    incHtml += '<div class="bar-row" style="cursor:pointer" onclick="flowDrill(\'' + esc(i.name) + '\',\'credit\',\'' + start + '\',\'' + end + '\')">'
      + '<div class="bar-label"><span class="cat-dot" style="background:' + (i.color || '#4ade80') + '"></span>' + esc(i.name) + '</div>'
      + '<div class="bar-track"><div class="bar-fill" style="width:' + (i.amount / maxInc * 100).toFixed(1) + '%;background:' + (i.color || '#4ade80') + '"></div></div>'
      + '<div class="bar-amount">' + fmt(i.amount) + '</div></div>';
  });
  incHtml += '</div>';
  $('flow-income-list').innerHTML = incHtml;

  // Spending breakdown
  var spHtml = '<div class="bar-list">';
  var maxSp = d.spending[0] ? d.spending[0].amount : 1;
  d.spending.forEach(function(s) {
    spHtml += '<div class="bar-row" style="cursor:pointer" onclick="flowDrill(\'' + esc(s.name) + '\',\'debit\',\'' + start + '\',\'' + end + '\')">'
      + '<div class="bar-label"><span class="cat-dot" style="background:' + (s.color || '#475569') + '"></span>' + esc(s.name) + '</div>'
      + '<div class="bar-track"><div class="bar-fill" style="width:' + (s.amount / maxSp * 100).toFixed(1) + '%;background:' + (s.color || '#475569') + '"></div></div>'
      + '<div class="bar-amount">' + fmt(s.amount) + '</div></div>';
  });
  if (d.net > 0) {
    spHtml += '<div class="bar-row"><div class="bar-label" style="color:#86efac;font-weight:600">Savings</div><div class="bar-track"><div class="bar-fill" style="width:' + (d.net / maxSp * 100).toFixed(1) + '%;background:#22c55e"></div></div><div class="bar-amount" style="color:#86efac;font-weight:600">' + fmt(d.net) + '</div></div>';
  } else if (d.net < 0) {
    spHtml += '<div class="bar-row"><div class="bar-label" style="color:#fca5a5;font-weight:600">Over budget</div><div class="bar-track"><div class="bar-fill" style="width:100%;background:#ef4444"></div></div><div class="bar-amount" style="color:#fca5a5;font-weight:600">' + fmt(-d.net) + '</div></div>';
  }
  spHtml += '</div>';
  $('flow-spend-list').innerHTML = spHtml;
}

function flowDrill(catName, type, start, end) {
  var catObj = (typeof categories !== 'undefined' ? categories : []).find(function(c) { return c.name === catName; });
  if (catObj) {
    drillDown({ category: catObj.id, from: start, to: end, type: type });
  } else {
    drillDown({ from: start, to: end, type: type });
  }
}

function renderFlowSankey(d, wrapperId) {
  var wrap = document.getElementById(wrapperId);
  var wrapW = wrap.offsetWidth || 900;
  var labelR = 180, labelL = 100, padH = 30, nodeW = 16, gap = 5;
  var flowW = Math.max(200, wrapW - labelL - labelR - padH * 2);
  var W = labelL + padH + flowW + padH + labelR;

  var totalIn = d.total_income, totalOut = d.total_spending;
  if (!totalIn && !totalOut) { wrap.innerHTML = '<p class="empty">No data</p>'; return; }
  var maxVal = Math.max(totalIn, totalOut);

  // Scale height to number of items
  var itemCount = Math.max(d.income.length, d.spending.length + (d.net > 0 ? 1 : 0));
  var H = Math.max(300, Math.min(600, itemCount * 35 + 80));
  var padV = 40;
  var usableH = H - padV * 2;

  var incNodes = d.income.map(function(i) { return {name: i.name, color: i.color || '#4ade80', amount: i.amount, h: Math.max(6, (i.amount / maxVal) * usableH)}; });
  var spItems = d.spending.slice(0, 15);
  var rest = d.spending.slice(15);
  if (rest.length) { spItems.push({name: 'Other', color: '#475569', amount: rest.reduce(function(s, r) { return s + r.amount; }, 0)}); }
  var spNodes = spItems.map(function(s) { return {name: s.name, color: s.color || '#475569', amount: s.amount, h: Math.max(6, (s.amount / maxVal) * usableH)}; });

  var net = d.net;
  var netH = net > 0 ? Math.max(6, (net / maxVal) * usableH) : 0;

  // Y positions
  var yL = padV;
  incNodes.forEach(function(n) { n.y = yL; yL += n.h + gap; });
  var yR = padV;
  spNodes.forEach(function(n) { n.y = yR; yR += n.h + gap; });
  var netY = yR;

  var centerX = labelL + padH + flowW / 2 - nodeW / 2;
  var centerY = padV;
  var centerH = (totalIn / maxVal) * usableH;
  var rX = labelL + padH + flowW + padH;

  var svg = '<svg width="' + W + '" height="' + (H + 20) + '" viewBox="0 0 ' + W + ' ' + (H + 20) + '" xmlns="http://www.w3.org/2000/svg" style="font-family:-apple-system,sans-serif">';

  function flowPath(x1, y1, h1, x2, y2, h2, color, opacity) {
    var mx = (x1 + x2) / 2;
    return '<path d="M' + x1 + ',' + y1 + ' C' + mx + ',' + y1 + ' ' + mx + ',' + y2 + ' ' + x2 + ',' + y2 + ' L' + x2 + ',' + (y2 + h2) + ' C' + mx + ',' + (y2 + h2) + ' ' + mx + ',' + (y1 + h1) + ' ' + x1 + ',' + (y1 + h1) + ' Z" fill="' + color + '" opacity="' + (opacity || 0.35) + '" style="cursor:pointer"><title>' + color + '</title></path>';
  }

  // Income → center flows
  var cY = centerY;
  incNodes.forEach(function(n) {
    var flowH = (n.amount / totalIn) * centerH;
    svg += flowPath(labelL + nodeW, n.y, n.h, centerX, cY, flowH, n.color, 0.3);
    cY += flowH;
  });

  // Center → spending flows
  var cY2 = centerY;
  spNodes.forEach(function(n) {
    var flowH = (n.amount / totalIn) * centerH;
    svg += flowPath(centerX + nodeW, cY2, flowH, rX, n.y, n.h, n.color, 0.3);
    cY2 += flowH;
  });

  // Center → savings
  if (netH > 0 && net > 0) {
    var flowH2 = (net / totalIn) * centerH;
    svg += flowPath(centerX + nodeW, cY2, flowH2, rX, netY, netH, '#22c55e', 0.25);
  }

  // Income nodes (left) — clickable
  incNodes.forEach(function(n) {
    svg += '<rect x="' + labelL + '" y="' + n.y + '" width="' + nodeW + '" height="' + n.h + '" rx="3" fill="' + n.color + '" style="cursor:pointer" onclick="flowDrill(\'' + n.name.replace(/'/g, "\\'") + '\',\'credit\',\'' + (d._start || '') + '\',\'' + (d._end || '') + '\')"/>';
    svg += '<text x="' + (labelL - 6) + '" y="' + (n.y + n.h / 2 + 4) + '" text-anchor="end" fill="#94a3b8" font-size="11" style="cursor:pointer" onclick="flowDrill(\'' + n.name.replace(/'/g, "\\'") + '\',\'credit\',\'' + (d._start || '') + '\',\'' + (d._end || '') + '\')">' + n.name + '</text>';
  });

  // Center node
  svg += '<rect x="' + centerX + '" y="' + centerY + '" width="' + nodeW + '" height="' + centerH + '" rx="3" fill="#3b82f6"/>';
  svg += '<text x="' + (centerX + nodeW / 2) + '" y="' + (centerY - 8) + '" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="600">' + fmt(totalIn) + '</text>';

  // Spending nodes (right) — clickable
  spNodes.forEach(function(n) {
    svg += '<rect x="' + rX + '" y="' + n.y + '" width="' + nodeW + '" height="' + n.h + '" rx="3" fill="' + n.color + '" style="cursor:pointer" onclick="flowDrill(\'' + n.name.replace(/'/g, "\\'") + '\',\'debit\',\'' + (d._start || '') + '\',\'' + (d._end || '') + '\')"/>';
    svg += '<text x="' + (rX + nodeW + 6) + '" y="' + (n.y + n.h / 2 + 4) + '" fill="#94a3b8" font-size="11" style="cursor:pointer" onclick="flowDrill(\'' + n.name.replace(/'/g, "\\'") + '\',\'debit\',\'' + (d._start || '') + '\',\'' + (d._end || '') + '\')">' + n.name + ' ' + fmt(n.amount) + '</text>';
  });

  // Savings node
  if (netH > 0 && net > 0) {
    svg += '<rect x="' + rX + '" y="' + netY + '" width="' + nodeW + '" height="' + netH + '" rx="3" fill="#22c55e"/>';
    svg += '<text x="' + (rX + nodeW + 6) + '" y="' + (netY + netH / 2 + 4) + '" fill="#86efac" font-size="12" font-weight="600">Savings ' + fmt(net) + '</text>';
  } else if (net < 0) {
    svg += '<text x="' + (rX + nodeW + 6) + '" y="' + ((yR || padV) + 10) + '" fill="#fca5a5" font-size="12" font-weight="600">Over budget ' + fmt(-net) + '</text>';
  }

  // Labels
  svg += '<text x="' + labelL + '" y="' + (H + 14) + '" fill="#475569" font-size="10">INCOME</text>';
  svg += '<text x="' + rX + '" y="' + (H + 14) + '" fill="#475569" font-size="10">SPENDING</text>';
  svg += '</svg>';
  wrap.innerHTML = svg;
}

// ── Dashboard mini Sankey (keep for backward compat) ──
var _sankeyStart = null, _sankeyEnd = null;

function setSankeyRange(key, btn) {
  btn.parentElement.querySelectorAll('.quick-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  var now = new Date(), y = now.getFullYear(), mo = now.getMonth();
  var from, to, label;
  if (key === 'this-month') { from = new Date(y, mo, 1); to = new Date(y, mo + 1, 0); label = 'This Month'; }
  else if (key === 'last-month') { from = new Date(y, mo - 1, 1); to = new Date(y, mo, 0); label = 'Last Month'; }
  else if (key === '3-months') { from = new Date(y, mo - 2, 1); to = new Date(y, mo + 1, 0); label = '3 Months'; }
  else if (key === 'ytd') { from = new Date(y, 0, 1); to = new Date(y, mo + 1, 0); label = 'Year to Date'; }
  _sankeyStart = from.toISOString().slice(0, 10);
  _sankeyEnd = to.toISOString().slice(0, 10);
  var t = $('sankey-title'); if (t) t.textContent = 'Money Flow \u2014 ' + label;
  loadSankey();
}

async function loadSankey() {
  var now = new Date(), y = now.getFullYear(), m = now.getMonth();
  var start = _sankeyStart || (y + '-' + String(m + 1).padStart(2, '0') + '-01');
  var end = _sankeyEnd || (y + '-' + String(m + 1).padStart(2, '0') + '-' + String(new Date(y, m + 1, 0).getDate()).padStart(2, '0'));
  try {
    var d = await api('/api/spending/flow?start_date=' + start + '&end_date=' + end);
    if (!d.income.length && !d.spending.length) { $('dash-sankey-card').style.display = 'none'; return; }
    $('dash-sankey-card').style.display = 'block';
    d._start = start;
    d._end = end;
    renderFlowSankey(d, 'sankey-wrap');
  } catch (e) { console.error('Sankey error:', e); }
}

loadSankey();

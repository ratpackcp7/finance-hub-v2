// Finance Hub — rules.js
// Payee rules: CRUD, preview, advanced create

async function loadRules() {
  try {
    var rules = await api('/api/payee-rules/full');
  } catch(e) {
    // Fallback to basic endpoint if full not available
    var rules = await api('/api/payee-rules');
  }
  if (!rules.length) {
    $('rules-tbody').innerHTML = '<tr><td colspan="7" class="empty">No rules yet.</td></tr>';
    $('rules-count').textContent = '0 rules';
    return;
  }
  $('rules-count').textContent = rules.length + ' rules';
  $('rules-tbody').innerHTML = rules.map(function(r) {
    var extras = [];
    if (r.amount_min != null || r.amount_max != null) {
      var range = '';
      if (r.amount_min != null && r.amount_max != null) range = fmt(r.amount_min) + '–' + fmt(r.amount_max);
      else if (r.amount_min != null) range = '≥ ' + fmt(r.amount_min);
      else range = '≤ ' + fmt(r.amount_max);
      extras.push('<span class="badge" style="background:#1e3a5f;color:#7dd3fc;font-size:.62rem">' + range + '</span>');
    }
    if (r.set_transfer === true) extras.push('<span class="badge" style="background:#1e3a5f;color:#7dd3fc;font-size:.62rem">→ transfer</span>');
    if (r.tag) extras.push('<span class="badge" style="background:#4c1d95;color:#c4b5fd;font-size:.62rem">🏷 ' + esc(r.tag) + '</span>');
    var extrasHtml = extras.length ? '<div style="margin-top:.2rem">' + extras.join(' ') + '</div>' : '';

    return '<tr>'
      + '<td><code style="background:#1e2530;padding:.1rem .4rem;border-radius:4px;font-size:.8rem">' + esc(r.pattern) + '</code>' + extrasHtml + '</td>'
      + '<td style="color:#94a3b8">' + esc(r.payee_name || '\u2014') + '</td>'
      + '<td>' + catBadge(r.category_id, r.category) + '</td>'
      + '<td style="color:#64748b">' + r.priority + '</td>'
      + '<td><button class="btn btn-ghost btn-sm" onclick="previewPattern(\'' + esc(r.pattern) + '\')">Test</button></td>'
      + '<td><button class="btn btn-danger btn-sm" onclick="deleteRule(' + r.id + ')">Delete</button></td>'
      + '</tr>';
  }).join('');
}

function openRuleModal(p) {
  $('mr-pattern').value = p || '';
  $('mr-payee').value = '';
  $('mr-category').value = '';
  $('mr-priority').value = 0;
  $('mr-amount-min').value = '';
  $('mr-amount-max').value = '';
  $('mr-set-transfer').checked = false;
  $('mr-preview-results').innerHTML = '';
  $('mr-preview-counts').innerHTML = '';
  openModal('modal-rule');
  if (p) runModalPreview();
}

async function runModalPreview() {
  var pattern = $('mr-pattern').value.trim();
  if (!pattern) { $('mr-preview-results').innerHTML = ''; $('mr-preview-counts').innerHTML = ''; return; }

  var params = 'pattern=' + encodeURIComponent(pattern) + '&limit=10';
  var amtMin = $('mr-amount-min').value;
  var amtMax = $('mr-amount-max').value;
  if (amtMin) params += '&amount_min=' + amtMin;
  if (amtMax) params += '&amount_max=' + amtMax;

  try {
    var data = await api('/api/payee-rules/preview?' + params);
    $('mr-preview-counts').innerHTML =
      '<span style="color:#86efac;font-weight:600">' + data.total_matches + '</span> total matches, '
      + '<span style="color:#fbbf24;font-weight:600">' + data.uncategorized_matches + '</span> would be categorized';

    if (!data.preview.length) {
      $('mr-preview-results').innerHTML = '<div class="empty" style="padding:.75rem 0">No transactions match this pattern</div>';
      return;
    }
    $('mr-preview-results').innerHTML = '<div style="max-height:250px;overflow-y:auto;margin-top:.5rem">'
      + data.preview.map(function(t) {
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.4rem .5rem;border-bottom:1px solid #0f1117;font-size:.78rem">'
          + '<div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
          + '<span style="color:#e2e8f0">' + esc(t.payee || t.description || '\u2014') + '</span>'
          + '<span style="color:#475569;margin-left:.4rem;font-size:.7rem">' + esc(t.account_name) + '</span>'
          + '</div>'
          + '<div style="display:flex;align-items:center;gap:.5rem;flex-shrink:0">'
          + (t.category ? '<span class="badge" style="background:#1e2530;color:#94a3b8;font-size:.62rem">' + esc(t.category) + '</span>' : '<span style="color:#fbbf24;font-size:.65rem">uncategorized</span>')
          + '<span class="' + (t.amount < 0 ? 'amt-neg' : 'amt-pos') + '" style="font-size:.8rem;font-weight:600;min-width:70px;text-align:right">' + fmt(t.amount) + '</span>'
          + '</div></div>';
      }).join('')
      + '</div>';
  } catch (e) {
    $('mr-preview-results').innerHTML = '<div style="color:#fca5a5;font-size:.78rem">Error: ' + e.message + '</div>';
  }
}

async function saveRule() {
  var pattern = $('mr-pattern').value.trim();
  if (!pattern) return toast('Pattern required', 'error');

  var body = {
    match_pattern: pattern,
    payee_name: $('mr-payee').value.trim() || null,
    category_id: $('mr-category').value ? parseInt($('mr-category').value) : null,
    priority: parseInt($('mr-priority').value) || 0,
  };

  // Advanced fields
  var amtMin = parseFloat($('mr-amount-min').value);
  var amtMax = parseFloat($('mr-amount-max').value);
  if (!isNaN(amtMin)) body.amount_min = amtMin;
  if (!isNaN(amtMax)) body.amount_max = amtMax;
  if ($('mr-set-transfer').checked) body.set_transfer = true;

  // Use advanced endpoint if any advanced fields set
  var endpoint = (body.amount_min != null || body.amount_max != null || body.set_transfer)
    ? '/api/payee-rules/advanced'
    : '/api/payee-rules';

  try {
    var result = await api(endpoint, { method: 'POST', body: JSON.stringify(body) });
    var msg = 'Rule saved';
    if (result.retroactive > 0) msg += ' \u2014 ' + result.retroactive + ' transactions auto-categorized';
    toast(msg, 'success');
    closeModal('modal-rule');
    loadRules();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function deleteRule(id) {
  customConfirm('Delete this rule?', async function() {
    await api('/api/payee-rules/' + id, { method: 'DELETE' });
    loadRules();
  });
}

// ── Standalone preview on the Rules page ──

async function previewPattern(p) {
  if (p) $('rp-pattern').value = p;
  runPagePreview();
}

async function runPagePreview() {
  var pattern = $('rp-pattern').value.trim();
  if (!pattern) { $('rp-results').innerHTML = ''; $('rp-counts').innerHTML = ''; return; }

  $('rp-results').innerHTML = '<p class="empty"><span class="spinner"></span> Searching...</p>';

  var params = 'pattern=' + encodeURIComponent(pattern) + '&limit=25';
  var amtMin = $('rp-amount-min').value;
  var amtMax = $('rp-amount-max').value;
  if (amtMin) params += '&amount_min=' + amtMin;
  if (amtMax) params += '&amount_max=' + amtMax;

  try {
    var data = await api('/api/payee-rules/preview?' + params);
    $('rp-counts').innerHTML =
      '<span style="color:#86efac;font-weight:600">' + data.total_matches + '</span> matches \u00b7 '
      + '<span style="color:#fbbf24;font-weight:600">' + data.uncategorized_matches + '</span> uncategorized';

    if (!data.preview.length) {
      $('rp-results').innerHTML = '<div class="empty" style="padding:1rem 0">No transactions match this pattern</div>';
      return;
    }
    var html = '<table style="font-size:.78rem;margin-top:.5rem"><thead><tr><th>Date</th><th>Description</th><th>Account</th><th>Category</th><th style="text-align:right">Amount</th></tr></thead><tbody>';
    data.preview.forEach(function(t) {
      html += '<tr>'
        + '<td style="color:#64748b;white-space:nowrap">' + (t.posted || '\u2014') + '</td>'
        + '<td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(t.payee || t.description || '\u2014') + '</td>'
        + '<td style="color:#64748b;font-size:.72rem">' + esc(t.account_name || '') + '</td>'
        + '<td>' + (t.category ? '<span class="badge" style="background:#1e2530;color:#94a3b8;font-size:.62rem">' + esc(t.category) + '</span>' : '<span style="color:#fbbf24;font-size:.65rem">\u2014</span>') + '</td>'
        + '<td class="' + (t.amount < 0 ? 'amt-neg' : 'amt-pos') + '" style="text-align:right">' + fmt(t.amount) + '</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
    if (data.total_matches > 25) html += '<div style="font-size:.72rem;color:#475569;margin-top:.3rem">Showing 25 of ' + data.total_matches + ' matches</div>';
    $('rp-results').innerHTML = html;
  } catch (e) {
    $('rp-results').innerHTML = '<div style="color:#fca5a5;font-size:.78rem">Error: ' + e.message + '</div>';
  }
}

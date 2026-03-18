// Finance Hub — merchants.js
// Merchant list, rename, merge, duplicate detection

var _merchantList = [];

async function loadMerchantsPage() {
  loadMerchants();
  loadMerchantDupes();
}

async function loadMerchants(search) {
  var el = $('merchant-list');
  var params = 'limit=100&min_count=2';
  if (search) params += '&search=' + encodeURIComponent(search);

  try {
    var data = await api('/api/merchants?' + params);
    _merchantList = data.merchants;
    $('merchant-count').textContent = data.total + ' merchants';

    if (!data.merchants.length) {
      el.innerHTML = '<p class="empty">No merchants found.</p>';
      return;
    }

    el.innerHTML = '<table style="font-size:.8rem"><thead><tr><th>Merchant</th><th style="text-align:right">Txns</th><th style="text-align:right">Total</th><th>Last Seen</th><th></th></tr></thead><tbody>'
      + data.merchants.map(function(m) {
        return '<tr><td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(m.name) + '</td>'
          + '<td style="text-align:right;color:#64748b">' + m.count + '</td>'
          + '<td class="amt-neg" style="text-align:right">' + fmt(m.total_amount) + '</td>'
          + '<td style="color:#64748b;font-size:.72rem">' + (m.last_seen || '') + '</td>'
          + '<td><button class="btn btn-ghost btn-sm" onclick="openRenameModal(\'' + esc(m.name).replace(/'/g, "\\'") + '\')">Rename</button></td></tr>';
      }).join('')
      + '</tbody></table>';
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

async function loadMerchantDupes() {
  var el = $('merchant-dupes');
  try {
    var data = await api('/api/merchants/duplicates?min_count=2&limit=20');
    if (!data.suggestions.length) {
      el.innerHTML = '<p class="empty">No obvious duplicates found.</p>';
      return;
    }

    el.innerHTML = data.suggestions.map(function(g) {
      var variants = g.variants.map(function(v) {
        return '<span class="badge" style="background:#1e2530;color:#94a3b8;margin-right:.3rem;font-size:.7rem">'
          + esc(v.name) + ' (' + v.count + ')</span>';
      }).join('');

      return '<div style="padding:.6rem .8rem;border:1px solid #1e2530;border-radius:8px;margin-bottom:.5rem;background:#0f1117">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem">'
        + '<div style="font-size:.82rem;color:#e2e8f0">' + esc(g.suggested_name)
        + ' <span style="color:#64748b;font-size:.72rem">(' + g.total_txns + ' txns)</span></div>'
        + '<button class="btn btn-primary btn-sm" onclick="quickMerge(' + JSON.stringify(g.variants.map(function(v){return v.name;})) + ',\'' + esc(g.suggested_name).replace(/'/g, "\\'") + '\')">Merge</button>'
        + '</div>'
        + '<div>' + variants + '</div></div>';
    }).join('');
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

function openRenameModal(name) {
  $('mr-old-name').value = name;
  $('mr-new-name').value = name;
  $('mr-result').innerHTML = '';
  openModal('modal-merchant-rename');
  setTimeout(function() { $('mr-new-name').select(); }, 50);
}

async function saveMerchantRename() {
  var oldName = $('mr-old-name').value.trim();
  var newName = $('mr-new-name').value.trim();
  if (!oldName || !newName) return toast('Both names required', 'error');
  try {
    var r = await api('/api/merchants/rename', {
      method: 'POST', body: JSON.stringify({ old_name: oldName, new_name: newName })
    });
    $('mr-result').innerHTML = '<span style="color:#86efac">\u2713 ' + r.updated + ' transactions renamed</span>';
    toast(r.updated + ' transactions renamed', 'success');
    setTimeout(function() { closeModal('modal-merchant-rename'); loadMerchants(); }, 800);
  } catch (e) { $('mr-result').innerHTML = '<span style="color:#fca5a5">Error: ' + e.message + '</span>'; }
}

async function quickMerge(names, target) {
  var sources = names.filter(function(n) { return n !== target; });
  if (!sources.length) return;
  customConfirm('Merge ' + sources.length + ' variants into "' + target + '"?\n\nThis will also create payee rules so future imports are auto-renamed.', async function() {
    try {
      var r = await api('/api/merchants/merge', {
        method: 'POST', body: JSON.stringify({ source_names: sources, target_name: target, create_rule: true })
      });
      toast(r.updated + ' transactions merged, ' + r.rules_created + ' rules created', 'success');
      loadMerchants();
      loadMerchantDupes();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  }, 'Merge', 'btn btn-primary');
}

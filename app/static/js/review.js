// Finance Hub — review.js
// Review queue: triage unreviewed/uncategorized transactions

let _reviewItems = [];
let _reviewFilter = '';

async function loadReviewPage() {
  loadReviewQueue();
}

async function loadReviewQueue() {
  var el = $('review-list');
  var params = 'limit=50';
  if (_reviewFilter) params += '&filter_type=' + _reviewFilter;

  try {
    var data = await api('/api/review/queue?' + params);
    var counts = data.counts;
    _reviewItems = data.items;

    // Update counts
    $('rv-uncat').textContent = counts.uncategorized;
    $('rv-ai').textContent = counts.ai_assigned;
    $('rv-recent').textContent = counts.recent;
    $('rv-large').textContent = counts.large;
    $('rv-total').textContent = counts.total;

    // Highlight active filter
    document.querySelectorAll('.rv-filter-btn').forEach(function(b) {
      b.classList.toggle('active', b.dataset.filter === (_reviewFilter || ''));
    });

    if (!data.items.length) {
      el.innerHTML = '<div class="empty" style="padding:2rem 0">\u2705 All caught up! No transactions need review.</div>';
      return;
    }

    el.innerHTML = data.items.map(function(t, idx) {
      var reasonBadges = t.reasons.map(function(r) {
        var colors = {
          uncategorized: 'background:#713f12;color:#fde68a',
          'ai-assigned': 'background:#1e3a5f;color:#7dd3fc',
          recent: 'background:#14532d;color:#86efac',
          large: 'background:#7f1d1d;color:#fca5a5'
        };
        return '<span class="badge" style="' + (colors[r] || 'background:#1e2530;color:#94a3b8') + ';font-size:.62rem">' + r + '</span>';
      }).join(' ');

      var catDisplay = t.category
        ? '<span class="badge" style="background:#1e2530;color:#94a3b8;font-size:.65rem">' + esc(t.category) + '</span>'
        : '<span style="color:#fbbf24;font-size:.72rem">\u2014 uncategorized</span>';

      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.7rem .8rem;border:1px solid #1e2530;border-radius:8px;margin-bottom:.5rem;background:#0f1117" data-txn-id="' + t.id + '">'
        + '<div style="flex:1;min-width:0">'
        + '<div style="display:flex;align-items:center;gap:.4rem;flex-wrap:wrap">'
        + '<span style="font-size:.85rem;color:#e2e8f0">' + esc(t.payee || t.description || '\u2014') + '</span>'
        + reasonBadges
        + '</div>'
        + '<div style="font-size:.72rem;color:#64748b;margin-top:.2rem">'
        + (t.posted || '') + ' \u00b7 ' + esc(t.account_name) + ' \u00b7 ' + catDisplay
        + '</div></div>'
        + '<div style="display:flex;align-items:center;gap:.5rem;flex-shrink:0">'
        + '<span class="' + (t.amount < 0 ? 'amt-neg' : 'amt-pos') + '" style="font-size:.9rem;font-weight:600;min-width:80px;text-align:right">' + fmt(t.amount) + '</span>'
        + '<button class="btn btn-ghost btn-sm" onclick="reviewEditTxn(\'' + t.id + '\')" title="Edit">\u270f</button>'
        + '<button class="btn btn-success btn-sm" onclick="reviewMarkOne(\'' + t.id + '\',this)" title="Mark reviewed">\u2713</button>'
        + '</div></div>';
    }).join('');

  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

function setReviewFilter(type, btn) {
  _reviewFilter = (_reviewFilter === type) ? '' : type;
  loadReviewQueue();
}

function reviewEditTxn(txnId) {
  // Load into the global txn list so the edit modal can find it
  var t = _reviewItems.find(function(x) { return x.id === txnId; });
  if (t) {
    _txnList = [t];
    openTxnModal(txnId);
  }
}

async function reviewMarkOne(txnId, btn) {
  try {
    await api('/api/review/mark-reviewed', {
      method: 'POST', body: JSON.stringify({ txn_ids: [txnId] })
    });
    // Remove from list with animation
    var row = btn.closest('[data-txn-id]');
    if (row) {
      row.style.transition = 'opacity .3s, transform .3s';
      row.style.opacity = '0';
      row.style.transform = 'translateX(40px)';
      setTimeout(function() { row.remove(); loadReviewCounts(); }, 300);
    }
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function reviewMarkAllVisible() {
  var ids = _reviewItems.filter(function(t) { return !t.reviewed_at; }).map(function(t) { return t.id; });
  if (!ids.length) return toast('Nothing to mark', 'info');
  customConfirm('Mark ' + ids.length + ' transactions as reviewed?', async function() {
    try {
      await api('/api/review/mark-reviewed', {
        method: 'POST', body: JSON.stringify({ txn_ids: ids })
      });
      toast(ids.length + ' marked as reviewed', 'success');
      loadReviewQueue();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  }, 'Mark All', 'btn btn-success');
}

async function reviewMarkAllCategorized() {
  customConfirm('Mark ALL categorized transactions as reviewed? This covers your full history.', async function() {
    try {
      var result = await api('/api/review/mark-all-reviewed', { method: 'POST' });
      toast(result.reviewed + ' transactions marked as reviewed', 'success');
      loadReviewQueue();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  }, 'Mark All Reviewed', 'btn btn-success');
}

// Dashboard badge
async function loadReviewCounts() {
  try {
    var data = await api('/api/review/counts');
    var badge = $('rv-sidebar-badge');
    if (badge) {
      badge.textContent = data.total;
      badge.style.display = data.total > 0 ? 'inline-flex' : 'none';
    }
    var dashStat = $('ds-review');
    if (dashStat) {
      dashStat.textContent = data.total;
      dashStat.style.color = data.total > 0 ? '#fbbf24' : '#86efac';
    }
  } catch (e) { /* silent */ }
}

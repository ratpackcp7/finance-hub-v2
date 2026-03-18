// Finance Hub — feedback.js
// Feedback FAB, modal, list

let fbType = 'bug';
function setFbType(t) {
  fbType = t;
  ['bug','feature','feedback'].forEach(x => {
    const btn = $('fb-type-' + x);
    if (btn) btn.classList.toggle('active', x === t);
  });
}
function openFeedbackModal() {
  $('fb-msg').value = '';
  setFbType('bug');
  openModal('modal-feedback');
  loadFeedbackList();
}
async function submitFeedback() {
  const msg = $('fb-msg').value.trim();
  if (!msg) return;
  const btn = $('fb-submit-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  try {
    await api('/api/feedback', {method:'POST', body: JSON.stringify({type: fbType, message: msg})});
    $('fb-msg').value = '';
    btn.textContent = '✓ Sent';
    btn.className = 'btn btn-success';
    setTimeout(() => { btn.textContent = 'Submit'; btn.className = 'btn btn-primary'; btn.disabled = false; }, 1500);
    loadFeedbackList();
  } catch(e) {
    alert('Error: ' + e.message);
    btn.textContent = 'Submit'; btn.className = 'btn btn-primary'; btn.disabled = false;
  }
}
async function loadFeedbackList() {
  try {
    const items = await api('/api/feedback');
    if (!items.length) { $('fb-list').innerHTML = '<p class="empty" style="padding:.5rem 0">No feedback yet.</p>'; return; }
    $('fb-list').innerHTML = items.slice(0, 15).map(fb => {
      const bc = fb.type === 'bug' ? 'fb-badge-bug' : fb.type === 'feature' ? 'fb-badge-feature' : 'fb-badge-feedback';
      const syncDot = fb.synced ? '<span title="Synced to Notion" style="color:#22c55e">●</span>' : '<span title="Not yet synced" style="color:#475569">○</span>';
      return '<div class="fb-item">' +
        '<div class="fb-item-msg"><span class="' + bc + '">' + fb.type + '</span> ' + esc(fb.message) + '</div>' +
        '<div class="fb-item-meta">' + syncDot + ' ' + fb.created_at.slice(0,10) +
        ' <button class="btn btn-ghost btn-sm" style="padding:.1rem .3rem;font-size:.68rem" onclick="deleteFb(' + fb.id + ')">×</button></div>' +
      '</div>';
    }).join('');
  } catch(e) {
    $('fb-list').innerHTML = '<p class="empty" style="color:#fca5a5">Error loading</p>';
  }
}
async function deleteFb(id) {
  try { await api('/api/feedback/' + id, {method:'DELETE'}); loadFeedbackList(); }
  catch(e) { alert('Error: ' + e.message); }
}

// Finance Hub — goals.js
// Savings goals: CRUD, progress bars, contributions

async function loadGoalsPage() {
  loadGoals();
}

async function loadGoals() {
  var el = $('goals-list');
  try {
    var goals = await api('/api/goals');
    if (!goals.length) {
      el.innerHTML = '<p class="empty">No goals yet. Create one to start tracking.</p>';
      $('goals-active-count').textContent = '0';
      $('goals-total-target').textContent = fmt(0);
      return;
    }

    var active = goals.filter(function(g) { return g.status === 'active'; });
    var completed = goals.filter(function(g) { return g.status === 'completed'; });
    $('goals-active-count').textContent = active.length;
    $('goals-total-target').textContent = fmt(active.reduce(function(s, g) { return s + g.target_amount; }, 0));

    var html = '';

    // Active goals
    if (active.length) {
      html += active.map(function(g) {
        var pctW = Math.min(g.pct, 100);
        var barColor = g.pct >= 100 ? '#22c55e' : g.pct >= 75 ? '#3b82f6' : g.pct >= 50 ? '#f59e0b' : g.color || '#3b82f6';
        var typeIcon = {emergency_fund: '\uD83D\uDEE1\uFE0F', savings: '\uD83D\uDCB0', debt_payoff: '\uD83D\uDCC9', purchase: '\uD83D\uDED2', custom: '\u2B50'}[g.goal_type] || '\u2B50';
        var monthsLabel = g.months_to_goal ? g.months_to_goal + ' mo remaining' : '';
        var accountLabel = g.account_name ? '<span style="font-size:.7rem;color:#64748b">\u2192 ' + esc(g.account_name) + '</span>' : '';

        return '<div style="border:1px solid #1e2530;border-radius:10px;padding:1rem;background:#0f1117;margin-bottom:.6rem">'
          + '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.6rem">'
          + '<div>'
          + '<div style="font-size:.9rem;font-weight:600;color:#e2e8f0">' + typeIcon + ' ' + esc(g.name) + '</div>'
          + '<div style="font-size:.72rem;color:#64748b">' + g.goal_type.replace('_', ' ') + (g.target_date ? ' \u00b7 due ' + g.target_date : '') + ' ' + accountLabel + '</div>'
          + '</div>'
          + '<div style="display:flex;gap:.4rem">'
          + (!g.account_id ? '<button class="btn btn-success btn-sm" onclick="openContributeModal(' + g.id + ',' + g.current_amount + ',' + g.target_amount + ',\'' + esc(g.name) + '\')">+ Add</button>' : '')
          + '<button class="btn btn-ghost btn-sm" onclick="openEditGoalModal(' + g.id + ')">Edit</button>'
          + '</div></div>'
          // Progress bar
          + '<div style="background:#1e2530;border-radius:6px;height:20px;overflow:hidden;margin-bottom:.4rem;position:relative">'
          + '<div style="width:' + pctW + '%;background:' + barColor + ';height:100%;border-radius:6px;transition:width .5s"></div>'
          + '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:600;color:#f8fafc">' + g.pct + '%</div>'
          + '</div>'
          // Amount details
          + '<div style="display:flex;justify-content:space-between;font-size:.78rem">'
          + '<span style="color:#86efac">' + fmt(g.current_amount) + '</span>'
          + '<span style="color:#64748b">' + fmt(g.remaining) + ' to go' + (monthsLabel ? ' \u00b7 ' + monthsLabel : '') + '</span>'
          + '<span style="color:#94a3b8;font-weight:600">' + fmt(g.target_amount) + '</span>'
          + '</div></div>';
      }).join('');
    }

    // Completed goals
    if (completed.length) {
      html += '<div style="margin-top:1rem"><div style="font-size:.72rem;font-weight:600;text-transform:uppercase;color:#475569;margin-bottom:.5rem">Completed</div>';
      html += completed.map(function(g) {
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.5rem .8rem;border:1px solid #14532d;border-radius:8px;margin-bottom:.4rem;background:#0a1a0a">'
          + '<div style="color:#86efac;font-size:.82rem">\u2705 ' + esc(g.name) + '</div>'
          + '<div style="display:flex;align-items:center;gap:.5rem">'
          + '<span style="color:#86efac;font-size:.82rem;font-weight:600">' + fmt(g.target_amount) + '</span>'
          + '<button class="btn btn-ghost btn-sm" style="font-size:.7rem" onclick="deleteGoal(' + g.id + ',\'' + esc(g.name) + '\')">Remove</button>'
          + '</div></div>';
      }).join('');
      html += '</div>';
    }

    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<p class="empty" style="color:#fca5a5">Error: ' + e.message + '</p>';
  }
}

// Dashboard widget
async function loadGoalsDashboard() {
  var card = $('dash-goals-card');
  if (!card) return;
  try {
    var data = await api('/api/goals/summary');
    if (!data.goals.length) { card.style.display = 'none'; return; }
    card.style.display = 'block';
    $('dash-goals').innerHTML = data.goals.map(function(g) {
      var pctW = Math.min(g.pct, 100);
      var barColor = g.pct >= 100 ? '#22c55e' : g.color || '#3b82f6';
      return '<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem">'
        + '<span style="width:120px;font-size:.78rem;color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(g.name) + '</span>'
        + '<div style="flex:1;background:#1e2530;border-radius:4px;height:10px;overflow:hidden">'
        + '<div style="width:' + pctW + '%;background:' + barColor + ';height:100%;border-radius:4px"></div></div>'
        + '<span style="width:45px;text-align:right;font-size:.72rem;font-weight:600;color:' + barColor + '">' + g.pct + '%</span>'
        + '</div>';
    }).join('');
  } catch (e) { card.style.display = 'none'; }
}

function openCreateGoalModal() {
  $('mg-name').value = '';
  $('mg-target').value = '';
  $('mg-type').value = 'savings';
  $('mg-date').value = '';
  $('mg-monthly').value = '';
  $('mg-color').value = '#3b82f6';
  $('mg-notes').value = '';
  $('mg-account').value = '';
  $('mg-id').value = '';
  $('mg-title').textContent = 'Create Goal';
  // Populate accounts
  if (typeof accounts !== 'undefined' && accounts.length) {
    $('mg-account').innerHTML = '<option value="">Manual tracking</option>'
      + accounts.filter(function(a) { return ['checking','savings','money_market'].indexOf(a.account_type) >= 0 || a.account_type === 'other'; })
      .map(function(a) { return '<option value="' + a.id + '">' + (a.org ? a.org + ' \u2013 ' : '') + a.name + '</option>'; }).join('');
  }
  openModal('modal-goal');
}

async function openEditGoalModal(id) {
  var goals = await api('/api/goals');
  var g = goals.find(function(x) { return x.id === id; });
  if (!g) return;
  openCreateGoalModal(); // Set up form
  $('mg-id').value = g.id;
  $('mg-title').textContent = 'Edit Goal';
  $('mg-name').value = g.name;
  $('mg-target').value = g.target_amount;
  $('mg-type').value = g.goal_type;
  $('mg-date').value = g.target_date || '';
  $('mg-monthly').value = g.monthly_contribution || '';
  $('mg-color').value = g.color || '#3b82f6';
  $('mg-notes').value = g.notes || '';
  $('mg-account').value = g.account_id || '';
}

async function saveGoal() {
  var id = $('mg-id').value;
  var body = {
    name: $('mg-name').value.trim(),
    target_amount: parseFloat($('mg-target').value),
    goal_type: $('mg-type').value,
    color: $('mg-color').value,
  };
  if (!body.name) return toast('Name required', 'error');
  if (!body.target_amount || body.target_amount <= 0) return toast('Target amount required', 'error');
  var d = $('mg-date').value; if (d) body.target_date = d;
  var m = parseFloat($('mg-monthly').value); if (m) body.monthly_contribution = m;
  var n = $('mg-notes').value.trim(); if (n) body.notes = n;
  var a = $('mg-account').value; if (a) body.account_id = a;

  try {
    if (id) {
      await api('/api/goals/' + id, { method: 'PATCH', body: JSON.stringify(body) });
      toast('Goal updated', 'success');
    } else {
      await api('/api/goals', { method: 'POST', body: JSON.stringify(body) });
      toast('Goal created', 'success');
    }
    closeModal('modal-goal');
    loadGoals();
    loadGoalsDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

function openContributeModal(id, current, target, name) {
  $('mc-goal-id').value = id;
  $('mc-goal-name').textContent = name;
  $('mc-current').textContent = fmt(current);
  $('mc-remaining').textContent = fmt(target - current);
  $('mc-amount').value = '';
  openModal('modal-contribute');
}

async function saveContribution() {
  var id = $('mc-goal-id').value;
  var amount = parseFloat($('mc-amount').value);
  if (!amount || amount <= 0) return toast('Enter an amount', 'error');
  try {
    var result = await api('/api/goals/' + id + '/contribute', {
      method: 'POST', body: JSON.stringify({ amount: amount })
    });
    toast('Added ' + fmt(amount) + (result.goal_status === 'completed' ? ' \u2014 Goal reached!' : ''), 'success');
    closeModal('modal-contribute');
    loadGoals();
    loadGoalsDashboard();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function deleteGoal(id, name) {
  customConfirm('Delete goal "' + name + '"?', async function() {
    await api('/api/goals/' + id, { method: 'DELETE' });
    toast('Goal deleted', 'success');
    loadGoals();
    loadGoalsDashboard();
  });
}

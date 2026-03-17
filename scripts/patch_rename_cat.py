#!/usr/bin/env python3
"""Patch index.html: add Rename button + modal to Settings > Categories."""
import re

path = "/home/chris/docker/finance-hub-v2/app/static/index.html"
html = open(path).read()

# ── 1. Replace the actions cell in loadCategoriesSettings ──────────────────
old_cell = "<td>${c.name!=='Uncategorized'?`<button class=\"btn btn-danger btn-sm\" onclick=\"deleteCat(${c.id},'${c.name}')\">×</button>`:''}</td>"
new_cell = "<td>${c.name!=='Uncategorized'?`<button class=\"btn btn-ghost btn-sm\" style=\"margin-right:.3rem\" onclick=\"openRenameCatModal(${c.id},'${c.name.replace(/'/g,\"\\\\'\")}')\">Rename</button><button class=\"btn btn-danger btn-sm\" onclick=\"deleteCat(${c.id},'${c.name}')\">×</button>`:''}</td>"

if old_cell in html:
    html = html.replace(old_cell, new_cell, 1)
    print("✓ patched table cell")
else:
    print("✗ table cell not found — check manually")

# ── 2. Insert rename modal before closing </body> ───────────────────────────
rename_modal = """
<!-- ── Rename Category Modal ── -->
<div class="modal-bg" id="modal-rename-cat">
  <div class="modal">
    <div class="modal-header">
      <h3>Rename Category</h3>
      <button class="modal-close" onclick="closeModal('modal-rename-cat')">✕</button>
    </div>
    <div class="field"><label>New Name</label><input type="text" id="mrc-name"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal('modal-rename-cat')">Cancel</button>
      <button class="btn btn-primary" onclick="renameCat()">Save</button>
    </div>
  </div>
</div>

"""

if "modal-rename-cat" not in html:
    html = html.replace("</body>", rename_modal + "</body>", 1)
    print("✓ inserted rename modal")
else:
    print("⚠ rename modal already present, skipping")

# ── 3. Insert rename JS before closing </script> ────────────────────────────
rename_js = """
/* ────────────────────────────────────────────────────────
   Rename Category
──────────────────────────────────────────────────────── */
let renamingCatId = null;

function openRenameCatModal(id, currentName) {
  renamingCatId = id;
  $('mrc-name').value = currentName;
  openModal('modal-rename-cat');
  setTimeout(() => { $('mrc-name').select(); }, 50);
}

async function renameCat() {
  const name = $('mrc-name').value.trim();
  if (!name) return;
  await api('/api/categories/' + renamingCatId, {method:'PATCH', body: JSON.stringify({name})});
  closeModal('modal-rename-cat');
  loadCategoriesSettings();
  loadCategories();
}

"""

if "renamingCatId" not in html:
    # Insert before the last </script>
    idx = html.rfind("</script>")
    html = html[:idx] + rename_js + html[idx:]
    print("✓ inserted rename JS")
else:
    print("⚠ rename JS already present, skipping")

open(path, "w").write(html)
print("Done.")

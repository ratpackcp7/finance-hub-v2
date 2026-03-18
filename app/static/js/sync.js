// Finance Hub — sync.js
// Sync trigger + status polling

async function triggerSync(){$('sync-btn').disabled=true;try{await api('/api/sync',{method:'POST',body:JSON.stringify({})});pollSyncStatus();}catch(e){toast('Sync error: '+e.message,'error');$('sync-btn').disabled=false;}}
function setSyncDot(cls){['sync-dot','sync-dot-sb'].forEach(id=>{var el=$(id);if(el)el.className='sync-dot '+cls;});}
async function pollSyncStatus(){clearTimeout(syncPollTimer);try{const s=await api('/api/sync/status');if(s.running){setSyncDot('running');$('sync-btn').disabled=true;syncPollTimer=setTimeout(pollSyncStatus,2000);}else{setSyncDot('ok');$('sync-btn').disabled=false;const active=document.querySelector('.page.active')?.id?.replace('page-','');if(active)showPage(active);}}catch(e){setSyncDot('error');$('sync-btn').disabled=false;}}
pollSyncStatus();

// Finance Hub — sync.js
// Auto-split from index.html

async function triggerSync(){$('sync-btn').disabled=true;try{await api('/api/sync',{method:'POST',body:JSON.stringify({})});pollSyncStatus();}catch(e){alert('Sync error: '+e.message);$('sync-btn').disabled=false;}}
async function pollSyncStatus(){clearTimeout(syncPollTimer);const dot=$('sync-dot');try{const s=await api('/api/sync/status');if(s.running){dot.className='sync-dot running';$('sync-btn').disabled=true;syncPollTimer=setTimeout(pollSyncStatus,2000);}else{dot.className='sync-dot ok';$('sync-btn').disabled=false;const active=document.querySelector('.page.active')?.id?.replace('page-','');if(active)showPage(active);}}catch(e){dot.className='sync-dot error';$('sync-btn').disabled=false;}}
pollSyncStatus();

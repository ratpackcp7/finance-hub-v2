// Finance Hub — sankey.js
// Auto-split from index.html

let _sankeyStart=null,_sankeyEnd=null;

function setSankeyRange(key,btn){
  // Update active button
  const row=btn.parentElement;
  row.querySelectorAll('.quick-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const now=new Date(),y=now.getFullYear(),mo=now.getMonth();
  let from,to,label;
  if(key==='this-month'){from=new Date(y,mo,1);to=new Date(y,mo+1,0);label='This Month';}
  else if(key==='last-month'){from=new Date(y,mo-1,1);to=new Date(y,mo,0);label='Last Month';}
  else if(key==='3-months'){from=new Date(y,mo-2,1);to=new Date(y,mo+1,0);label='3 Months';}
  else if(key==='ytd'){from=new Date(y,0,1);to=new Date(y,mo+1,0);label='Year to Date';}
  _sankeyStart=from.toISOString().slice(0,10);
  _sankeyEnd=to.toISOString().slice(0,10);
  const t=$('sankey-title');if(t)t.textContent='Money Flow — '+label;
  loadSankey();
}

async function loadSankey(){
  const now=new Date(),y=now.getFullYear(),m=now.getMonth();
  const start=_sankeyStart||`${y}-${String(m+1).padStart(2,'0')}-01`;
  const end=_sankeyEnd||`${y}-${String(m+1).padStart(2,'0')}-${String(new Date(y,m+1,0).getDate()).padStart(2,'0')}`;
  try{
    const d=await api(`/api/spending/flow?start_date=${start}&end_date=${end}`);
    if(!d.income.length&&!d.spending.length){$('dash-sankey-card').style.display='none';return;}
    $('dash-sankey-card').style.display='block';
    renderSankey(d);
  }catch(e){console.error('Sankey error:',e);}
}
function renderSankey(d){
  const wrapW=document.getElementById('sankey-wrap').offsetWidth||860;
  const labelR=160,labelL=90,pad=30,nodeW=16,gap=5;
  const flowW=Math.min(600,wrapW-labelL-labelR-pad*2);
  const W=labelL+pad+flowW+pad+labelR;
  const H=380;
  const totalIn=d.total_income,totalOut=d.total_spending;
  if(!totalIn&&!totalOut){$('sankey-wrap').innerHTML='<p class="empty">No data</p>';return;}
  const maxVal=Math.max(totalIn,totalOut);
  const usableH=H-pad*2;
  // Left nodes (income)
  const incNodes=d.income.map(i=>({...i,h:Math.max(4,(i.amount/maxVal)*usableH)}));
  // Right nodes (spending, top 12 + "Other")
  let spItems=d.spending.slice(0,12);
  const rest=d.spending.slice(12);
  if(rest.length){spItems.push({name:'Other',color:'#475569',amount:rest.reduce((s,r)=>s+r.amount,0)});}
  const spNodes=spItems.map(s=>({...s,h:Math.max(4,(s.amount/maxVal)*usableH)}));
  // Net savings node
  const net=d.net;
  const netH=net>0?Math.max(4,(net/maxVal)*usableH):0;
  // Y positions
  let yL=pad;
  incNodes.forEach(n=>{n.y=yL;yL+=n.h+gap;});
  let yR=pad;
  spNodes.forEach(n=>{n.y=yR;yR+=n.h+gap;});
  if(netH>0)var netY=yR;
  // Center column (total income)
  const centerX=labelL+pad+flowW/2-nodeW/2,centerY=pad,centerH=(totalIn/maxVal)*usableH;
  // SVG
  let svg=`<svg width="${W}" height="${H+20}" viewBox="0 0 ${W} ${H+20}" xmlns="http://www.w3.org/2000/svg" style="font-family:-apple-system,sans-serif">`;
  // Helper: curved path
  function flowPath(x1,y1,h1,x2,y2,h2,color,opacity){
    const mx=(x1+x2)/2;
    return`<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2} L${x2},${y2+h2} C${mx},${y2+h2} ${mx},${y1+h1} ${x1},${y1+h1} Z" fill="${color}" opacity="${opacity||0.35}"/>`;
  }
  // Income → center flows
  let cY=centerY;
  incNodes.forEach(n=>{
    const flowH=(n.amount/totalIn)*centerH;
    svg+=flowPath(labelL+nodeW,n.y,n.h,centerX,cY,flowH,n.color,0.3);
    cY+=flowH;
  });
  // Center → spending flows
  let cY2=centerY;
  spNodes.forEach(n=>{
    const flowH=(n.amount/totalIn)*centerH;
    svg+=flowPath(centerX+nodeW,cY2,flowH,labelL+pad+flowW+pad,n.y,n.h,n.color,0.3);
    cY2+=flowH;
  });
  // Center → savings flow
  if(netH>0&&net>0){
    const flowH=(net/totalIn)*centerH;
    svg+=flowPath(centerX+nodeW,cY2,flowH,labelL+pad+flowW+pad,netY,netH,'#22c55e',0.25);
  }
  // Draw nodes
  // Income nodes (left)
  incNodes.forEach(n=>{
    svg+=`<rect x="${labelL}" y="${n.y}" width="${nodeW}" height="${n.h}" rx="3" fill="${n.color}"/>`;
    svg+=`<text x="${labelL-6}" y="${n.y+n.h/2+4}" text-anchor="end" fill="#94a3b8" font-size="11">${n.name}</text>`;
  });
  // Center node
  svg+=`<rect x="${centerX}" y="${centerY}" width="${nodeW}" height="${centerH}" rx="3" fill="#3b82f6"/>`;
  svg+=`<text x="${centerX+nodeW/2}" y="${centerY-8}" text-anchor="middle" fill="#f8fafc" font-size="12" font-weight="600">${fmt(totalIn)}</text>`;
  // Spending nodes (right)
  spNodes.forEach(n=>{
    var rX=labelL+pad+flowW+pad;
    svg+=`<rect x="${rX}" y="${n.y}" width="${nodeW}" height="${n.h}" rx="3" fill="${n.color}"/>`;
    svg+=`<text x="${rX+nodeW+6}" y="${n.y+n.h/2+4}" fill="#94a3b8" font-size="11">${n.name} ${fmt(n.amount)}</text>`;
  });
  // Savings node
  if(netH>0&&net>0){
    var rX2=labelL+pad+flowW+pad;
    svg+=`<rect x="${rX2}" y="${netY}" width="${nodeW}" height="${netH}" rx="3" fill="#22c55e"/>`;
    svg+=`<text x="${rX2+nodeW+6}" y="${netY+netH/2+4}" fill="#86efac" font-size="11" font-weight="600">Savings ${fmt(net)}</text>`;
  }else if(net<0){
    svg+=`<text x="${labelL+pad+flowW+pad+nodeW+6}" y="${(yR||pad)+10}" fill="#fca5a5" font-size="11" font-weight="600">Over budget ${fmt(-net)}</text>`;
  }
  // Labels
  svg+=`<text x="${labelL}" y="${H+14}" fill="#475569" font-size="10">INCOME</text>`;
  svg+=`<text x="${labelL+pad+flowW+pad}" y="${H+14}" fill="#475569" font-size="10">SPENDING</text>`;
  svg+=`</svg>`;
  $('sankey-wrap').innerHTML=svg;
}
loadSankey();

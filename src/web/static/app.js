'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states={NORMAL:'Normal',SURVEILLANCE:'À surveiller',ALERT:'Alerte',CRITICAL:'Critique',DISCONNECTED:'Capteur déconnecté'};
const severities={INFO:'Information',WARNING:'Alerte',CRITICAL:'Critique'};
const clock=new Intl.DateTimeFormat('fr-FR',{timeZone:'Africa/Casablanca',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const preciseClock=new Intl.DateTimeFormat('fr-FR',{timeZone:'Africa/Casablanca',hour:'2-digit',minute:'2-digit',second:'2-digit',fractionalSecondDigits:1});
const calendar=new Intl.DateTimeFormat('fr-FR',{timeZone:'Africa/Casablanca',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const num=new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1});
const colors=['#216e95','#26775b','#97691c','#724793'];
const formatTime=v=>v?clock.format(new Date(v)):'—';
const formatDate=v=>v?calendar.format(new Date(v)):'—';
const badge=(text,style)=>`<span class="badge ${esc(style)}">${esc(text)}</span>`;
const isAlerts=document.body.dataset.view==='alerts';
let overview=null,selected=new URLSearchParams(location.search).get('patient'),parameter='heart_rate';
let minutes=60,offset=0,paused=false,timer=null,controller=null,requestId=0,unavailable=false,lastHistory=null,currentUser=null,doctors=[];
function online(){const r=overview?.runtime;return !unavailable && r?.running && r.connected && r.evaluated_at && Date.now()-Date.parse(r.evaluated_at)<5000;}
function stale(m){return !m || m.stale || Date.now()-Date.parse(m.timestamp)>(overview.max_age_seconds||120)*1000;}
function viewState(p){
  if(p.state==='NORMAL' && (paused || !online() || !Object.keys(p.latest).length || Object.values(p.latest).some(stale))) return 'SURVEILLANCE';
  return p.state;
}
async function get(path,signal){
  const response=await fetch(path,{signal,cache:'no-store'});
  if(response.status===401){SmartcareAuth.expired();throw new Error('Session expirée');}
  if(!response.ok)throw new Error('Données indisponibles');
  return response.json();
}
function patientList(){
  const focus=document.activeElement?.dataset.patient;
  $('patient-list').innerHTML=overview.patients.map(p=>`<button class="patient-button ${p.patient_id===selected?'active':''}" data-patient="${esc(p.patient_id)}" aria-pressed="${p.patient_id===selected}" aria-label="Sélectionner ${esc(p.name)} ${esc(p.patient_id)}"><strong>${esc(p.patient_id)} · ${esc(p.name)}</strong><small>${esc(states[viewState(p)])}</small></button>`).join('')||'<p class="empty">Aucun patient configuré.</p>';
  if(focus) [...$('patient-list').children].find(e=>e.dataset.patient===focus)?.focus({preventScroll:true});
}
function renderOverview(){
  $('updated-at').textContent=paused?'Affichage en pause':`Actualisé à ${formatTime(overview.generated_at)}`;
  $('receiver-status').textContent=unavailable?'Service indisponible':online()?'Réception active':overview.runtime.mode==='history'?'Historique uniquement':'Réception en attente';
  $('receiver-status').className=`connection ${online()?'online':'offline'}`;
  $('notice').hidden=!!online();
  $('notice').textContent='Les données affichées sont historiques ou la réception est interrompue. Le suivi ne peut pas être confirmé normal.';
  const navBadge=document.querySelector('.nav-alert-count');if(navBadge){navBadge.textContent=overview.totals.active_alerts;navBadge.hidden=!overview.totals.active_alerts;navBadge.classList.toggle('urgent',overview.totals.critical_patients>0);}
  if(isAlerts)return;
  if(!overview.patients.some(p=>p.patient_id===selected))selected=overview.patients[0]?.patient_id??null;
  patientList();
  const p=overview.patients.find(p=>p.patient_id===selected);
  if(!p){$('patient-title').textContent='Aucun patient disponible';$('profiles').textContent='';$('patient-subtitle').textContent='';$('vitals').innerHTML='<p class="empty">Aucun patient configuré ou enregistré.</p>';$('other-vitals').innerHTML='';return;}
  $('patient-title').textContent=p.name;
  $('profiles').textContent=p.profiles.map(v=>v.name).join(' · ');
  const state=viewState(p);$('patient-state').textContent=states[state];$('patient-state').className=`badge ${state.toLowerCase()}`;
  $('patient-subtitle').textContent=`${p.patient_id} · ${p.last_measurement_at?'Dernière mesure : '+formatDate(p.last_measurement_at):'Aucune mesure reçue'}`;
  if(!p.consent.granted){$('notice').hidden=false;$('notice').textContent='Suivi suspendu : consentement absent ou retiré. Contactez l’administrateur.';}
  const catalog=overview.parameters;
  const keys=Object.keys(catalog).sort((a,b)=>Number(p.priority_parameters.includes(b))-Number(p.priority_parameters.includes(a)));
  const cards=list=>list.map(key=>{const m=p.latest[key];return `<article class="vital ${m&&(stale(m)||unavailable)?'stale':''}"><div class="vital-label">${esc(catalog[key].label)}</div><div class="vital-value">${m?num.format(m.value):'—'}<span>${esc(catalog[key].unit)}</span></div><p class="vital-time">${m?`${stale(m)||unavailable?'Ancienne · ':''}${formatTime(m.timestamp)}`:'Aucune mesure'}</p></article>`;}).join('');
  $('vitals').innerHTML=p.consent.granted?cards(keys.slice(0,4)):'<p class="empty">Aucune donnée consultable sans consentement.</p>';
  $('other-vitals').innerHTML=p.consent.granted?cards(keys.slice(4)):'';
  if(!$('parameter').options.length){$('parameter').innerHTML=Object.entries(catalog).map(([key,p])=>`<option value="${esc(key)}">${esc(p.label)}</option>`).join('');$('parameter').value=parameter;}
}
function renderAlerts(data){
  $('alert-rows').innerHTML=data.items.map(a=>{const p=overview.patients.find(p=>p.patient_id===a.patient_id), actions=(a.actions||[]).map(action=>`<li>${action.action==='RESOLVED'?`Résolue par ${esc(action.actor)}`:`Médecin ${esc(action.target)} contacté par ${esc(action.actor)}`} · ${esc(formatDate(action.timestamp))}</li>`).join(''), nurse=currentUser?.role==='NURSE';return `<article class="alert-card severity-${a.severity.toLowerCase()} ${a.status==='ACTIVE'?'is-active':''}" data-alert-card="${esc(a.alert_id)}"><header><a href="/?patient=${encodeURIComponent(a.patient_id)}">${esc(a.patient_id)} · ${esc(p?.name||a.patient_id)}</a>${badge(severities[a.severity],a.severity.toLowerCase())}</header><strong>${esc((a.parameter||'').split(' + ').map(k=>overview.parameters[k]?.label||k).join(' + '))}</strong><p>${esc(a.message)}</p><small>${a.status==='ACTIVE'?'Active — action requise':'Résolue'} · ${esc(formatDate(a.timestamp))} · ${a.occurrences} observation(s)</small>${actions?`<ul class="alert-actions-history">${actions}</ul>`:''}${isAlerts&&a.status==='ACTIVE'?`<div class="alert-actions"><button class="button resolve-alert" data-resolve="${esc(a.alert_id)}">Résoudre l’alerte</button>${nurse?`<label>Médecin<select data-doctor-for="${esc(a.alert_id)}">${doctors.map(d=>`<option value="${d.user_id}">${esc(d.username)}</option>`).join('')}</select></label><button class="button contact-doctor" data-contact="${esc(a.alert_id)}" ${doctors.length?'':'disabled'}>Contacter le médecin</button>`:''}</div>`:''}</article>`;}).join('')||'<p class="empty">Aucune alerte physiologique pour cette sélection.</p>';
  if(isAlerts){$('alert-pagination').textContent=data.total?`${offset+1}–${offset+data.items.length} sur ${data.total}`:'Aucune alerte';$('previous-alerts').disabled=offset===0;$('next-alerts').disabled=offset+data.items.length>=data.total;}
}
function renderTechnical(items){
  $('technical-alerts').innerHTML=items.map(e=>`<article class="alert-card technical"><header><strong>Incident technique · ${esc(e.patient_id)}</strong><span>${e.status==='ACTIVE'?'Actif':'Résolu'}</span></header><p>${esc(e.description)}</p><small>${esc(e.device_id)} · ${esc(formatDate(e.timestamp))}</small></article>`).join('')||(isAlerts?'<p class="empty">Aucun incident technique dans cette sélection.</p>':'');
}
function renderChart(history) {
  lastHistory=history;
  const readings=history.items, catalog=overview.parameters[parameter];
  $('chart-caption').textContent=`${catalog.label} · ${catalog.unit} · ${readings.length} mesures${history.truncated?' · dernières valeurs affichées (limite atteinte)':''}`;
  $('measurement-rows').innerHTML=readings.length ? [...readings].reverse().map(m=>`<tr><td>${esc(formatDate(m.timestamp))} (${formatTime(m.timestamp)})</td><td>${num.format(m.value)} ${esc(m.unit)}</td><td>${esc(m.device_id)}</td><td>${m.quality==='valid'||m.quality==='good'?'Valide':esc(m.quality)}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">Aucune mesure sur cette période.</td></tr>';
  if (!readings.length) {
    $('chart').innerHTML='<p class="empty">Aucune mesure sur cette période.<br>Choisissez un autre paramètre ou une période plus large.</p>';
    $('chart-legend').innerHTML=''; return;
  }
  const width=760, height=260, left=58, right=24, top=18, bottom=38;
  const times=readings.map(m=>Date.parse(m.timestamp)), values=readings.map(m=>m.value);
  let minX=Math.min(...times), maxX=Math.max(...times), minY=Math.min(...values), maxY=Math.max(...values);
  if (minX===maxX) { minX-=1000; maxX+=1000; }
  const chartTime=v=>maxX-minX<60000?preciseClock.format(new Date(v)):formatTime(v);
  const margin=Math.max((maxY-minY)*0.2, Math.abs(maxY)*0.015, .5); minY-=margin; maxY+=margin;
  const x=v=>left+(v-minX)/(maxX-minX)*(width-left-right), y=v=>height-bottom-(v-minY)/(maxY-minY)*(height-top-bottom);
  let drawing='';
  for (let i=0;i<5;i++) {
    const value=minY+(maxY-minY)*i/4, yy=y(value);
    drawing+=`<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#edf0f6" stroke-dasharray="3 5"/><text x="${left-12}" y="${yy+4}" text-anchor="end">${num.format(value)}</text>`;
  }
  for (let i=0;i<4;i++) { const t=minX+(maxX-minX)*i/3; drawing+=`<text x="${x(t)}" y="${height-8}" text-anchor="${i===0?'start':i===3?'end':'middle'}">${chartTime(t)}</text>`; }
  const devices=[...new Set(readings.map(m=>m.device_id))];
  devices.forEach((device,index)=>{
    const color=colors[index%colors.length], points=readings.filter(m=>m.device_id===device);
    let segment=[];
    const flush=()=>{ if(segment.length>1) drawing+=`<polyline points="${segment.map(m=>`${x(Date.parse(m.timestamp))},${y(m.value)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`; segment=[]; };
    points.forEach((m,i)=>{ if(i && Date.parse(m.timestamp)-Date.parse(points[i-1].timestamp)>120000) flush(); segment.push(m); }); flush();
    points.forEach(m=>{drawing+=`<circle cx="${x(Date.parse(m.timestamp))}" cy="${y(m.value)}" r="3" fill="${color}"><title>${esc(device)} · ${chartTime(Date.parse(m.timestamp))} · ${num.format(m.value)} ${esc(m.unit)}</title></circle>`;});
  });
  $('chart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(catalog.label)} : ${readings.length} mesures. Les valeurs détaillées sont disponibles sous la courbe.">${drawing}</svg>`;
  $('chart-legend').innerHTML=devices.map((device,i)=>`<span><svg width="10" height="10" aria-hidden="true"><circle cx="4" cy="5" r="3" fill="${colors[i%colors.length]}"/></svg> ${esc(device)}</span>`).join('')+'<span>Passer sur un point pour lire sa valeur · Interruption de courbe au-delà de 2 min</span>';
}

function renderEvents(data) {
  const labels={STATE_CHANGED:'Changement d’état',DISCONNECTED:'Déconnexion du capteur',MISSING_DATA:'Données manquantes',RECOVERY:'Réception rétablie'};
  $('event-list').innerHTML=data.items.length ? data.items.map(e=>`<li><span class="event-mark" aria-hidden="true">↗</span><div>${esc(e.type==='STATE_CHANGED' && e.details ? `${states[e.details.previous_state]||e.details.previous_state} → ${states[e.details.state]||e.details.state}` : e.description)}<small class="muted"> · ${esc(labels[e.type]||'Événement technique')}</small></div><time datetime="${esc(e.timestamp)}">${esc(formatDate(e.timestamp))}</time></li>`).join('') : '<li class="empty">Aucun événement enregistré pour ce patient.</li>';
}

function clearDetails(){
  lastHistory=null;
  if(!isAlerts){$('chart').innerHTML='<p class="empty">Chargement de l’historique…</p>';$('chart-legend').innerHTML='';$('measurement-rows').innerHTML='';}
  $('alert-rows').innerHTML='<p class="empty">Chargement…</p>';$('technical-alerts').innerHTML='';
}
async function refresh(){
  clearTimeout(timer);controller?.abort();controller=new AbortController();
  const signal=controller.signal,id=++requestId;
  const timeout=setTimeout(()=>{if(id===requestId)controller.abort();},10000);
  try{
    const data=await get('/api/overview',signal);if(id!==requestId)return;
    overview=data;unavailable=false;renderOverview();
    if(isAlerts){
      const status=$('alert-status').value;
      const params=new URLSearchParams({status,limit:'10',offset:String(offset)});
      const alerts=await get(`/api/alerts?${params}`,signal);
      let technical=overview.patients.flatMap(p=>p.technical_alerts||[]);
      if(status!=='ACTIVE'){
        const histories=await Promise.all(overview.patients.filter(p=>p.consent.granted).map(p=>get(`/api/patients/${encodeURIComponent(p.patient_id)}/events`,signal)));
        const byId=new Map(technical.map(e=>[e.event_id,e]));
        histories.flatMap(h=>h.items).filter(e=>['DISCONNECTED','MISSING_DATA'].includes(e.type)).forEach(e=>byId.set(e.event_id,e));
        technical=[...byId.values()].filter(e=>status==='ALL'||e.status===status);
      }
      if(id!==requestId)return;renderAlerts(alerts);renderTechnical(technical);
    }else{
      const patient=overview.patients.find(p=>p.patient_id===selected);
      if(patient?.consent.granted){
        const pid=encodeURIComponent(selected);
        const [history,alerts]=await Promise.all([
          get(`/api/patients/${pid}/history?parameter=${parameter}&minutes=${minutes}&limit=240`,signal),
          get(`/api/alerts?patient_id=${pid}&status=ACTIVE&limit=3`,signal)]);
        if(id!==requestId)return;renderChart(history);renderAlerts(alerts);renderTechnical(patient.technical_alerts||[]);
      }else{clearDetails();$('chart').innerHTML='<p class="empty">Aucune donnée consultable.</p>';renderAlerts({items:[],total:0});renderTechnical([]);}
    }
    $('error').hidden=true;
  }catch(error){
    if(id!==requestId)return;unavailable=true;
    if(overview)renderOverview();
    $('error').hidden=false;$('error').textContent='Actualisation impossible. Les données peuvent être anciennes. Vérifiez le service, puis cliquez sur Actualiser.';
    $('receiver-status').textContent='Service indisponible';$('updated-at').textContent='Données non actualisées';
  }finally{clearTimeout(timeout);if(id===requestId&&!paused)timer=setTimeout(refresh,3000);}
}
$('patient-list')?.addEventListener('click',event=>{const b=event.target.closest('[data-patient]');if(!b)return;selected=b.dataset.patient;clearDetails();renderOverview();const url=new URL(location.href);url.searchParams.set('patient',selected);history.replaceState(null,'',url);refresh();});
$('parameter')?.addEventListener('change',()=>{parameter=$('parameter').value;clearDetails();refresh();});
document.querySelector('.segments')?.addEventListener('click',event=>{const b=event.target.closest('[data-minutes]');if(!b)return;minutes=Number(b.dataset.minutes);document.querySelectorAll('[data-minutes]').forEach(e=>{e.classList.toggle('active',e===b);e.setAttribute('aria-pressed',String(e===b));});clearDetails();refresh();});
$('alert-status')?.addEventListener('change',()=>{offset=0;clearDetails();refresh();});
$('previous-alerts')?.addEventListener('click',()=>{offset=Math.max(0,offset-10);refresh();});
$('next-alerts')?.addEventListener('click',()=>{offset+=10;refresh();});
$('alert-rows')?.addEventListener('click',async event=>{
  const alertId=event.target.dataset.resolve||event.target.dataset.contact;if(!alertId)return;
  event.target.disabled=true;
  try{
    if(event.target.dataset.resolve) await SmartcareAuth.request(`/api/alerts/${encodeURIComponent(alertId)}/resolve`,{method:'POST'});
    else {const select=document.querySelector(`[data-doctor-for="${CSS.escape(alertId)}"]`);await SmartcareAuth.request(`/api/alerts/${encodeURIComponent(alertId)}/contact-doctor`,{method:'POST',body:JSON.stringify({doctor_id:select.value})});}
    $('notice').hidden=false;$('notice').textContent=event.target.dataset.resolve?'Alerte résolue et enregistrée dans l’historique.':'Le contact du médecin a été enregistré.';await refresh();
  }catch(error){$('error').hidden=false;$('error').textContent=error.message;event.target.disabled=false;}
});
$('quick-patient-form')?.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,data=new FormData(form),profiles=data.getAll('profiles'),message=$('quick-patient-message');
  if(!profiles.length){message.textContent='Sélectionnez au moins un profil.';return;}
  try{await SmartcareAuth.request('/api/patient-registry',{method:'POST',body:JSON.stringify({patient_id:data.get('patient_id'),name:data.get('name'),profiles,monitoring_enabled:true})});message.textContent='Patient ajouté.';form.reset();await refresh();}catch(error){message.textContent=error.message;}
});
$('refresh').addEventListener('click',refresh);
$('pause')?.addEventListener('click',()=>{paused=!paused;$('pause').textContent=paused?'Reprendre le suivi':'Mettre en pause';clearTimeout(timer);if(paused&&overview)renderOverview();else refresh();});
// Even a paused display must never keep an obsolete Normal label.
setInterval(()=>{if(overview&&!isAlerts&&(paused||unavailable||!online()))renderOverview();},1000);
SmartcareAuth.init().then(async session=>{currentUser=session.user;const quick=$('quick-patient');if(quick)quick.hidden=!['ADMIN','DOCTOR'].includes(currentUser.role);if(currentUser.role==='NURSE')doctors=(await SmartcareAuth.request('/api/doctors')).items;return refresh();}).catch(error=>{$('account-error').textContent=error.message;});

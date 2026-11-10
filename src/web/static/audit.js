'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=value=>value?new Date(value).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca'}):'—';
const stateNames={CONNECTED:'Connecté',DISCONNECTED:'Déconnecté',DEGRADED:'Données incomplètes',WAITING:'En attente',PAUSED:'Suspendu',UNKNOWN:'Non déterminé'};
const eventNames={STATE_CHANGED:'Changement d’état',DISCONNECTED:'Déconnexion',MISSING_DATA:'Données manquantes',RECOVERY:'Reprise de réception',MONITORING_STARTED:'Surveillance démarrée'};
let overview=null;
async function load(){
  try{
    overview=await SmartcareAuth.request('/api/overview');
    const count=overview.totals.active_alerts, badge=document.querySelector('.nav-alert-count');badge.textContent=count;badge.hidden=!count;
    $('audit-updated').textContent=`Actualisé le ${date(overview.generated_at)}`;
    $('audit-devices').innerHTML=overview.patients.flatMap(p=>(p.devices||[]).map(d=>`<article class="audit-device ${d.status==='CONNECTED'?'connected':'attention'}"><div><strong>${esc(p.patient_id)} · ${esc(p.name)}</strong><span class="device-status">${esc(stateNames[d.status]||d.status)}</span></div><p>${esc(d.device_id)}</p><small>Dernière réception : ${esc(date(d.last_seen_at))}</small>${d.missing_parameters?.length?`<small>Paramètres absents : ${esc(d.missing_parameters.join(', '))}</small>`:''}</article>`)).join('')||'<p class="empty">Aucun capteur enregistré.</p>';
    const current=$('audit-patient').value;$('audit-patient').innerHTML='<option value="ALL">Tous les patients</option>'+overview.patients.map(p=>`<option value="${esc(p.patient_id)}">${esc(p.patient_id)} · ${esc(p.name)}</option>`).join('');if(current)$('audit-patient').value=current;
    await loadEvents();$('audit-error').hidden=true;
  }catch(error){$('audit-error').hidden=false;$('audit-error').textContent=error.message;}
}
async function loadEvents(){
  const selected=$('audit-patient').value||'ALL', patients=overview.patients.filter(p=>selected==='ALL'||p.patient_id===selected).filter(p=>p.consent.granted);
  const histories=await Promise.all(patients.map(p=>SmartcareAuth.request(`/api/patients/${encodeURIComponent(p.patient_id)}/events?limit=100`).then(data=>data.items.map(item=>({...item,patient_name:p.name})))));
  const events=histories.flat().sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp));
  $('audit-events').innerHTML=events.map(e=>`<tr><td>${esc(date(e.timestamp))}</td><td>${esc(e.patient_id||'Système')}<small>${esc(e.patient_name||'')}</small></td><td>${esc(eventNames[e.type]||e.type)}</td><td>${esc(e.description)}</td><td><span class="status-dot ${e.status?.toLowerCase()}">${esc(e.status==='ACTIVE'?'Actif':e.status==='RESOLVED'?'Résolu':'Enregistré')}</span></td></tr>`).join('')||'<tr><td colspan="5" class="empty">Aucun événement enregistré.</td></tr>';
}
$('refresh').addEventListener('click',load);$('audit-patient').addEventListener('change',()=>loadEvents().catch(e=>{$('audit-error').hidden=false;$('audit-error').textContent=e.message;}));
SmartcareAuth.init().then(load).catch(error=>$('account-error').textContent=error.message);

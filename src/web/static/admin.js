'use strict';
const $=id=>document.getElementById(id);
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roleNames={ADMIN:'Administrateur',DOCTOR:'Médecin',NURSE:'Infirmier / infirmière'};
const actionNames={BOOTSTRAP_ADMIN:'Premier administrateur créé',LOGIN_SUCCESS:'Connexion réussie',LOGIN_FAILED:'Connexion refusée',LOGIN_THROTTLED:'Tentatives limitées',LOGOUT:'Déconnexion',USER_CREATED:'Compte créé',USER_UPDATED:'Compte modifié',REGISTRATION_REQUESTED:'Demande de compte',REGISTRATION_APPROVED:'Compte validé',PATIENT_CREATED:'Patient ajouté',ALERT_RESOLVED:'Alerte résolue',DOCTOR_CONTACTED:'Médecin contacté',ACCESS_DENIED:'Accès refusé',CSRF_REJECTED:'Requête refusée'};
let users=[], auditOffset=0, consents=[];
actionNames.CONSENT_GRANTED='Consentement enregistré';actionNames.CONSENT_REVOKED='Consentement retiré';
async function audit(){
  const data=await SmartcareAuth.request(`/api/admin/audit?limit=25&offset=${auditOffset}`);
  $('audit').innerHTML=data.items.map(a=>`<tr><td>${escape(new Date(a.timestamp).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca'}))}</td><td>${escape(a.username||'—')}</td><td>${escape(actionNames[a.action]||a.action)}</td><td>${escape(users.find(u=>u.user_id===a.target)?.username||a.target||'—')}</td></tr>`).join('')||'<tr><td colspan="4">Aucun événement.</td></tr>';
  $('audit-prev').disabled=auditOffset===0; $('audit-next').disabled=data.items.length<25;
}
async function reload(){
  users=(await SmartcareAuth.request('/api/admin/users')).items;
  $('users').innerHTML=users.map(u=>`<tr class="${u.approval_status==='PENDING'?'pending-user':''}"><td>${escape(u.username)}${u.approval_status==='PENDING'?'<span class="pending-label">Validation demandée</span>':''}</td><td><select data-role="${u.user_id}" aria-label="Rôle de ${escape(u.username)}">${Object.entries(roleNames).map(([r,label])=>`<option value="${r}" ${r===u.role?'selected':''}>${label}</option>`).join('')}</select></td><td>${u.approval_status==='PENDING'?'En attente':u.active?'Actif':'Désactivé'}</td><td class="user-actions">${u.approval_status==='PENDING'?`<button class="button primary" data-approve="${u.user_id}">Valider le compte</button>`:`<button class="button" data-save="${u.user_id}">Enregistrer le rôle</button><button class="button" data-toggle="${u.user_id}">${u.active?'Désactiver':'Réactiver'}</button>`}</td></tr>`).join('');
  $('reset-user').innerHTML=users.map(u=>`<option value="${u.user_id}">${escape(u.username)}</option>`).join('');
  consents=(await SmartcareAuth.request('/api/admin/consents')).items;
  $('consents').innerHTML=consents.map(c=>`<tr><td>${escape(c.name)}<small>${escape(c.patient_id)}</small></td><td>${c.granted?'Accordé':'Non accordé'}${c.source==='simulation_config'?'<small>Simulation</small>':''}</td><td>${c.date?escape(new Date(c.date).toLocaleString('fr-FR')):'—'}</td><td><button class="button" data-consent="${escape(c.patient_id)}">${c.granted?'Retirer le consentement':'Enregistrer l’accord'}</button></td></tr>`).join('');
  await audit();
}
$('consents').addEventListener('click',event=>{
  const pid=event.target.dataset.consent;if(!pid)return;
  perform(()=>SmartcareAuth.request(`/api/admin/consents/${encodeURIComponent(pid)}`,{method:'PUT',body:JSON.stringify({granted:!consents.find(c=>c.patient_id===pid).granted})}));
});
async function perform(operation){
  $('admin-message').textContent='';
  try{await operation(); await reload(); $('admin-message').textContent='Modification enregistrée.';}
  catch(error){$('admin-message').textContent=error.message;}
}
$('create-user').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.target;
  perform(async()=>{await SmartcareAuth.request('/api/admin/users',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();});
});
$('users').addEventListener('click',event=>{
  const id=event.target.dataset.save||event.target.dataset.toggle||event.target.dataset.approve; if(!id)return;
  const changes=event.target.dataset.approve ? {active:true,role:document.querySelector(`[data-role="${id}"]`).value} : event.target.dataset.save ? {role:document.querySelector(`[data-role="${id}"]`).value} : {active:!users.find(u=>u.user_id===id).active};
  perform(()=>SmartcareAuth.request(`/api/admin/users/${id}`,{method:'PATCH',body:JSON.stringify(changes)}));
});
$('create-patient').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.target, data=new FormData(form), profiles=data.getAll('profiles');
  if(!profiles.length){$('admin-message').textContent='Sélectionnez au moins un profil clinique.';return;}
  perform(async()=>{await SmartcareAuth.request('/api/patient-registry',{method:'POST',body:JSON.stringify({patient_id:data.get('patient_id'),name:data.get('name'),profiles,monitoring_enabled:true})});form.reset();});
});
$('reset-password').addEventListener('submit',event=>{
  event.preventDefault(); const form=event.target, values=Object.fromEntries(new FormData(form));
  perform(async()=>{await SmartcareAuth.request(`/api/admin/users/${values.user_id}`,{method:'PATCH',body:JSON.stringify({password:values.password})});form.reset();});
});
$('reload-audit').onclick=()=>perform(async()=>{auditOffset=0;});
$('audit-prev').onclick=()=>{auditOffset=Math.max(0,auditOffset-25);audit().catch(e=>$('admin-message').textContent=e.message);};
$('audit-next').onclick=()=>{auditOffset+=25;audit().catch(e=>$('admin-message').textContent=e.message);};
SmartcareAuth.init().then(reload).catch(error=>$('admin-message').textContent=error.message);

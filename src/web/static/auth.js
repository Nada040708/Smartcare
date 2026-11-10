'use strict';
window.SmartcareAuth = (() => {
  let session = null;
  const roles = {ADMIN:'Administrateur', DOCTOR:'Médecin', NURSE:'Infirmier / infirmière'};
  function expired() { document.body.hidden=true; location.replace('/login'); }
  async function request(path, options={}) {
    const response = await fetch(path, {...options, cache:'no-store', headers:{
      'Content-Type':'application/json', ...(session ? {'X-CSRF-Token':session.csrf_token}:{}), ...options.headers
    }});
    if (response.status===401 && path!=='/api/auth/login') { expired(); throw new Error('Session expirée.'); }
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Opération impossible.');
    return data;
  }
  async function init() {
    session = await request('/api/auth/me');
    const label = document.getElementById('account-label');
    if (label) label.textContent = `${session.user.username} · ${roles[session.user.role]}`;
    const admin = document.getElementById('admin-link');
    if (admin) admin.hidden = session.user.role !== 'ADMIN';
    document.getElementById('logout')?.addEventListener('click', async () => {
      try { await request('/api/auth/logout', {method:'POST'}); expired(); }
      catch (error) { document.getElementById('account-error').textContent=error.message; }
    });
    return session;
  }
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
  return {request, init, expired};
})();

'use strict';
document.getElementById('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button=event.target.querySelector('button'), error=document.getElementById('login-error');
  button.disabled=true; error.textContent='';
  try {
    await SmartcareAuth.request('/api/auth/login', {method:'POST',body:JSON.stringify({
      username:document.getElementById('username').value, password:document.getElementById('password').value
    })});
    document.getElementById('password').value=''; location.replace('/');
  } catch (failure) { error.textContent=failure.message; }
  finally { button.disabled=false; }
});

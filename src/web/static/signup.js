'use strict';
document.getElementById('signup-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form=event.target, button=form.querySelector('button'), message=document.getElementById('signup-message');
  button.disabled=true; message.className='form-error'; message.textContent='';
  try {
    const values=Object.fromEntries(new FormData(form));
    const result=await SmartcareAuth.request('/api/auth/signup',{method:'POST',body:JSON.stringify(values)});
    form.reset(); message.className='success-message'; message.textContent=result.message;
  } catch (error) { message.textContent=error.message; }
  finally { button.disabled=false; }
});

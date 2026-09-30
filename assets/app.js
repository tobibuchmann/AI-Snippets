(function(){
  const form=document.getElementById('questForm');
  if(!form)return;

  function setBusy(button,busy){
    if(!button.dataset.defaultText) button.dataset.defaultText=button.textContent;
    button.disabled=busy;
    button.textContent=busy?'Bestellung wird vorbereitet …':button.dataset.defaultText;
  }

  form.addEventListener('submit',async(e)=>{
    e.preventDefault();
    const button=form.querySelector('button[type="submit"]');
    const checkedLocations=[...form.querySelectorAll('input[name="locations"]:checked')].map(x=>x.value);
    if(checkedLocations.length===0&&!form.other_locations.value.trim()){
      alert('Bitte wähle mindestens einen nutzbaren Ort aus.');
      return;
    }

    const fd=new FormData(form);
    const data=Object.fromEntries(fd.entries());
    data.locations=checkedLocations;
    const cfg=window.GQ_CONFIG||{};
    const api=(cfg.API_BASE||'').replace(/\/$/,'');
    if(!api){alert('Der Bestellservice ist noch nicht konfiguriert.');return;}

    localStorage.setItem('geburtstagsquest_order',JSON.stringify(data));
    setBusy(button,true);

    try{
      const orderRes=await fetch(api+'/api/orders',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)
      });
      const order=await orderRes.json();
      if(!orderRes.ok) throw new Error(order.error||'Bestellung konnte nicht gespeichert werden.');
      localStorage.setItem('geburtstagsquest_order_id',order.order_id);

      const checkoutRes=await fetch(api+'/api/create-checkout',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:order.order_id})
      });
      const checkout=await checkoutRes.json();
      if(checkoutRes.status===503&&checkout.error==='payments_not_configured'){
        throw new Error('Die Zahlung wird gerade eingerichtet. Bitte versuche es später noch einmal.');
      }
      if(!checkoutRes.ok||!checkout.checkout_url) throw new Error(checkout.error||'Checkout konnte nicht gestartet werden.');
      window.location.href=checkout.checkout_url;
    }catch(err){
      console.error(err);
      alert(err.message||'Leider ist ein Fehler aufgetreten.');
      setBusy(button,false);
    }
  });
})();
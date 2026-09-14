import React,{useEffect,useState} from 'react';
import {Check, Copy, Crown, QrCode, Sparkles, X, Zap} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {api} from '../lib/api';

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const tierClass=(index,total)=>index===0?'basic':index===total-1?'premium':'plus';

export default function PlanChoice(){
  const nav=useNavigate();
  const [plans,setPlans]=useState([]);
  const [access,setAccess]=useState(null);
  const [order,setOrder]=useState(null);
  const [taxId,setTaxId]=useState('');
  const [qrImage,setQrImage]=useState('');
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState('');
  const [copied,setCopied]=useState(false);

  useEffect(()=>{
    Promise.all([api('/api/plans'),api('/api/me/publish-plan')])
      .then(([catalog,current])=>{setPlans(catalog||[]);setAccess(current)})
      .catch(e=>setErr(e.message));
  },[]);

  useEffect(()=>{
    if(!order?.id || order.status==='paid') return;
    let cancelled=false;
    if(order.qr_image_available){
      api(`/api/payments/${order.id}/qrcode`).then(r=>{if(!cancelled)setQrImage(r.data_url||'')}).catch(()=>{});
    }
    const timer=setInterval(async()=>{
      try{
        const status=await api(`/api/payments/${order.id}/status`);
        if(cancelled) return;
        if(status.status==='paid'){
          setOrder(prev=>({...prev,status:'paid'}));
          clearInterval(timer);
          api('/api/me/publish-plan').then(setAccess).catch(()=>{});
        }else if(['failed','cancelled'].includes(status.status)){
          setOrder(prev=>({...prev,status:status.status}));
          clearInterval(timer);
        }
      }catch{}
    },5000);
    return()=>{cancelled=true;clearInterval(timer)};
  },[order?.id,order?.status]);

  async function choosePlan(plan){
    setErr('');
    setBusy(true);
    try{
      if(plan.free || Number(plan.amount||0)<=0){
        await api('/api/payments',{method:'POST',body:JSON.stringify({plan_code:plan.code,method:'pix'})});
        const current=await api('/api/me/publish-plan');
        setAccess(current);
        nav('/publicar');
        return;
      }
      const digits=taxId.replace(/\D/g,'');
      if(![11,14].includes(digits.length)){
        setErr('Informe seu CPF ou CNPJ para gerar o PIX do plano pago.');
        return;
      }
      const payment=await api('/api/payments',{method:'POST',body:JSON.stringify({plan_code:plan.code,method:'pix',tax_id:digits})});
      setOrder(payment);
    }catch(e){setErr(e.message)}finally{setBusy(false)}
  }

  async function copyPix(){
    if(!order?.pix_code) return;
    await navigator.clipboard.writeText(order.pix_code);
    setCopied(true);
    setTimeout(()=>setCopied(false),1800);
  }

  if(access?.ready && !order) return <div className="page plan-gate-ready">
    <div className="plan-gate-success"><Check/><div><span className="section-kicker">PLANO SELECIONADO</span><h1>{access.plan?.name}</h1><p>Seu plano já está liberado. Agora você pode publicar o anúncio.</p><button className="primary" onClick={()=>nav('/publicar')}>Continuar para publicar</button></div></div>
  </div>;

  return <div className="page plan-choice-page">
    <div className="plan-choice-hero">
      <div>
        <span className="section-kicker">ANTES DE PUBLICAR</span>
        <h1>Escolha como seu anúncio será publicado</h1>
        <p>Todo anúncio precisa de um plano. O <b>Grátis não gera cobrança</b>. Plus e Premium são liberados depois da confirmação do PIX.</p>
      </div>
      <div className="plan-choice-steps"><span><b>1</b> Escolha o plano</span><span><b>2</b> Pague somente se for Plus/Premium</span><span><b>3</b> Publique o anúncio</span></div>
    </div>

    {!order ? <>
      <div className="plan-choice-tax">
        <QrCode/>
        <div><b>CPF/CNPJ para planos pagos</b><span>Necessário apenas se escolher Plus ou Premium. No Grátis, nenhuma cobrança é criada.</span></div>
        <input value={taxId} onChange={e=>setTaxId(e.target.value)} inputMode="numeric" placeholder="CPF ou CNPJ"/>
      </div>
      {err&&<div className="form-error plan-choice-error">{err}</div>}
      <div className="plans-highlight-grid colorful-plans-grid plan-choice-grid">
        {plans.map((plan,index)=>{
          const tier=tierClass(index,plans.length);
          return <article className={`plan-teaser-card ${tier} ${tier==='premium'?'recommended':''}`} key={plan.code}>
            <div className="plan-top-badges">
              <span className="plan-mini-kicker">{tier==='basic'?'Grátis':tier==='plus'?'Plus':'Premium'}</span>
              {tier==='plus'&&<span className="plan-chip sold">Mais vendido</span>}
              {tier==='premium'&&<span className="plan-chip premium-chip">Mais vantagens</span>}
            </div>
            <h3>{plan.name}</h3>
            <div className="plan-teaser-price">{plan.free?'R$ 0,00':money(plan.amount)}</div>
            <p>{plan.tagline}</p>
            {(plan.features||[]).length>0&&<ul>{plan.features.map(f=><li key={f}>{f}</li>)}</ul>}
            {(plan.limitations||[]).length>0&&<ul className="plan-limit-list">{plan.limitations.map(f=><li key={f}><X size={14}/> {f}</li>)}</ul>}
            <button className={`plan-cta ${tier!=='basic'?'active':''}`} disabled={busy} onClick={()=>choosePlan(plan)}>
              {busy?'Aguarde...':plan.free?'Escolher Grátis':'Gerar PIX e escolher'}
            </button>
          </article>
        })}
      </div>
    </> : <div className={`checkout-card pagbank-checkout plan-choice-checkout ${order.status==='paid'?'paid':''}`}>
      <h2>{order.status==='paid'?'Plano liberado':order.status==='failed'?'Pagamento recusado':order.status==='cancelled'?'Pagamento cancelado':'Pague com PIX'}</h2>
      <p>Valor: <b>{money(order.amount)}</b></p>
      <p>Provedor: <b>PagBank</b></p>
      {order.status==='pending'&&<>
        {qrImage&&<img className="pagbank-qr-image" src={qrImage} alt="QR Code PIX PagBank"/>}
        {order.pix_code&&<div className="pix-copy-area"><code>{order.pix_code}</code><button type="button" className="secondary-btn" onClick={copyPix}><Copy/>{copied?'Copiado':'Copiar PIX'}</button></div>}
        <div className="pagbank-waiting"><span className="payment-pulse"></span> Aguardando confirmação do PagBank...</div>
        <small>Assim que o PagBank confirmar, o botão para publicar será liberado.</small>
      </>}
      {order.status==='paid'&&<><div className="success-box"><Check/> Pagamento confirmado. Seu plano está pronto para uso.</div><button className="primary wide" onClick={()=>nav('/publicar')}>Publicar anúncio agora</button></>}
      {['failed','cancelled'].includes(order.status)&&<button className="primary wide" onClick={()=>{setOrder(null);setQrImage('')}}>Escolher outro plano</button>}
    </div>}
  </div>;
}

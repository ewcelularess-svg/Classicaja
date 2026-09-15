import React,{useEffect,useState} from 'react';
import {Check, Copy, Crown, QrCode, Sparkles, X, Zap} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {api} from '../lib/api';
import {useAuth} from '../main';

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const tierClass=(index,total)=>index===0?'basic':index===total-1?'premium':'plus';

export default function PlanChoice(){
  const nav=useNavigate();
  const {user,refreshUser}=useAuth();
  const [plans,setPlans]=useState([]);
  const [access,setAccess]=useState(null);
  const [order,setOrder]=useState(null);
  const [taxId,setTaxId]=useState('');
  const [qrImage,setQrImage]=useState('');
  const [busy,setBusy]=useState(false);
  const [err,setErr]=useState('');
  const [copied,setCopied]=useState(false);
  const [verifyBusy,setVerifyBusy]=useState(false);

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

  async function resendVerification(){
    if(!user?.email) return;
    setErr('');setVerifyBusy(true);
    try{
      const result=await api('/api/auth/resend-verification',{method:'POST',body:JSON.stringify({email:user.email})});
      setErr(result.message||'Se o e-mail estiver pendente, enviaremos um novo link.');
      await refreshUser().catch(()=>{});
    }catch(e){setErr(e.message)}finally{setVerifyBusy(false)}
  }

  async function copyPix(){
    if(!order?.pix_code) return;
    await navigator.clipboard.writeText(order.pix_code);
    setCopied(true);
    setTimeout(()=>setCopied(false),1800);
  }

  if(access?.ready && !order) return <div className="page plan-gate-ready">
    <div className="plan-gate-success"><Check/><div><span className="section-kicker">PLANO ATIVO</span><h1>{access.plan?.name}</h1><p>Seu plano já está liberado. Você usou <b>{access.ads_used||0} de {access.ad_limit||0}</b> vagas e ainda pode publicar <b>{access.ads_remaining||0}</b> anúncio(s).</p><button className="primary" onClick={()=>nav('/publicar')}>Continuar para publicar</button></div></div>
  </div>;

  return <div className="page plan-choice-page">
    <div className="plan-choice-hero">
      <div>
        <span className="section-kicker">ANTES DE PUBLICAR</span>
        <h1>Escolha como seu anúncio será publicado</h1>
        <p>Seu plano vale para a conta durante a validade e possui um limite de anúncios. O <b>Grátis libera 3 anúncios por conta por 7 dias</b>. Plus e Premium permitem várias publicações até o limite do plano, sem pagar novamente a cada anúncio.</p>
      </div>
      <div className="plan-choice-steps"><span><b>1</b> Use seu plano ativo ou escolha um</span><span><b>2</b> Pague somente ao contratar/renovar</span><span><b>3</b> Publique até o limite do plano</span></div>
    </div>

    {!order ? <>
      {access?.status==='quota_full'&&access?.plan&&<div className="plan-quota-alert"><div><b>Limite do {access.plan.name} atingido</b><span>Você já possui {access.ads_used||0} anúncio(s) cadastrados e o limite deste plano é {access.ad_limit||0}. Exclua um anúncio antigo para liberar uma vaga{Number(access.plan.boost||0)<3?' ou faça upgrade para um plano maior':''}.</span></div></div>}
      {access?.status==='expired'&&access?.plan&&<div className="plan-quota-alert"><div><b>{access.plan.name} vencido</b><span>{access.plan.code==='boost_30'?'Sua conta continua vinculada ao Premium. Renove o Premium para voltar a publicar.':'Renove o Plus ou faça upgrade para Premium para voltar a publicar.'}</span></div></div>}
      {user && !user.email_verified&&<div className="email-verify-banner"><div><b>Confirme seu e-mail</b><span>O Plano Grátis é liberado somente após a confirmação do e-mail. Planos pagos continuam disponíveis normalmente.</span></div><button type="button" className="secondary-btn" onClick={resendVerification} disabled={verifyBusy}>{verifyBusy?'Enviando...':'Reenviar confirmação'}</button></div>}
      <div className="plan-choice-tax">
        <QrCode/>
        <div><b>CPF/CNPJ para planos pagos</b><span>Necessário apenas se escolher Plus ou Premium. No Grátis, nenhuma cobrança é criada.</span></div>
        <input value={taxId} onChange={e=>setTaxId(e.target.value)} inputMode="numeric" placeholder="CPF ou CNPJ"/>
      </div>
      {err&&<div className="form-error plan-choice-error">{err}</div>}
      <div className="plans-highlight-grid colorful-plans-grid plan-choice-grid">
        {plans.map((plan,index)=>{
          const tier=tierClass(index,plans.length);
          const currentCode=access?.plan?.code||null;
          const allowedPaid=access?.allowed_paid_plan_codes||['boost_15','boost_30'];
          const paidAccount=['boost_15','boost_30'].includes(currentCode);
          const freeLocked=Boolean(plan.free && (access?.free_available===false || paidAccount));
          const transitionLocked=Boolean(!plan.free && paidAccount && !allowedPaid.includes(plan.code));
          const isRenewal=Boolean(paidAccount && plan.code===currentCode);
          const isUpgrade=Boolean(currentCode==='boost_15' && plan.code==='boost_30');
          const actionLabel=freeLocked?'Indisponível':transitionLocked?'Indisponível':isRenewal?`Renovar ${currentCode==='boost_30'?'Premium':'Plus'}`:isUpgrade?'Fazer upgrade para Premium':plan.free?'Escolher Grátis':'Gerar PIX e escolher';
          return <article className={`plan-teaser-card ${tier} ${tier==='premium'?'recommended':''} ${(freeLocked||transitionLocked)?'plan-locked':''}`} key={plan.code}>
            <div className="plan-top-badges">
              <span className="plan-mini-kicker">{tier==='basic'?'Grátis':tier==='plus'?'Plus':'Premium'}</span>
              {tier==='plus'&&<span className="plan-chip sold">Mais vendido</span>}
              {tier==='premium'&&<span className="plan-chip premium-chip">Mais vantagens</span>}
              {freeLocked&&<span className="plan-chip used-chip">Grátis já utilizado</span>}
            </div>
            <h3>{plan.name}</h3>
            <div className="plan-teaser-price">{plan.free?'R$ 0,00':money(plan.amount)}</div>
            <p>{plan.tagline}</p>
            <div className="plan-ad-limit"><b>{plan.ad_limit||1}</b> anúncio(s) cadastrados no máximo</div>
            {(plan.features||[]).length>0&&<ul>{plan.features.map(f=><li key={f}>{f}</li>)}</ul>}
            {(plan.limitations||[]).length>0&&<ul className="plan-limit-list">{plan.limitations.map(f=><li key={f}><X size={14}/> {f}</li>)}</ul>}
            <button className={`plan-cta ${tier!=='basic'?'active':''}`} disabled={busy || freeLocked || transitionLocked} onClick={()=>choosePlan(plan)}>
              {busy?'Aguarde...':actionLabel}
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
      {order.status==='paid'&&<><div className="success-box"><Check/> Pagamento confirmado. Seu plano foi {order.purchase_action==='upgrade'?'atualizado':order.purchase_action==='renewal'?'renovado':'ativado'}.</div>{access?.ready?<button className="primary wide" onClick={()=>nav('/publicar')}>Publicar anúncio agora</button>:access?.status==='quota_full'?<div className="form-error">Plano ativo, mas o limite de {access.ad_limit||0} anúncios cadastrados já foi atingido. {access.plan?.code==='boost_15'?'Exclua um anúncio ou faça upgrade para Premium.':'Exclua um anúncio para liberar uma vaga.'}</div>:<button className="primary wide" onClick={()=>nav('/publicar')}>Continuar</button>}</>}
      {['failed','cancelled'].includes(order.status)&&<button className="primary wide" onClick={()=>{setOrder(null);setQrImage('')}}>Escolher outro plano</button>}
    </div>}
  </div>;
}

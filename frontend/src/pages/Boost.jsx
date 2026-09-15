import React,{useEffect,useState} from 'react';
import {Check, Copy, Crown, QrCode, Sparkles, Zap, X} from 'lucide-react';
import {Link,useParams} from 'react-router-dom';
import {api} from '../lib/api';
const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const rows = [
  {label:'Publicação normal no marketplace', values:[true,true,true]},
  {label:'Selo de anúncio em destaque', values:[false,true,true]},
  {label:'Prioridade nas buscas', values:['Sem prioridade','Maior','Máxima']},
  {label:'Tempo em evidência', values:['Sem destaque','15 dias','30 dias']},
  {label:'Melhor posição no catálogo', values:[false,true,true]},
  {label:'Mais visualizações no catálogo', values:[false,false,true]},
  {label:'Maior exposição entre anúncios', values:[false,false,true]},
];
function tierClass(index,total){if(index===0)return'basic';if(index===total-1)return'premium';return'plus'}
function renderCell(value){if(value===true)return <span className="table-yes"><Check size={15}/> Sim</span>;if(value===false)return <span className="table-no"><X size={15}/> Não</span>;return <span className="table-text">{value}</span>}

export default function Boost(){
 const {id}=useParams();
 const [plans,setPlans]=useState([]);
 const [p,setP]=useState(null);
 const [access,setAccess]=useState(null);
 const [order,setOrder]=useState(null);
 const [busy,setBusy]=useState(false);
 const [taxId,setTaxId]=useState('');
 const [qrImage,setQrImage]=useState('');
 const [copied,setCopied]=useState(false);
 const [err,setErr]=useState('');
 useEffect(()=>{api('/api/plans').then(setPlans);api(`/api/products/${id}`).then(setP);api('/api/me/publish-plan').then(setAccess).catch(()=>{})},[id]);

 useEffect(()=>{
   if(!order?.id || order.status==='paid') return;
   let cancelled=false;
   if(order.qr_image_available){
     api(`/api/payments/${order.id}/qrcode`).then(r=>{if(!cancelled)setQrImage(r.data_url||'')}).catch(()=>{});
   }
   const timer=setInterval(async()=>{
     try{
       const status=await api(`/api/payments/${order.id}/status`);
       if(cancelled)return;
       if(status.status==='paid'){
         setOrder(prev=>({...prev,status:'paid'}));
         clearInterval(timer);
         api(`/api/products/${id}`).then(setP).catch(()=>{});
         api('/api/me/publish-plan').then(setAccess).catch(()=>{});
       }else if(['failed','cancelled'].includes(status.status)){
         setOrder(prev=>({...prev,status:status.status}));
         clearInterval(timer);
       }
     }catch{}
   },5000);
   return()=>{cancelled=true;clearInterval(timer)};
 },[order?.id,order?.status,id]);

 const buy=async code=>{
   setErr('');
   const digits=taxId.replace(/\D/g,'');
   if(![11,14].includes(digits.length)){setErr('Informe seu CPF ou CNPJ para gerar o PIX PagBank.');return}
   setBusy(true);
   try{
     const o=await api('/api/payments',{method:'POST',body:JSON.stringify({product_id:id,plan_code:code,method:'pix',tax_id:digits})});
     setOrder(o);setQrImage('');
   }catch(e){setErr(e.message)}finally{setBusy(false)}
 };
 const copyPix=async()=>{if(!order?.pix_code)return;await navigator.clipboard.writeText(order.pix_code);setCopied(true);setTimeout(()=>setCopied(false),1800)};

 return <div className="page boost-page">
  <div className="boost-hero-card">
    <div><span className="section-kicker">MONETIZAÇÃO</span><h1>Impulsione seu anúncio</h1><p>Plus e Premium aumentam a exposição do anúncio. O pagamento é gerado por PIX real do PagBank.</p><div className="boost-hero-benefits"><span><Zap size={16}/> Mais cliques</span><span><Sparkles size={16}/> Mais destaque</span><span><Crown size={16}/> Mais prioridade</span></div></div>
    {p&&<div className="boost-product boost-product-premium"><Sparkles/><div><b>{p.title}</b><span>{p.featured_active?'Este anúncio já possui destaque ativo.':'Escolha Plus ou Premium para aumentar a exposição do anúncio.'}</span></div></div>}
  </div>

  {!order ? <>
    <div className="pagbank-payment-box">
      <div className="pagbank-payment-title"><QrCode/><div><b>Pagamento via PIX PagBank</b><span>O QR Code será gerado pelo PagBank e confirmado automaticamente após o pagamento.</span></div></div>
      <label>CPF ou CNPJ do pagador<input value={taxId} onChange={e=>setTaxId(e.target.value)} inputMode="numeric" placeholder="Somente números"/></label>
      {err&&<div className="form-error">{err}</div>}
    </div>

    <div className="plan-grid premium-plan-grid colorful-plans-grid">
      {plans.map((plan,index)=>{
        const tier=tierClass(index,plans.length);
        const currentCode=access?.plan?.code||null;
        const paidAccount=['boost_15','boost_30'].includes(currentCode);
        const allowed=access?.allowed_paid_plan_codes||['boost_15','boost_30'];
        const locked=Boolean((plan.free&&paidAccount)||(!plan.free&&paidAccount&&!allowed.includes(plan.code)));
        const isRenewal=Boolean(paidAccount&&plan.code===currentCode);
        const isUpgrade=Boolean(currentCode==='boost_15'&&plan.code==='boost_30');
        const paidLabel=isRenewal?`Renovar ${currentCode==='boost_30'?'Premium':'Plus'}`:isUpgrade?'Fazer upgrade para Premium':'Pagar com PIX';
        return <div className={`plan-card ${tier} ${tier==='premium'?'plan-card-featured':''} ${locked?'plan-locked':''}`} key={plan.code}>
        <div className="plan-top-badges"><span className="plan-name">{tier==='basic'?'Grátis':tier==='plus'?'Plus':'Premium'}</span>{tier==='plus'&&<span className="plan-chip sold">Mais vendido</span>}{tier==='plus'&&<span className="plan-chip value">Melhor custo-benefício</span>}{tier==='premium'&&<span className="plan-chip premium-chip">Mais vantagens</span>}</div>
        <b>{plan.free?'Grátis':money(plan.amount)}</b><p className="plan-copy">{plan.tagline||'Escolha o nível de exposição do seu anúncio.'}</p>
        <div className="plan-ad-limit"><b>{plan.ad_limit||1}</b> anúncio(s) cadastrados no máximo</div>
        {(plan.features||[]).length>0&&<ul>{(plan.features||[]).map(feature=><li key={feature}><Check/> {feature}</li>)}</ul>}
        {(plan.limitations||[]).length>0&&<ul className="plan-limit-list">{(plan.limitations||[]).map(item=><li key={item}><X/> {item}</li>)}</ul>}
        {plan.free?<Link className={`plan-free-btn wide ${locked?'disabled':''}`} aria-disabled={locked} onClick={e=>{if(locked)e.preventDefault()}} to={`/produto/${id}`}>{locked?'Indisponível':'Continuar no Grátis'}</Link>:<button className="primary wide" disabled={busy||locked} onClick={()=>buy(plan.code)}>{busy?'Gerando PIX...':locked?'Indisponível':paidLabel}</button>}
      </div>})}
    </div>

    <div className="plan-comparison-wrap boost-comparison-wrap"><div className="comparison-head"><h3>Tabela de comparação</h3><p>O Grátis não recebe recursos de destaque. Plus e Premium aumentam a exposição.</p></div><div className="plan-comparison-table-wrap"><table className="plan-comparison-table"><thead><tr><th>Recursos</th><th className="basic">Grátis</th><th className="plus">Plus</th><th className="premium">Premium</th></tr></thead><tbody><tr><td>Limite de anúncios cadastrados</td>{plans.map(plan=><td key={plan.code}><span className="table-text">Até {plan.ad_limit||1}</span></td>)}</tr>{rows.map(row=><tr key={row.label}><td>{row.label}</td>{row.values.map((value,i)=><td key={i}>{renderCell(value)}</td>)}</tr>)}</tbody></table></div></div>
  </> : <div className={`checkout-card pagbank-checkout ${order.status==='paid'?'paid':''}`}>
    <h2>{order.status==='paid'?'Pagamento confirmado':order.status==='failed'?'Pagamento recusado':order.status==='cancelled'?'Pagamento cancelado':'Pague com PIX'}</h2>
    <p>Valor: <b>{money(order.amount)}</b></p>
    <p>Provedor: <b>PagBank</b></p>
    {order.status==='pending'&&<>
      {qrImage&&<img className="pagbank-qr-image" src={qrImage} alt="QR Code PIX PagBank"/>}
      {order.pix_code&&<div className="pix-copy-area"><code>{order.pix_code}</code><button type="button" className="secondary-btn" onClick={copyPix}><Copy/>{copied?'Copiado':'Copiar PIX'}</button></div>}
      <div className="pagbank-waiting"><span className="payment-pulse"></span> Aguardando confirmação do PagBank...</div>
      <small>Depois de pagar, esta tela atualiza automaticamente. O QR Code expira conforme a validade informada pelo PagBank.</small>
    </>}
    {order.status==='paid'&&<><div className="success-box"><Check/> Pagamento confirmado. Destaque ativado.</div><Link className="primary wide" to={`/produto/${id}`}>Voltar ao anúncio</Link></>}
    {['failed','cancelled'].includes(order.status)&&<button className="primary wide" onClick={()=>setOrder(null)}>Gerar novo PIX</button>}
  </div>}
 </div>
}

import React,{useEffect,useMemo,useState} from 'react';
import {Check, CreditCard, Crown, QrCode, Sparkles, Zap} from 'lucide-react';
import {Link,useParams} from 'react-router-dom';
import {api} from '../lib/api';
const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function Boost(){
 const {id}=useParams();
 const [plans,setPlans]=useState([]);
 const [p,setP]=useState(null);
 const [order,setOrder]=useState(null);
 const [busy,setBusy]=useState(false);
 const [method,setMethod]=useState('pix');
 useEffect(()=>{api('/api/plans').then(setPlans);api(`/api/products/${id}`).then(setP)},[id]);
 const buy=async code=>{setBusy(true);try{const o=await api('/api/payments',{method:'POST',body:JSON.stringify({product_id:id,plan_code:code,method})});setOrder(o)}finally{setBusy(false)}};
 const confirm=async()=>{setBusy(true);try{await api(`/api/payments/${order.id}/demo-confirm`,{method:'POST'});setOrder({...order,status:'paid'});const updated=await api(`/api/products/${id}`);setP(updated)}finally{setBusy(false)}};
 const featuredIndex=useMemo(()=>plans.length>1?1:0,[plans]);

 return <div className="page boost-page">
  <div className="boost-hero-card">
    <div>
      <span className="section-kicker">MONETIZAÇÃO</span>
      <h1>Impulsione seu anúncio</h1>
      <p>Ganhe mais visualizações, prioridade nas listagens e destaque visual para vender mais rápido.</p>
      <div className="boost-hero-benefits">
        <span><Zap size={16}/> Mais cliques</span>
        <span><Sparkles size={16}/> Mais destaque</span>
        <span><Crown size={16}/> Mais prioridade</span>
      </div>
    </div>
    {p&&<div className="boost-product boost-product-premium"><Sparkles/><div><b>{p.title}</b><span>{p.featured_active?'Este anúncio já possui destaque ativo.':'Escolha um plano para aumentar a exposição do seu anúncio.'}</span></div></div>}
  </div>

  {!order ? <>
    <div className="payment-methods">
      <button className={method==='pix'?'selected':''} onClick={()=>setMethod('pix')}><QrCode/> PIX</button>
      <button className={method==='card'?'selected':''} onClick={()=>setMethod('card')}><CreditCard/> Cartão</button>
    </div>

    <div className="plan-grid premium-plan-grid">
      {plans.map((plan, index)=><div className={`plan-card ${index===featuredIndex?'plan-card-featured':''}`} key={plan.code}>
        {index===featuredIndex && <span className="plan-ribbon">Mais escolhido</span>}
        <span className="plan-name">{plan.name}</span>
        <b>{money(plan.amount)}</b>
        <p className="plan-copy">Seu anúncio fica mais visível, com prioridade e selo especial.</p>
        <ul>
          <li><Check/> prioridade nas buscas</li>
          <li><Check/> selo de destaque</li>
          <li><Check/> melhor posição no catálogo</li>
        </ul>
        <button className="primary wide" disabled={busy} onClick={()=>buy(plan.code)}>Escolher plano</button>
      </div>)}
    </div>
  </> : <div className="checkout-card"><h2>{order.status==='paid'?'Pagamento confirmado':'Pedido criado'}</h2><p>Valor: <b>{money(order.amount)}</b></p><p>Forma: <b>{order.method==='pix'?'PIX':'Cartão'}</b></p>{order.pix_code&&<div className="pix-box"><QrCode/><code>{order.pix_code}</code></div>}{order.status!=='paid'?<><div className="demo-warning">Modo de demonstração: em produção esta etapa será confirmada automaticamente pelo gateway de pagamento.</div><button className="primary wide" disabled={busy} onClick={confirm}>Simular pagamento aprovado</button></>:<><div className="success-box"><Check/> Destaque ativado com sucesso.</div><Link className="primary wide" to={`/produto/${id}`}>Voltar ao anúncio</Link></>}</div>}
 </div>
}

import React,{useEffect,useState} from 'react';
import {Check, CreditCard, Crown, QrCode, Sparkles, Zap, X} from 'lucide-react';
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
function tierClass(index,total){
  if(index===0) return 'basic';
  if(index===total-1) return 'premium';
  return 'plus';
}
function renderCell(value){
  if(value===true) return <span className="table-yes"><Check size={15}/> Sim</span>;
  if(value===false) return <span className="table-no"><X size={15}/> Não</span>;
  return <span className="table-text">{value}</span>;
}

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

 return <div className="page boost-page">
  <div className="boost-hero-card">
    <div>
      <span className="section-kicker">MONETIZAÇÃO</span>
      <h1>Impulsione seu anúncio</h1>
      <p>O plano Grátis mantém seu anúncio publicado normalmente, mas sem prioridade ou destaque. Plus e Premium aumentam a exposição e a posição do anúncio.</p>
      <div className="boost-hero-benefits">
        <span><Zap size={16}/> Mais cliques</span>
        <span><Sparkles size={16}/> Mais destaque</span>
        <span><Crown size={16}/> Mais prioridade</span>
      </div>
    </div>
    {p&&<div className="boost-product boost-product-premium"><Sparkles/><div><b>{p.title}</b><span>{p.featured_active?'Este anúncio já possui destaque ativo.':'Escolha Plus ou Premium para aumentar a exposição do anúncio.'}</span></div></div>}
  </div>

  {!order ? <>
    <div className="payment-methods">
      <button className={method==='pix'?'selected':''} onClick={()=>setMethod('pix')}><QrCode/> PIX</button>
      <button className={method==='card'?'selected':''} onClick={()=>setMethod('card')}><CreditCard/> Cartão</button>
    </div>
    <div className="provider-installment-note">
      <b>Forma de pagamento usada somente em Plus e Premium.</b>{' '}
      {method==='pix'
        ? <>PIX é à vista em 1x.</>
        : <>As opções de parcelamento serão carregadas diretamente do gateway/banco quando a integração real estiver ativa.</>}
    </div>

    <div className="plan-grid premium-plan-grid colorful-plans-grid">
      {plans.map((plan, index)=>{
        const tier=tierClass(index, plans.length);
        return <div className={`plan-card ${tier} ${tier==='premium'?'plan-card-featured':''}`} key={plan.code}>
          <div className="plan-top-badges">
            <span className="plan-name">{tier==='basic'?'Grátis':tier==='plus'?'Plus':'Premium'}</span>
            {tier==='plus' && <span className="plan-chip sold">Mais vendido</span>}
            {tier==='plus' && <span className="plan-chip value">Melhor custo-benefício</span>}
            {tier==='premium' && <span className="plan-chip premium-chip">Mais vantagens</span>}
          </div>
          <b>{plan.free?'Grátis':money(plan.amount)}</b>
          <p className="plan-copy">{plan.tagline||'Escolha o nível de exposição do seu anúncio.'}</p>
          {(plan.features||[]).length>0 && <ul>
            {(plan.features||[]).map((feature)=><li key={feature}><Check/> {feature}</li>)}
          </ul>}
          {(plan.limitations||[]).length>0 && <ul className="plan-limit-list">
            {(plan.limitations||[]).map((item)=><li key={item}><X/> {item}</li>)}
          </ul>}
          {plan.free
            ? <Link className="plan-free-btn wide" to={`/produto/${id}`}>Continuar no Grátis</Link>
            : <button className="primary wide" disabled={busy} onClick={()=>buy(plan.code)}>Escolher plano</button>}
        </div>
      })}
    </div>

    <div className="plan-comparison-wrap boost-comparison-wrap">
      <div className="comparison-head">
        <h3>Tabela de comparação</h3>
        <p>O Grátis não recebe recursos de destaque. Plus e Premium aumentam a exposição.</p>
      </div>
      <div className="plan-comparison-table-wrap">
        <table className="plan-comparison-table">
          <thead>
            <tr>
              <th>Recursos</th>
              <th className="basic">Grátis</th>
              <th className="plus">Plus</th>
              <th className="premium">Premium</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row)=><tr key={row.label}>
              <td>{row.label}</td>
              {row.values.map((value, i)=><td key={i}>{renderCell(value)}</td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>
  </> : <div className="checkout-card"><h2>{order.status==='paid'?'Pagamento confirmado':'Pedido criado'}</h2><p>Valor: <b>{money(order.amount)}</b></p><p>Forma: <b>{order.method==='pix'?'PIX':'Cartão'}</b></p><p>Parcelamento: <b>{order.installments?`${order.installments}x`:order.provider_installment_message||'Definido pelo gateway/banco'}</b></p>{order.pix_code&&<div className="pix-box"><QrCode/><code>{order.pix_code}</code></div>}{order.status!=='paid'?<><div className="demo-warning">Modo de demonstração: em produção esta etapa será confirmada automaticamente pelo gateway de pagamento.</div><button className="primary wide" disabled={busy} onClick={confirm}>Simular pagamento aprovado</button></>:<><div className="success-box"><Check/> Destaque ativado com sucesso.</div><Link className="primary wide" to={`/produto/${id}`}>Voltar ao anúncio</Link></>}</div>}
 </div>
}

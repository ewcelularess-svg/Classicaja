import React,{useEffect,useState} from 'react';
import {AlertTriangle, ArrowUpCircle, Check, Clock3, Crown, Eye, Heart, History, MessageCircle, PackageCheck, PackageOpen, PlusCircle, QrCode, RefreshCw, Sparkles, XCircle} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api} from '../lib/api';

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const planTone=(code)=>code==='boost_7'?'basic':code==='boost_15'?'plus':'premium';
const formatDate=(value)=>{
  if(!value) return '—';
  try{return new Date(value).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'})}catch{return value}
};
const statusLabel=(status)=>({paid:'Pago',pending:'Pendente',cancelled:'Cancelado',failed:'Falhou'}[status]||status);

export default function Dashboard(){
 const [s,setS]=useState(null);
 const [plans,setPlans]=useState([]);
 const [payments,setPayments]=useState([]);
 const [err,setErr]=useState('');
 const [busyCancel,setBusyCancel]=useState('');
 const [busyRenew,setBusyRenew]=useState('');
 const [renewOrder,setRenewOrder]=useState(null);
 const [confirming,setConfirming]=useState(false);

 const load=()=>Promise.all([api('/api/me/dashboard'),api('/api/plans'),api('/api/me/payments')])
  .then(([dashboard, planList, history])=>{setS(dashboard);setPlans(planList);setPayments(history||[])})
  .catch(e=>setErr(e.message));
 useEffect(()=>{load()},[]);

 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;
 if(!s) return <div className="loading">Carregando painel...</div>;

 const cards=[
  ['Anúncios',s.total,<PackageOpen/>],['Ativos',s.active,<PackageCheck/>],['Visualizações',s.views,<Eye/>],['Favoritos recebidos',s.favorites_received,<Heart/>],['Mensagens não lidas',s.unread_messages,<MessageCircle/>]
 ];
 const summary=s.plan_summary||{};
 const featuredAds=summary.featured_ads||[];
 const expiringAds=featuredAds.filter(item=>item.expiring_soon);

 const cancelFeature=async(productId)=>{
   if(!confirm('Deseja cancelar o destaque deste anúncio?')) return;
   setBusyCancel(productId);
   try{await api(`/api/products/${productId}/cancel-feature`,{method:'POST'}); await load();}
   catch(e){alert(e.message)}
   finally{setBusyCancel('')}
 };

 const quickRenew=async(item)=>{
   setBusyRenew(item.id);
   try{
     const order=await api(`/api/products/${item.id}/renew-feature`,{method:'POST',body:JSON.stringify({method:'pix'})});
     setRenewOrder({...order,product_id:item.id,product_title:item.title});
     await load();
   }catch(e){alert(e.message)}
   finally{setBusyRenew('')}
 };

 const confirmDemoRenew=async()=>{
   if(!renewOrder?.id) return;
   setConfirming(true);
   try{
     await api(`/api/payments/${renewOrder.id}/demo-confirm`,{method:'POST'});
     setRenewOrder({...renewOrder,status:'paid'});
     await load();
   }catch(e){alert(e.message)}
   finally{setConfirming(false)}
 };

 return <div className="page"><div className="section-head"><div><span className="section-kicker">ÁREA DO VENDEDOR</span><h1>Visão geral</h1></div><Link className="primary small" to="/publicar"><PlusCircle/> Novo anúncio</Link></div>
  <div className="metric-grid">{cards.map(([label,value,icon])=><div className="metric-card" key={label}><span className="metric-icon">{icon}</span><div><b>{value}</b><small>{label}</small></div></div>)}</div>
  <div className="dashboard-actions"><Link to="/meus-anuncios"><b>Gerenciar anúncios</b><span>Edite status, exclua ou coloque em destaque.</span></Link><Link to="/mensagens"><b>Abrir mensagens</b><span>Converse com compradores e vendedores.</span></Link><Link to="/favoritos"><b>Ver favoritos</b><span>Acesse os produtos que você salvou.</span></Link></div>

  {expiringAds.length>0 && <div className="plan-expiry-alert">
    <AlertTriangle/>
    <div>
      <b>{expiringAds.length===1?'Seu plano está perto de vencer':'Você tem planos perto de vencer'}</b>
      <span>{expiringAds.map(item=>`${item.title} (${item.days_left ?? 0} dia${item.days_left===1?'':'s'})`).join(' • ')}</span>
    </div>
  </div>}

  <section className="dashboard-plan-section">
    <div className="section-head small-head">
      <div>
        <span className="section-kicker">MEU PLANO</span>
        <h2>Gerencie seu destaque</h2>
        <p className="section-desc">Veja seu plano atual, renove rapidamente, migre para um melhor ou cancele o destaque.</p>
      </div>
    </div>

    <div className="dashboard-plan-summary">
      <div className="plan-summary-card current">
        <div className="plan-summary-top">
          <span className="summary-icon"><Crown/></span>
          <div>
            <small>Plano atual</small>
            <h3>{summary.current_plan_name || 'Sem plano ativo'}</h3>
          </div>
        </div>
        <div className="summary-points">
          <span><b>{summary.featured_count || 0}</b> anúncio(s) em destaque</span>
          <span>Próximo vencimento: <b>{formatDate(summary.next_expiration)}</b></span>
          {summary.expiring_soon_count>0 && <span className="expiry-inline"><Clock3 size={15}/> {summary.expiring_soon_count} plano(s) vencendo em até 3 dias</span>}
        </div>
        <div className="summary-actions">
          <Link className="secondary-btn" to="/meus-anuncios">Administrar plano</Link>
          {summary.current_plan_code==='boost_30' && featuredAds[0] ?
            <button className="primary" onClick={()=>quickRenew(featuredAds[0])} disabled={busyRenew===featuredAds[0].id}><RefreshCw/>{busyRenew===featuredAds[0].id?'Gerando...':'Renovar Premium'}</button>
            : summary.current_plan_code ?
              <Link className="primary" to={featuredAds[0]?`/destaque/${featuredAds[0].id}`:'/meus-anuncios'}><ArrowUpCircle/> Migrar para melhor</Link>
              : <Link className="primary" to="/meus-anuncios"><Sparkles/> Escolher plano</Link>}
        </div>
      </div>

      <div className="plan-summary-card compare">
        <div className="plan-mini-grid">
          {plans.map(plan=><div className={`plan-mini-card ${planTone(plan.code)}`} key={plan.code}>
            <span className="mini-name">{plan.code==='boost_7'?'Básico':plan.code==='boost_15'?'Plus':'Premium'}</span>
            <b>{money(plan.amount)}</b>
            <small>{plan.days} dias • boost {plan.boost}</small>
          </div>)}
        </div>
      </div>
    </div>

    {renewOrder && <div className={`quick-renew-checkout ${renewOrder.status==='paid'?'paid':''}`}>
      <div className="quick-renew-title"><QrCode/><div><b>{renewOrder.status==='paid'?'Renovação confirmada':'Cobrança de renovação criada'}</b><span>{renewOrder.product_title} • {renewOrder.plan_name}</span></div></div>
      <div className="quick-renew-body">
        <span>Valor: <b>{money(renewOrder.amount)}</b></span>
        <span>Forma: <b>PIX • 1x</b></span>
        {renewOrder.pix_code&&renewOrder.status!=='paid'&&<code>{renewOrder.pix_code}</code>}
      </div>
      {renewOrder.status!=='paid' ? <button className="primary" onClick={confirmDemoRenew} disabled={confirming}><Check/>{confirming?'Confirmando...':'Simular pagamento aprovado'}</button> : <span className="renew-success"><Check/> Plano renovado</span>}
      <small>No gateway real, este mesmo botão criará a cobrança PIX verdadeira e a confirmação virá pelo webhook do banco/gateway.</small>
    </div>}

    {featuredAds.length>0 ? <div className="featured-plan-list">
      {featuredAds.map(item=><div className={`featured-plan-item ${item.expiring_soon?'expiring':''}`} key={item.id}>
        <div>
          <b>{item.title}</b>
          <small>{item.plan_name || 'Plano ativo'} • vence em {formatDate(item.featured_until)} {item.days_left!==null&&item.days_left!==undefined?`• ${item.days_left} dia(s) restante(s)`:''}</small>
        </div>
        <div className="featured-plan-actions">
          <button className="renew-btn" onClick={()=>quickRenew(item)} disabled={busyRenew===item.id}><RefreshCw/>{busyRenew===item.id?'Gerando...':item.plan_code==='boost_30'?'Renovar Premium':'Renovar 1 clique'}</button>
          {item.plan_code!=='boost_30' && <Link className="secondary-btn" to={`/destaque/${item.id}`}><Sparkles/> Migrar</Link>}
          <button className="danger-lite-btn" onClick={()=>cancelFeature(item.id)} disabled={busyCancel===item.id}><XCircle/>{busyCancel===item.id?'Cancelando...':'Cancelar'}</button>
        </div>
      </div>)}
    </div> : <div className="empty empty-plan-box"><h3>Você ainda não ativou nenhum plano de destaque.</h3><p>Escolha um dos planos para dar mais visibilidade aos seus anúncios.</p><Link className="primary" to="/meus-anuncios"><Sparkles/> Escolher plano</Link></div>}
  </section>

  <section className="payment-history-section">
    <div className="section-head small-head">
      <div><span className="section-kicker">PAGAMENTOS</span><h2>Histórico de pagamentos</h2><p className="section-desc">Acompanhe pagamentos, forma utilizada, parcelas e status.</p></div>
      <History/>
    </div>
    {payments.length ? <div className="payment-history-table-wrap"><table className="payment-history-table">
      <thead><tr><th>Data</th><th>Anúncio</th><th>Plano</th><th>Forma</th><th>Parcelas</th><th>Valor</th><th>Status</th></tr></thead>
      <tbody>{payments.map(row=><tr key={row.id}><td>{formatDate(row.paid_at||row.created_at)}</td><td>{row.product_title||'—'}</td><td>{row.plan_name||row.plan_code}</td><td>{row.method==='pix'?'PIX':'Cartão'}</td><td>{row.installment_label||'—'}</td><td>{money(row.amount)}</td><td><span className={`payment-status ${row.status}`}>{statusLabel(row.status)}</span></td></tr>)}</tbody>
    </table></div> : <div className="empty payment-empty"><h3>Nenhum pagamento registrado ainda.</h3></div>}
  </section>
 </div>
}

import React,{useEffect,useState} from 'react';
import {AlertTriangle, ArrowUpCircle, Check, Clock3, Copy, Crown, Eye, Heart, History, ImagePlus, Link2, MessageCircle, PackageCheck, PackageOpen, PlusCircle, QrCode, RefreshCw, Sparkles, Trash2, Handshake, XCircle} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';

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
 const [renewQr,setRenewQr]=useState('');
 const [partner,setPartner]=useState(null);
 const [partnerForm,setPartnerForm]=useState({company_name:'',title:'',subtitle:'',target_url:'',image_url:''});
 const [partnerFile,setPartnerFile]=useState(null);
 const [partnerPreview,setPartnerPreview]=useState('');
 const [partnerBusy,setPartnerBusy]=useState(false);

 const load=()=>Promise.all([api('/api/me/dashboard'),api('/api/plans'),api('/api/me/payments'),api('/api/me/partner-benefit')])
  .then(([dashboard, planList, history, partnerData])=>{setS(dashboard);setPlans(planList);setPayments(history||[]);setPartner(partnerData)})
  .catch(e=>setErr(e.message));
 useEffect(()=>{load()},[]);
 useEffect(()=>{
   if(!renewOrder?.id || renewOrder.status==='paid') return;
   const timer=setInterval(async()=>{
     try{
       const status=await api(`/api/payments/${renewOrder.id}/status`);
       if(status.status==='paid'){
         setRenewOrder(prev=>({...prev,status:'paid'}));
         clearInterval(timer);
         load();
       }else if(['failed','cancelled'].includes(status.status)){
         setRenewOrder(prev=>({...prev,status:status.status}));
         clearInterval(timer);
       }
     }catch{}
   },5000);
   return()=>clearInterval(timer);
 },[renewOrder?.id,renewOrder?.status]);

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
   const taxId=(prompt('Digite seu CPF ou CNPJ para gerar o PIX PagBank:')||'').replace(/\D/g,'');
   if(![11,14].includes(taxId.length)){alert('Informe um CPF ou CNPJ válido.');return}
   setBusyRenew(item.id);
   try{
     const order=await api(`/api/products/${item.id}/renew-feature`,{method:'POST',body:JSON.stringify({method:'pix',tax_id:taxId})});
     setRenewOrder({...order,product_id:item.id,product_title:item.title});
     setRenewQr('');
     if(order.qr_image_available){api(`/api/payments/${order.id}/qrcode`).then(r=>setRenewQr(r.data_url||'')).catch(()=>{})}
   }catch(e){alert(e.message)}
   finally{setBusyRenew('')}
 };

 const copyRenewPix=async()=>{
   if(!renewOrder?.pix_code)return;
   await navigator.clipboard.writeText(renewOrder.pix_code);
 };

 const onPartnerImage=(e)=>{
   const file=e.target.files?.[0]||null;
   setPartnerFile(file);
   setPartnerPreview(file?URL.createObjectURL(file):'');
 };

 const submitPartner=async(e)=>{
   e.preventDefault();
   if(!partner?.eligible || partner.remaining<=0) return;
   setPartnerBusy(true);
   try{
     let imageUrl=(partnerForm.image_url||'').trim();
     if(partnerFile){
       const fd=new FormData();
       fd.append('image',partnerFile);
       const uploaded=await api('/api/me/partner-ads/image',{method:'POST',body:fd});
       imageUrl=uploaded.image_url;
     }
     if(!imageUrl){alert('Selecione uma imagem ou informe a URL da imagem.');return}
     await api('/api/me/partner-ads',{method:'POST',body:JSON.stringify({...partnerForm,image_url:imageUrl})});
     setPartnerForm({company_name:'',title:'',subtitle:'',target_url:'',image_url:''});
     setPartnerFile(null);
     setPartnerPreview('');
     await load();
   }catch(e){alert(e.message)}finally{setPartnerBusy(false)}
 };

 const endPartner=async(id)=>{
   if(!confirm('Encerrar esta campanha de parceria? O uso do mês continuará contabilizado.')) return;
   try{await api(`/api/me/partner-ads/${id}`,{method:'DELETE'});await load()}catch(e){alert(e.message)}
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
            : summary.current_plan_code==='boost_7' ?
              <Link className="primary" to="/meus-anuncios"><ArrowUpCircle/> Fazer upgrade</Link>
            : summary.current_plan_code ?
              <Link className="primary" to={featuredAds[0]?`/destaque/${featuredAds[0].id}`:'/meus-anuncios'}><ArrowUpCircle/> Migrar para melhor</Link>
              : <Link className="primary" to="/meus-anuncios"><Sparkles/> Escolher plano</Link>}
        </div>
      </div>

      <div className="plan-summary-card compare">
        <div className="plan-mini-grid">
          {plans.map(plan=><div className={`plan-mini-card ${planTone(plan.code)}`} key={plan.code}>
            <span className="mini-name">{plan.code==='boost_7'?'Grátis':plan.code==='boost_15'?'Plus':'Premium'}</span>
            <b>{plan.free?'Grátis':money(plan.amount)}</b>
            <small>{plan.free?'Publicação padrão • sem destaque':`${plan.days} dias • boost ${plan.boost}`}</small>
          </div>)}
        </div>
      </div>
    </div>

    {renewOrder && <div className={`quick-renew-checkout ${renewOrder.status==='paid'?'paid':''}`}>
      <div className="quick-renew-title"><QrCode/><div><b>{renewOrder.status==='paid'?'Renovação confirmada':'PIX PagBank gerado'}</b><span>{renewOrder.product_title} • {renewOrder.plan_name}</span></div></div>
      <div className="quick-renew-body">
        <span>Valor: <b>{money(renewOrder.amount)}</b></span>
        <span>Forma: <b>PIX PagBank • 1x</b></span>
        {renewQr&&renewOrder.status!=='paid'&&<img className="renew-qr-image" src={renewQr} alt="QR Code PIX"/>}
        {renewOrder.pix_code&&renewOrder.status!=='paid'&&<><code>{renewOrder.pix_code}</code><button className="secondary-btn" onClick={copyRenewPix}><Copy/> Copiar PIX</button></>}
      </div>
      {renewOrder.status==='paid' ? <span className="renew-success"><Check/> Plano renovado</span> : <small>Aguardando confirmação automática do PagBank.</small>}
    </div>}

    {featuredAds.length>0 ? <div className="featured-plan-list">
      {featuredAds.map(item=><div className={`featured-plan-item ${item.expiring_soon?'expiring':''}`} key={item.id}>
        <div>
          <b>{item.title}</b>
          <small>{item.plan_name || 'Plano ativo'} • vence em {formatDate(item.featured_until)} {item.days_left!==null&&item.days_left!==undefined?`• ${item.days_left} dia(s) restante(s)`:''}</small>
        </div>
        <div className="featured-plan-actions">
          {item.plan_code!=='legacy_basic' && <button className="renew-btn" onClick={()=>quickRenew(item)} disabled={busyRenew===item.id}><RefreshCw/>{busyRenew===item.id?'Gerando...':item.plan_code==='boost_30'?'Renovar Premium':'Renovar 1 clique'}</button>}
          {item.plan_code!=='boost_30' && <Link className="secondary-btn" to={`/destaque/${item.id}`}><Sparkles/> {item.plan_code==='legacy_basic'?'Migrar para Plus':'Migrar'}</Link>}
          <button className="danger-lite-btn" onClick={()=>cancelFeature(item.id)} disabled={busyCancel===item.id}><XCircle/>{busyCancel===item.id?'Cancelando...':'Cancelar'}</button>
        </div>
      </div>)}
    </div> : <div className="empty empty-plan-box"><h3>Você ainda não ativou nenhum plano de destaque.</h3><p>Escolha um dos planos para dar mais visibilidade aos seus anúncios.</p><Link className="primary" to="/meus-anuncios"><Sparkles/> Escolher plano</Link></div>}
  </section>

  <section className="my-partner-section">
    <div className="section-head small-head">
      <div><span className="section-kicker">MINHA PARCERIA</span><h2>Divulgue sua marca no ClassificaJá</h2><p className="section-desc">Benefício controlado pelo plano para dar visibilidade sem poluir o marketplace.</p></div>
      <Handshake/>
    </div>

    {partner?.eligible ? <div className={`my-partner-panel tier-${partner.tier}`}>
      <div className="partner-benefit-summary">
        <div><small>Seu benefício</small><h3>Parceria {partner.plan_name}</h3><p>Sua campanha aparece somente nos espaços permitidos pelo plano e expira junto com o benefício ativo.</p></div>
        <div className="partner-usage"><b>{partner.used_this_month}/{partner.monthly_limit}</b><span>publicação(ões) usadas neste mês</span><em>{partner.remaining} restante(s)</em></div>
      </div>
      <div className="partner-slot-list">{(partner.slots||[]).map(slot=><span key={slot.code}><Check size={14}/>{slot.label}</span>)}</div>

      <form className="my-partner-form" onSubmit={submitPartner}>
        <div className="two-cols">
          <label>Empresa / marca<input value={partnerForm.company_name} onChange={e=>setPartnerForm({...partnerForm,company_name:e.target.value})} placeholder="Nome da sua marca" required/></label>
          <label>Título da parceria<input value={partnerForm.title} onChange={e=>setPartnerForm({...partnerForm,title:e.target.value})} placeholder="Ex.: Oferta especial para clientes ClassificaJá" required/></label>
        </div>
        <label>Descrição curta<input value={partnerForm.subtitle} onChange={e=>setPartnerForm({...partnerForm,subtitle:e.target.value})} placeholder="Mensagem curta da campanha"/></label>
        <div className="two-cols">
          <label>Link de destino<div className="partner-field-icon"><Link2/><input value={partnerForm.target_url} onChange={e=>setPartnerForm({...partnerForm,target_url:e.target.value})} placeholder="https://seusite.com.br"/></div></label>
          <label>URL da imagem (opcional)<input value={partnerForm.image_url} onChange={e=>setPartnerForm({...partnerForm,image_url:e.target.value})} placeholder="https://.../banner.jpg"/></label>
        </div>
        <div className="partner-upload-row">
          <label className="partner-user-upload"><ImagePlus/><span>{partnerFile?'Imagem selecionada':'Selecionar imagem do celular/computador'}</span><input type="file" accept="image/*" onChange={onPartnerImage}/></label>
          {(partnerPreview||partnerForm.image_url)&&<div className="partner-user-preview"><img src={partnerPreview||partnerForm.image_url} alt="Prévia da parceria"/></div>}
          <button className="primary" disabled={partnerBusy||partner.remaining<=0}>{partnerBusy?'Publicando...':'Publicar parceria'}</button>
        </div>
        {partner.remaining<=0&&<div className="partner-limit-note"><AlertTriangle/> Você atingiu o limite deste mês. O contador reinicia no próximo mês; encerrar uma campanha não devolve a cota.</div>}
      </form>

      {(partner.ads||[]).length>0&&<div className="my-partner-list">
        {(partner.ads||[]).map(ad=><div className="my-partner-item" key={ad.id}>
          <div className="my-partner-thumb">{ad.image_url?<img src={imageUrl(ad.image_url)} alt={ad.company_name}/>:<Handshake/>}</div>
          <div><b>{ad.company_name}</b><span>{ad.title}</span><small>{ad.active?'Ativa':'Encerrada'}{ad.expires_at?` • expira em ${formatDate(ad.expires_at)}`:''}</small></div>
          {ad.active?<button className="danger-lite-btn" onClick={()=>endPartner(ad.id)}><Trash2/> Encerrar</button>:<span className="partner-ended">Encerrada</span>}
        </div>)}
      </div>}
    </div> : <div className="partner-benefit-locked">
      <span className="summary-icon"><Handshake/></span>
      <div><h3>Parcerias disponíveis no Plus e Premium</h3><p>O plano Grátis não inclui publicidade de parceria. Faça upgrade para liberar espaços controlados de divulgação.</p></div>
      <Link className="primary" to="/meus-anuncios"><ArrowUpCircle/> Ver planos</Link>
    </div>}
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

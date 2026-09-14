import React,{useEffect,useMemo,useState} from 'react';
import {
  BadgeCheck, Ban, CheckCircle2, CircleDollarSign, Crown, Eye, Flag, LayoutDashboard,
  KeyRound, Landmark, LockKeyhole, PackageOpen, PlugZap, Search, ShieldCheck, Trash2, UserCog, Users, WalletCards, XCircle
} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api} from '../lib/api';

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const date=v=>v?new Date(v).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'}):'—';
const statusLabel=s=>({active:'Ativo',blocked:'Bloqueado',paused:'Pausado',rejected:'Rejeitado',sold:'Vendido',open:'Aberta',resolved:'Resolvida',paid:'Pago',pending:'Pendente',cancelled:'Cancelado'}[s]||s);

function PlanEditor({plan,onSaved}){
  const [form,setForm]=useState(()=>({
    name:plan.name||'', amount:plan.amount??0, days:plan.days??0, active:Boolean(plan.active),
    badge:plan.badge||'', tagline:plan.tagline||'', features:(plan.features||[]).join('\n'), limitations:(plan.limitations||[]).join('\n')
  }));
  const [busy,setBusy]=useState(false);
  const save=async()=>{
    setBusy(true);
    try{
      const payload={
        ...form,
        amount:Number(form.amount||0),
        days:Number(form.days||0),
        features:String(form.features||'').split('\n').map(x=>x.trim()).filter(Boolean),
        limitations:String(form.limitations||'').split('\n').map(x=>x.trim()).filter(Boolean),
      };
      await api(`/api/admin/plans/${plan.code}`,{method:'PUT',body:JSON.stringify(payload)});
      onSaved();
    }catch(e){alert(e.message)}finally{setBusy(false)}
  };
  const tone=plan.free?'free':plan.boost>=3?'premium':'plus';
  return <article className={`master-plan-card ${tone}`}>
    <div className="master-plan-head"><div><span>{plan.free?'GRÁTIS':plan.boost>=3?'PREMIUM':'PLUS'}</span><h3>{plan.name}</h3></div><label className="master-switch"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/><i/></label></div>
    <div className="master-form-grid">
      <label>Nome<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
      <label>Preço (R$)<input type="number" min="0" step="0.01" value={form.amount} disabled={plan.free} onChange={e=>setForm({...form,amount:e.target.value})}/></label>
      <label>Duração (dias)<input type="number" min="0" value={form.days} onChange={e=>setForm({...form,days:e.target.value})}/><small className="field-help">Defina livremente a duração do plano grátis.</small></label>
      <label>Selo<input value={form.badge} onChange={e=>setForm({...form,badge:e.target.value})}/></label>
    </div>
    <label className="master-wide-label">Descrição<input value={form.tagline} onChange={e=>setForm({...form,tagline:e.target.value})}/></label>
    <div className="master-form-grid two">
      <label>Vantagens<textarea rows="5" value={form.features} onChange={e=>setForm({...form,features:e.target.value})} placeholder="Uma vantagem por linha"/></label>
      <label>Limitações<textarea rows="5" value={form.limitations} onChange={e=>setForm({...form,limitations:e.target.value})} placeholder="Uma limitação por linha"/></label>
    </div>
    <button className="primary wide" onClick={save} disabled={busy}>{busy?'Salvando...':'Salvar plano'}</button>
  </article>
}

function PaymentIntegrationCard({integration,onSaved}){
  const initialCredentials={};
  (integration.fields||[]).forEach(f=>{initialCredentials[f.key]=f.value||''});
  const [form,setForm]=useState({
    enabled:Boolean(integration.enabled),
    is_default:Boolean(integration.is_default),
    mode:integration.mode||'sandbox',
    credentials:initialCredentials,
  });
  const [busy,setBusy]=useState(false);
  const [testing,setTesting]=useState(false);
  const [testResult,setTestResult]=useState(null);
  const setCredential=(key,value)=>setForm({...form,credentials:{...form.credentials,[key]:value}});
  const save=async()=>{
    setBusy(true);
    setTestResult(null);
    try{
      await api(`/api/admin/payment-integrations/${integration.provider}`,{method:'PUT',body:JSON.stringify(form)});
      await onSaved();
    }catch(e){alert(e.message)}finally{setBusy(false)}
  };
  const testPagBank=async()=>{
    setTesting(true);
    setTestResult(null);
    try{
      const result=await api('/api/admin/payment-integrations/pagbank/test',{method:'POST'});
      setTestResult({ok:Boolean(result.ok),message:result.message||'Teste concluído.'});
    }catch(e){
      setTestResult({ok:false,message:e.message||'Falha ao testar PagBank.'});
    }finally{setTesting(false)}
  };
  return <article className={`pix-integration-card ${integration.enabled?'enabled':''} ${integration.is_default?'default':''}`}>
    <div className="pix-integration-head">
      <div className="pix-provider-icon"><Landmark/></div>
      <div className="pix-provider-title">
        <div className="pix-provider-status-row">
          <h3>{integration.label}</h3>
          {integration.is_default&&<span className="pix-main-badge">Principal</span>}
          <span className={`pix-config-badge ${integration.configured?'ok':'pending'}`}>{integration.configured?'Credenciais salvas':'Não configurado'}</span>
        </div>
        <p>{integration.description}</p>
      </div>
    </div>

    <div className="pix-integration-controls">
      <label className="pix-check-row"><input type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/><span>Ativar integração</span></label>
      <label className="pix-check-row"><input type="checkbox" checked={form.is_default} onChange={e=>setForm({...form,is_default:e.target.checked})}/><span>Usar como provedor principal</span></label>
      <label className="pix-mode-field">Ambiente<select value={form.mode} onChange={e=>setForm({...form,mode:e.target.value})}><option value="sandbox">Sandbox / Teste</option><option value="production">Produção / PIX real</option></select></label>
    </div>

    <div className="pix-credentials-grid">
      {(integration.fields||[]).map(field=><label key={field.key}>{field.label}
        <div className="pix-secret-input"><span>{field.secret?<LockKeyhole/>:<KeyRound/>}</span><input type={field.secret?'password':'text'} autoComplete="off" value={form.credentials[field.key]||''} onChange={e=>setCredential(field.key,e.target.value)} placeholder={field.configured?'Já configurado — deixe em branco para manter':'Cole a credencial aqui'}/></div>
        {field.configured&&<small>Credencial já armazenada com segurança.</small>}
      </label>)}
    </div>

    <div className="pix-webhook-box"><PlugZap/><div><b>Webhook do ClassificaJá</b><span>{integration.provider==='pagbank'?`${window.location.origin}/api/webhooks/pagbank`:`${window.location.origin}/api/payments/webhook/${integration.provider}`}</span><small>{integration.provider==='pagbank'?'O ClassificaJá envia este endereço automaticamente ao criar cada cobrança PIX PagBank.':'Use este endereço quando o conector real deste provedor for ativado.'}</small></div></div>
    {integration.provider==='pagbank'&&<div className="pix-live-note"><ShieldCheck/><span><b>Salvar credenciais não testa o token.</b> Depois de salvar, use o botão abaixo para validar a autenticação no mesmo ambiente selecionado. Para gerar PIX, a conta PagBank também precisa ter uma chave PIX ativa.</span></div>}

    {!integration.security_ready&&<div className="pix-security-warning"><LockKeyhole/><span>Configure <b>PAYMENT_CONFIG_KEY</b> no Render antes de salvar credenciais de produção.</span></div>}
    <button className="primary wide" onClick={save} disabled={busy}>{busy?'Salvando integração...':'Salvar integração PIX'}</button>
    {integration.provider==='pagbank'&&<>
      <button className="secondary-btn wide pix-test-button" onClick={testPagBank} disabled={testing||busy}>{testing?'Testando conexão...':'Testar conexão PagBank'}</button>
      {testResult&&<div className={`pix-test-result ${testResult.ok?'ok':'error'}`}><ShieldCheck/><span>{testResult.message}</span></div>}
    </>}
  </article>
}

export default function Admin(){
 const [stats,setStats]=useState(null);
 const [products,setProducts]=useState([]);
 const [users,setUsers]=useState([]);
 const [reports,setReports]=useState([]);
 const [plans,setPlans]=useState([]);
 const [payments,setPayments]=useState([]);
 const [integrations,setIntegrations]=useState([]);
 const [tab,setTab]=useState('overview');
 const [search,setSearch]=useState('');
 const [loading,setLoading]=useState(true);
 const [err,setErr]=useState('');

 const load=async()=>{
  setLoading(true); setErr('');
  try{
   const [s,p,u,r,pl,py,ix]=await Promise.all([
    api('/api/admin/stats'),api('/api/admin/products'),api('/api/admin/users'),api('/api/admin/reports'),api('/api/admin/plans'),api('/api/admin/payments'),api('/api/admin/payment-integrations')
   ]);
   setStats(s);setProducts(p);setUsers(u);setReports(r);setPlans(pl);setPayments(py);setIntegrations(ix);
  }catch(e){setErr(e.message)}finally{setLoading(false)}
 };
 useEffect(()=>{load()},[]);

 const q=search.trim().toLowerCase();
 const filteredProducts=useMemo(()=>!q?products:products.filter(p=>[p.title,p.city,p.state,p.seller_name,p.seller_email].some(v=>String(v||'').toLowerCase().includes(q))),[products,q]);
 const filteredUsers=useMemo(()=>!q?users:users.filter(u=>[u.name,u.email,u.phone,u.role,u.status].some(v=>String(v||'').toLowerCase().includes(q))),[users,q]);
 const filteredPayments=useMemo(()=>!q?payments:payments.filter(p=>[p.user_name,p.user_email,p.plan_name,p.product_title,p.status].some(v=>String(v||'').toLowerCase().includes(q))),[payments,q]);

 const setProductStatus=async(id,status)=>{try{await api(`/api/admin/products/${id}/status`,{method:'PUT',body:JSON.stringify({status})});load()}catch(e){alert(e.message)}};
 const deleteProduct=async p=>{if(!confirm(`Excluir definitivamente o anúncio “${p.title}”?`))return;try{await api(`/api/admin/products/${p.id}`,{method:'DELETE'});load()}catch(e){alert(e.message)}};
 const verify=async u=>{try{await api(`/api/admin/users/${u.id}/verify`,{method:'PUT',body:JSON.stringify({verified:!u.verified})});load()}catch(e){alert(e.message)}};
 const setUserStatus=async(u,status)=>{if(status==='blocked'&&!confirm(`Bloquear a conta de ${u.name}?`))return;try{await api(`/api/admin/users/${u.id}/status`,{method:'PUT',body:JSON.stringify({status})});load()}catch(e){alert(e.message)}};
 const deleteUser=async u=>{if(!confirm(`EXCLUIR definitivamente a conta de ${u.name}? Os anúncios e dados relacionados serão removidos.`))return;try{await api(`/api/admin/users/${u.id}`,{method:'DELETE'});load()}catch(e){alert(e.message)}};
 const resolve=async id=>{try{await api(`/api/admin/reports/${id}/resolve`,{method:'PUT'});load()}catch(e){alert(e.message)}};
 const cancelPayment=async p=>{if(!confirm('Cancelar este pagamento pendente?'))return;try{await api(`/api/admin/payments/${p.id}/cancel`,{method:'POST'});load()}catch(e){alert(e.message)}};

 if(loading&&!stats) return <div className="loading">Carregando Painel Master...</div>;
 if(err&&!stats) return <div className="page"><div className="empty"><h3>{err}</h3><button className="primary" onClick={load}>Tentar novamente</button></div></div>;

 const metricCards=[
  ['Contas',stats?.users,<Users/>],['Anúncios',stats?.products,<PackageOpen/>],['Visualizações',stats?.views,<Eye/>],['Destaques ativos',stats?.active_boosts,<Crown/>],['Receita',money(stats?.revenue),<WalletCards/>],['Denúncias',stats?.open_reports,<Flag/>]
 ];
 const tabs=[['overview','Visão geral',LayoutDashboard],['users','Contas',Users],['products','Anúncios',PackageOpen],['plans','Planos',Crown],['payments','Pagamentos',CircleDollarSign],['pix','Integrações PIX',Landmark],['reports','Denúncias',Flag]];

 return <div className="page master-admin-page">
  <div className="master-admin-header">
   <div><span className="section-kicker">PAINEL MASTER</span><h1>Central de comando do ClassificaJá</h1><p>Gerencie contas, anúncios, planos, pagamentos, PIX e moderação em um só lugar.</p></div>
   <div className="master-admin-badge"><ShieldCheck/> Master Admin</div>
  </div>

  <div className="master-admin-tabs">{tabs.map(([key,label,Icon])=><button key={key} className={tab===key?'active':''} onClick={()=>{setTab(key);setSearch('')}}><Icon/>{label}</button>)}</div>

  {['users','products','payments'].includes(tab)&&<div className="master-search"><Search/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder={tab==='users'?'Buscar nome, e-mail ou telefone':tab==='products'?'Buscar anúncio, vendedor ou cidade':'Buscar pagamento, usuário ou plano'}/></div>}

  {tab==='overview'&&<>
   <div className="metric-grid master-metrics">{metricCards.map(([label,value,icon])=><div className="metric-card" key={label}><span className="metric-icon">{icon}</span><div><b>{value??0}</b><small>{label}</small></div></div>)}</div>
   <div className="master-overview-grid">
    <section className="master-overview-card"><h3>Contas</h3><div className="master-stat-line"><span>Ativas</span><b>{stats?.active_users||0}</b></div><div className="master-stat-line"><span>Bloqueadas</span><b>{stats?.blocked_users||0}</b></div><div className="master-stat-line"><span>Administradores</span><b>{stats?.admins||0}</b></div><button onClick={()=>setTab('users')}>Gerenciar contas</button></section>
    <section className="master-overview-card"><h3>Anúncios</h3><div className="master-stat-line"><span>Ativos</span><b>{stats?.active_products||0}</b></div><div className="master-stat-line"><span>Pausados</span><b>{stats?.paused_products||0}</b></div><div className="master-stat-line"><span>Rejeitados</span><b>{stats?.rejected_products||0}</b></div><button onClick={()=>setTab('products')}>Gerenciar anúncios</button></section>
    <section className="master-overview-card"><h3>Financeiro</h3><div className="master-stat-line"><span>Pagos</span><b>{stats?.paid_payments||0}</b></div><div className="master-stat-line"><span>Pendentes</span><b>{stats?.pending_payments||0}</b></div><div className="master-stat-line"><span>Receita</span><b>{money(stats?.revenue)}</b></div><button onClick={()=>setTab('payments')}>Ver pagamentos</button></section>
   </div>
  </>}

  {tab==='users'&&<div className="master-table-wrap"><table className="master-table"><thead><tr><th>Conta</th><th>Tipo</th><th>Anúncios</th><th>Pagamentos</th><th>Status</th><th>Ações</th></tr></thead><tbody>{filteredUsers.map(u=><tr key={u.id}><td><b>{u.name}</b><small>{u.email}<br/>{u.phone||'Sem telefone'}</small></td><td><span className={`master-role-badge ${u.role==='admin'?'owner':''}`}>{u.role==='admin'?'Master proprietário':'Usuário'}</span></td><td>{u.ad_count}</td><td>{money(u.paid_total)}</td><td><span className={`master-status ${u.status}`}>{statusLabel(u.status)}</span></td><td><div className="master-actions"><button className={`verify-btn ${u.verified?'on':''}`} onClick={()=>verify(u)}><BadgeCheck/>{u.verified?'Verificado':'Verificar'}</button>{u.role!=='admin'&&(u.status==='active'?<button onClick={()=>setUserStatus(u,'blocked')}><Ban/>Bloquear</button>:<button onClick={()=>setUserStatus(u,'active')}><CheckCircle2/>Ativar</button>)}{u.role!=='admin'&&<button className="danger-lite-btn" onClick={()=>deleteUser(u)}><Trash2/>Excluir</button>}</div></td></tr>)}</tbody></table></div>}

  {tab==='products'&&<div className="master-table-wrap"><table className="master-table"><thead><tr><th>Anúncio</th><th>Vendedor</th><th>Local</th><th>Status</th><th>Destaque</th><th>Ações</th></tr></thead><tbody>{filteredProducts.map(p=><tr key={p.id}><td><Link to={`/produto/${p.id}`}><b>{p.title}</b></Link><small>{money(p.price)} • {p.views||0} visualizações</small></td><td><b>{p.seller_name||p.seller?.name||'—'}</b><small>{p.seller_email||''}</small></td><td>{p.city}/{p.state}</td><td><select value={p.status} onChange={e=>setProductStatus(p.id,e.target.value)}><option value="active">Ativo</option><option value="paused">Pausado</option><option value="rejected">Rejeitado</option><option value="sold">Vendido</option></select></td><td>{p.featured_active?<span className="master-status paid">Ativo</span>:<span className="master-status neutral">Normal</span>}</td><td><div className="master-actions"><Link className="master-link-btn" to={`/produto/${p.id}`}><Eye/>Abrir</Link><button className="danger-lite-btn" onClick={()=>deleteProduct(p)}><Trash2/>Excluir</button></div></td></tr>)}</tbody></table></div>}

  {tab==='plans'&&<div className="master-plans-grid">{plans.map(p=><PlanEditor key={p.code} plan={p} onSaved={load}/>)}</div>}

  {tab==='payments'&&<div className="master-table-wrap"><table className="master-table"><thead><tr><th>Cliente</th><th>Plano</th><th>Anúncio</th><th>Valor</th><th>Forma</th><th>Status</th><th>Data</th><th>Ação</th></tr></thead><tbody>{filteredPayments.map(p=><tr key={p.id}><td><b>{p.user_name||'Conta removida'}</b><small>{p.user_email||''}</small></td><td>{p.plan_name}</td><td>{p.product_title||'—'}</td><td><b>{money(p.amount)}</b></td><td>{p.method==='pix'?'PIX':p.method==='card'?'Cartão':p.method}</td><td><span className={`master-status ${p.status}`}>{statusLabel(p.status)}</span></td><td>{date(p.created_at)}</td><td>{p.status==='pending'?<button className="danger-lite-btn" onClick={()=>cancelPayment(p)}><XCircle/>Cancelar</button>:'—'}</td></tr>)}</tbody></table></div>}

  {tab==='pix'&&<section className="pix-master-section">
    <div className="pix-master-intro"><div><span className="section-kicker">RECEBIMENTO PIX</span><h2>Integrações de pagamento</h2><p>Cadastre e gerencie suas credenciais de pagamento diretamente no Master. As chaves privadas ficam criptografadas no backend e não são mostradas novamente.</p></div><div className="pix-security-pill"><ShieldCheck/> Credenciais protegidas</div></div>
    <div className="pix-provider-grid">{integrations.map(item=><PaymentIntegrationCard key={item.provider} integration={item} onSaved={load}/>)}</div>
    <div className="pix-master-note"><b>Importante:</b> no PagBank, o checkout PIX é exibido dentro do ClassificaJá em forma de QR Code e código Copia e Cola. Salvar o token não redireciona o navegador para o PagBank.</div>
  </section>}

  {tab==='reports'&&<div className="master-table-wrap"><table className="master-table"><thead><tr><th>Anúncio</th><th>Denunciante</th><th>Motivo</th><th>Detalhes</th><th>Status</th><th>Ação</th></tr></thead><tbody>{reports.map(r=><tr key={r.id}><td><b>{r.product_title}</b></td><td>{r.reporter_name}</td><td>{r.reason}</td><td>{r.details||'—'}</td><td><span className={`master-status ${r.status}`}>{statusLabel(r.status)}</span></td><td>{r.status==='open'?<button className="secondary-btn" onClick={()=>resolve(r.id)}>Resolver</button>:'—'}</td></tr>)}</tbody></table></div>}
 </div>
}

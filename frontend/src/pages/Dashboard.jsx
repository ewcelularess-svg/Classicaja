import React,{useEffect,useState} from 'react';
import {AlertTriangle, ArrowUpCircle, BadgeCheck, BellRing, Camera, Check, ChevronRight, Clock3, Copy, CreditCard, Crown, Eye, Heart, History, ImagePlus, LayoutDashboard, Link2, LockKeyhole, LogOut, MapPin, MessageCircle, PackageCheck, PackageOpen, PlusCircle, QrCode, RefreshCw, ShieldCheck, Sparkles, Trash2, Handshake, UserRound, XCircle} from 'lucide-react';
import {Link, useLocation, useNavigate} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
import {useAuth} from '../main';

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const planTone=(code)=>code==='boost_7'?'basic':code==='boost_15'?'plus':'premium';
const formatDate=(value)=>{
  if(!value) return '—';
  try{return new Date(value).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'})}catch{return value}
};
const statusLabel=(status)=>({paid:'Pago',pending:'Pendente',cancelled:'Cancelado',failed:'Falhou'}[status]||status);

const phoneDigitsBR=(value)=>{
  let d=String(value||'').replace(/\D/g,'');
  // Aceita números vindos como +55 / 55 e mantém somente DDD + número.
  if(d.startsWith('55') && d.length>11) d=d.slice(2);
  return d.slice(0,11);
};
const formatPhoneBR=(value)=>{
  const d=phoneDigitsBR(value);
  if(!d) return '';
  if(d.length<=2) return `(${d}`;
  if(d.length<=6) return `(${d.slice(0,2)}) ${d.slice(2)}`;
  if(d.length<=10) return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`;
  return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7,11)}`;
};
const verificationMeta=(status)=>({
  verified:{label:'Verificado',tone:'verified'},
  pending:{label:'Em análise',tone:'pending'},
  unverified:{label:'Não verificado',tone:'unverified'}
}[status]||{label:'Não verificado',tone:'unverified'});

const urlBase64ToUint8Array=(value)=>{
 const padding='='.repeat((4-value.length%4)%4);
 const base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/');
 const raw=window.atob(base64);
 return Uint8Array.from([...raw].map(ch=>ch.charCodeAt(0)));
};

export default function Dashboard(){
 const {refreshUser,logout}=useAuth();
 const nav=useNavigate();
 const location=useLocation();
 const [activeTab,setActiveTab]=useState(()=>{const tab=new URLSearchParams(window.location.search).get('tab');return ['overview','profile','plan','partner','payments','notifications'].includes(tab)?tab:'overview'});
 const [profile,setProfile]=useState(null);
 const [profileForm,setProfileForm]=useState({name:'',phone:'',address_line:'',neighborhood:'',city:'',state:'',postal_code:'',current_password:''});
 const [profileBusy,setProfileBusy]=useState(false);
 const [profilePhoto,setProfilePhoto]=useState(null);
 const [profilePhotoPreview,setProfilePhotoPreview]=useState('');
 const [passwordForm,setPasswordForm]=useState({current_password:'',new_password:'',confirm_password:''});
 const [passwordBusy,setPasswordBusy]=useState(false);
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
 const [pushPrefs,setPushPrefs]=useState({enabled:false,city_only:true,featured_only:false,category_slug:'',active_subscriptions:0,city:''});
 const [pushConfig,setPushConfig]=useState({enabled:false,public_key:''});
 const [pushCategories,setPushCategories]=useState([]);
 const [pushBusy,setPushBusy]=useState(false);
 const [pushSupported,setPushSupported]=useState(false);
 const [pushPermission,setPushPermission]=useState('default');

 const load=()=>Promise.all([api('/api/me/dashboard'),api('/api/plans'),api('/api/me/payments'),api('/api/me/partner-benefit'),api('/api/me')])
  .then(([dashboard, planList, history, partnerData, me])=>{
    setS(dashboard);setPlans(planList);setPayments(history||[]);setPartner(partnerData);setProfile(me);
    setProfileForm({name:me.name||'',phone:formatPhoneBR(me.phone||''),address_line:me.address_line||'',neighborhood:me.neighborhood||'',city:me.city||'',state:me.state||'',postal_code:me.postal_code||'',current_password:''});
  })
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
 useEffect(()=>{
   const supported=typeof window!=='undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
   setPushSupported(supported);
   setPushPermission(supported?window.Notification.permission:'unsupported');
   Promise.all([
     api('/api/me/push-preferences').catch(()=>null),
     api('/api/push/config').catch(()=>({enabled:false,public_key:''})),
     api('/api/categories').catch(()=>[])
   ]).then(([prefs,config,categories])=>{
     if(prefs)setPushPrefs(prefs);
     setPushConfig(config||{enabled:false,public_key:''});
     setPushCategories(categories||[]);
   });
 },[]);

 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;
 if(!s) return <div className="loading">Carregando painel...</div>;

 const cards=[
  {label:'Anúncios',value:s.total,icon:<PackageOpen/>,to:'/meus-anuncios',hint:'Gerenciar anúncios'},
  {label:'Ativos',value:s.active,icon:<PackageCheck/>,to:'/meus-anuncios?status=active',hint:'Ver anúncios ativos'},
  {label:'Visualizações',value:s.views,icon:<Eye/>,to:'/meus-anuncios?sort=views',hint:'Ver mais visualizados'},
  {label:'Favoritos recebidos',value:s.favorites_received,icon:<Heart/>,to:'/meus-anuncios?sort=favorites',hint:'Ver mais favoritados'},
  {label:'Mensagens não lidas',value:s.unread_messages,icon:<MessageCircle/>,to:'/mensagens?unread=1',hint:'Abrir mensagens'}
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

 const isMaster=Boolean(profile?.is_master);
 const profileStatusLabel=isMaster?'Master verificado':profile?.verified?'Perfil verificado':profile?.profile_review_status==='pending'?'Verificação em andamento':'Perfil incompleto';
 const profileStatusClass=(isMaster||profile?.verified)?'verified':profile?.profile_review_status==='pending'?'pending':'unverified';
 const emailSource=profile?.email_verification_source==='google'?'Google':profile?.email_verification_source==='facebook'?'Facebook':profile?.email_verification_source==='master'?'Master':'';
 const verificationItems=isMaster?[
   {key:'email',label:'E-mail',status:'verified',detail:'Conta proprietária • verificação automática'},
   {key:'name',label:'Nome',status:'verified',detail:'Dispensado de revisão • Master'},
   {key:'phone',label:'Telefone',status:'verified',detail:profile?.phone?formatPhoneBR(profile.phone):'Dispensado de revisão • Master'},
   {key:'address',label:'Endereço',status:'verified',detail:profile?.city&&profile?.state?`${profile.city} - ${profile.state}`:'Dispensado de revisão • Master'},
   {key:'avatar',label:'Foto',status:'verified',detail:profile?.avatar_url?'Foto da conta Master':'Dispensado de revisão • Master'},
 ]:[
   {key:'email',label:'E-mail',status:profile?.email_verified?'verified':'unverified',detail:profile?.email_verified?(emailSource?`Confirmado pelo ${emailSource}`:'E-mail confirmado'):'Ainda não confirmado'},
   {key:'name',label:'Nome',status:profile?.name_verification_status||'unverified',detail:'Identificação do perfil'},
   {key:'phone',label:'Telefone',status:profile?.phone_verification_status||'unverified',detail:profile?.phone?formatPhoneBR(profile.phone):'Não informado'},
   {key:'address',label:'Endereço',status:profile?.address_verification_status||'unverified',detail:profile?.city&&profile?.state?`${profile.city} - ${profile.state}`:'Não informado'},
   {key:'avatar',label:'Foto',status:profile?.avatar_verification_status||'unverified',detail:profile?.avatar_url?'Foto cadastrada':'Não enviada'},
 ];

 const saveProfile=async(e)=>{
   e.preventDefault();
   if(profile?.has_password&&!profileForm.current_password){alert('Digite sua senha atual para confirmar as alterações.');return}
   setProfileBusy(true);
   try{
     const result=await api('/api/me/profile',{method:'PUT',body:JSON.stringify(profileForm)});
     setProfile(result.user);
     setProfileForm(f=>({...f,current_password:''}));
     await refreshUser?.();
     alert(result.message||'Dados enviados para verificação.');
   }catch(e){alert(e.message)}finally{setProfileBusy(false)}
 };

 const chooseProfilePhoto=(e)=>{
   const file=e.target.files?.[0]||null;
   setProfilePhoto(file);
   setProfilePhotoPreview(file?URL.createObjectURL(file):'');
 };

 const uploadProfilePhoto=async()=>{
   if(!profilePhoto){alert('Selecione uma foto.');return}
   let password='';
   if(profile?.has_password){
     password=prompt('Digite sua senha atual para confirmar a troca da foto:')||'';
     if(!password)return;
   }
   setProfileBusy(true);
   try{
     const fd=new FormData();fd.append('current_password',password);fd.append('image',profilePhoto);
     const result=await api('/api/me/avatar',{method:'POST',body:fd});
     setProfile(result.user);setProfilePhoto(null);setProfilePhotoPreview('');await refreshUser?.();
     alert(result.message||'Foto enviada para verificação.');
   }catch(e){alert(e.message)}finally{setProfileBusy(false)}
 };

 const changePassword=async(e)=>{
   e.preventDefault();
   if(passwordForm.new_password!==passwordForm.confirm_password){alert('A confirmação da nova senha não confere.');return}
   setPasswordBusy(true);
   try{
     const result=await api('/api/me/password',{method:'PUT',body:JSON.stringify({current_password:passwordForm.current_password,new_password:passwordForm.new_password})});
     setPasswordForm({current_password:'',new_password:'',confirm_password:''});
     await refreshUser?.();
     await load();
     alert(result.message||'Senha alterada.');
   }catch(e){alert(e.message)}finally{setPasswordBusy(false)}
 };

 const persistPushPrefs=async(next)=>{
   const clean={enabled:Boolean(next.enabled),city_only:Boolean(next.city_only),featured_only:Boolean(next.featured_only),category_slug:next.category_slug||''};
   await api('/api/me/push-preferences',{method:'PUT',body:JSON.stringify(clean)});
   setPushPrefs(prev=>({...prev,...clean}));
   return clean;
 };

 const enablePush=async()=>{
   if(!pushSupported){alert('Este navegador não oferece suporte a notificações push. Use Chrome/Edge no Android ou um navegador compatível.');return}
   if(!pushConfig?.enabled || !pushConfig?.public_key){alert('O serviço de notificações ainda não está disponível. Atualize a página e tente novamente.');return}
   setPushBusy(true);
   try{
     const permission=await window.Notification.requestPermission();
     setPushPermission(permission);
     if(permission!=='granted'){alert('Permissão de notificações não concedida. Você pode liberar depois nas configurações do navegador.');return}
     const registration=await navigator.serviceWorker.register('/push-sw.js',{scope:'/'});
     await navigator.serviceWorker.ready;
     let subscription=await registration.pushManager.getSubscription();
     if(!subscription){
       subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(pushConfig.public_key)});
     }
     const json=subscription.toJSON();
     if(!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) throw new Error('O navegador não retornou uma inscrição push válida.');
     await api('/api/me/push-subscriptions',{method:'POST',body:JSON.stringify({endpoint:json.endpoint,p256dh:json.keys.p256dh,auth:json.keys.auth})});
     const cityOnly=Boolean(pushPrefs.city_only && pushPrefs.city);
     await persistPushPrefs({...pushPrefs,enabled:true,city_only:cityOnly});
     setPushPrefs(prev=>({...prev,enabled:true,city_only:cityOnly,active_subscriptions:Math.max(1,Number(prev.active_subscriptions||0))}));
   }catch(e){alert(e.message||'Não foi possível ativar as notificações.')}finally{setPushBusy(false)}
 };

 const disablePush=async()=>{
   setPushBusy(true);
   try{await persistPushPrefs({...pushPrefs,enabled:false})}catch(e){alert(e.message)}finally{setPushBusy(false)}
 };

 const updatePushOption=async(patch)=>{
   const next={...pushPrefs,...patch};
   setPushPrefs(next);
   try{await persistPushPrefs(next)}catch(e){alert(e.message)}
 };

 const testPush=async()=>{
   setPushBusy(true);
   try{await api('/api/me/push-test',{method:'POST'});alert('Notificação de teste enviada. Confira a barra de notificações do aparelho.')}catch(e){alert(e.message)}finally{setPushBusy(false)}
 };

 return <div className="page user-dashboard-v2165">
  <section className="user-panel-profile-summary">
    <div className="user-panel-avatar-wrap">
      <div className="user-panel-avatar">{profile?.avatar_url?<img src={imageUrl(profile.avatar_url)} alt={profile.name||'Perfil'}/>:<UserRound/>}</div>
      <span className={`profile-verify-dot ${profileStatusClass}`} title={profileStatusLabel}>{profile?.verified?<BadgeCheck/>:<ShieldCheck/>}</span>
    </div>
    <div className="user-panel-profile-copy"><span className="section-kicker">MINHA CONTA</span><h1>{profile?.name||'Meu painel'}</h1><p>{profile?.email}</p><span className={`profile-status-pill ${profileStatusClass}`}>{profile?.verified?<BadgeCheck/>:<ShieldCheck/>}{profileStatusLabel}</span></div>
    <Link className="primary small" to="/publicar"><PlusCircle/> Novo anúncio</Link>
  </section>

  <nav className="user-panel-tabs" aria-label="Seções do painel">
    <button className={activeTab==='overview'?'active':''} onClick={()=>setActiveTab('overview')}><LayoutDashboard/>Visão geral</button>
    <button className={activeTab==='profile'?'active':''} onClick={()=>setActiveTab('profile')}><UserRound/>Perfil e segurança</button>
    <button className={activeTab==='notifications'?'active':''} onClick={()=>setActiveTab('notifications')}><BellRing/>Notificações</button>
    <Link to="/meus-anuncios"><PackageOpen/>Meus anúncios</Link>
    <button className={activeTab==='plan'?'active':''} onClick={()=>setActiveTab('plan')}><Crown/>Plano</button>
    <button className={activeTab==='partner'?'active':''} onClick={()=>setActiveTab('partner')}><Handshake/>Parceria</button>
    <button className={activeTab==='payments'?'active':''} onClick={()=>setActiveTab('payments')}><CreditCard/>Pagamentos</button>
  </nav>

  {activeTab==='overview'&&<>
    <div className="metric-grid compact-dashboard-metrics">{cards.map(card=><Link className="metric-card metric-card-link user-metric-link" key={card.label} to={card.to} aria-label={`${card.hint}: ${card.label}`}><span className="metric-icon">{card.icon}</span><div className="metric-card-copy"><b>{card.value}</b><small>{card.label}</small><em>{card.hint}<ChevronRight/></em></div></Link>)}</div>
    <button type="button" className={`dashboard-push-cta ${pushPrefs.enabled?'active':''}`} onClick={()=>setActiveTab('notifications')}>
      <span className="dashboard-push-cta-icon"><BellRing/></span><span><b>{pushPrefs.enabled?'Notificações de novos anúncios ativas':'Receba novos anúncios no celular'}</b><small>{pushPrefs.enabled?'Toque para ajustar cidade, categoria ou destaques.':'Ative alertas push e escolha o que deseja receber.'}</small></span><ChevronRight/>
    </button>
    <div className="dashboard-actions compact-dashboard-actions"><Link to="/meus-anuncios"><b>Gerenciar anúncios</b><span>Editar, pausar ou destacar.</span></Link><Link to="/mensagens"><b>Abrir mensagens</b><span>Conversas com compradores.</span></Link><Link to="/favoritos"><b>Ver favoritos</b><span>Produtos que você salvou.</span></Link></div>
    {expiringAds.length>0 && <div className="plan-expiry-alert"><AlertTriangle/><div><b>{expiringAds.length===1?'Seu plano está perto de vencer':'Você tem planos perto de vencer'}</b><span>{expiringAds.map(item=>`${item.title} (${item.days_left ?? 0} dia${item.days_left===1?'':'s'})`).join(' • ')}</span></div></div>}
  </>}

  {activeTab==='notifications'&&<section className="push-settings-section">
    <div className="push-feature-card">
      <div className="push-feature-glow"></div>
      <div className="push-feature-icon"><BellRing/></div>
      <div className="push-feature-copy">
        <span className="push-feature-kicker">ALERTAS EM TEMPO REAL</span>
        <h2>Novos anúncios no seu celular</h2>
        <p>Receba uma notificação destacada quando um novo anúncio que combina com suas preferências for publicado.</p>
        <div className="push-status-row">
          <span className={`push-status-pill ${pushPrefs.enabled?'on':'off'}`}>{pushPrefs.enabled?'● Ativado':'● Desativado'}</span>
          <span>{pushPermission==='granted'?'Permissão do navegador liberada':pushPermission==='denied'?'Permissão bloqueada no navegador':'Aguardando sua autorização'}</span>
        </div>
      </div>
      <button type="button" className={`push-master-toggle ${pushPrefs.enabled?'on':''}`} disabled={pushBusy} onClick={pushPrefs.enabled?disablePush:enablePush} aria-pressed={pushPrefs.enabled}>
        <span></span><b>{pushBusy?'Aguarde':pushPrefs.enabled?'Ativadas':'Ativar'}</b>
      </button>
    </div>

    {!pushSupported&&<div className="push-browser-warning"><AlertTriangle/><div><b>Navegador sem suporte</b><span>Abra o ClassificaJá pelo Chrome ou Edge atualizado para receber notificações push.</span></div></div>}
    {pushPermission==='denied'&&<div className="push-browser-warning danger"><AlertTriangle/><div><b>Notificações bloqueadas</b><span>Libere as notificações para classificaja.com.br nas configurações do navegador e depois toque em Ativar.</span></div></div>}

    <div className="push-preference-grid">
      <div className="push-preference-card">
        <div><MapPin/><span><b>Somente minha cidade</b><small>{pushPrefs.city?`Receber anúncios de ${pushPrefs.city}.`:'Cadastre sua cidade no perfil para usar este filtro.'}</small></span></div>
        <button type="button" className={`mini-switch ${pushPrefs.city_only?'on':''}`} disabled={!pushPrefs.city} onClick={()=>updatePushOption({city_only:!pushPrefs.city_only})}><span></span></button>
      </div>
      <div className="push-preference-card">
        <div><Sparkles/><span><b>Somente destaques</b><small>Avise apenas quando o anúncio estiver em destaque.</small></span></div>
        <button type="button" className={`mini-switch ${pushPrefs.featured_only?'on':''}`} onClick={()=>updatePushOption({featured_only:!pushPrefs.featured_only})}><span></span></button>
      </div>
      <label className="push-category-card">
        <div><PackageOpen/><span><b>Categoria preferida</b><small>Escolha uma categoria ou receba de todas.</small></span></div>
        <select value={pushPrefs.category_slug||''} onChange={e=>updatePushOption({category_slug:e.target.value})}>
          <option value="">Todas as categorias</option>
          {pushCategories.map(cat=><option key={cat.slug} value={cat.slug}>{cat.icon} {cat.name}</option>)}
        </select>
      </label>
    </div>

    <div className="push-test-card">
      <div><BellRing/><span><b>Teste no aparelho</b><small>Envia uma notificação agora para confirmar que está funcionando.</small></span></div>
      <button type="button" className="secondary-btn" disabled={pushBusy||!pushPrefs.enabled} onClick={testPush}>Enviar teste</button>
    </div>
    <p className="push-privacy-note">Você só recebe notificações depois de ativar. O ClassificaJá não envia o seu próprio anúncio para você e você pode desativar a qualquer momento.</p>
  </section>}

  {activeTab==='profile'&&<section className="profile-security-section">
    <div className="profile-security-grid">
      <div className="profile-card-v2165 profile-verification-card">
        <div className="profile-card-title"><ShieldCheck/><div><h2>{isMaster?'Conta Master':'Status de verificação'}</h2><p>{isMaster?'A conta proprietária do ClassificaJá é verificada automaticamente e não passa por autoaprovação no Master.':'O selo geral só aparece quando todos os dados obrigatórios estiverem verificados.'}</p></div></div>
        <div className="profile-verification-list">
          {verificationItems.map(item=>{const meta=verificationMeta(item.status);return <div className="profile-verification-item" key={item.key}><div><b>{item.label}</b><small>{item.detail}</small></div><span className={`field-verification-pill ${meta.tone}`}>{meta.tone==='verified'?<BadgeCheck/>:meta.tone==='pending'?<Clock3/>:<ShieldCheck/>}{meta.label}</span></div>})}
        </div>
      </div>
      <div className="profile-card-v2165 profile-photo-card">
        <div className="profile-card-title"><Camera/><div><h2>Foto do perfil</h2><p>JPG, PNG ou WEBP até 5 MB.</p></div></div>
        <div className="profile-photo-preview">{profilePhotoPreview||profile?.avatar_url?<img src={profilePhotoPreview||imageUrl(profile?.avatar_url)} alt="Foto do perfil"/>:<UserRound/>}</div>
        <label className="profile-file-btn"><Camera/>Selecionar foto<input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseProfilePhoto}/></label>
        {profilePhoto&&<button className="primary" onClick={uploadProfilePhoto} disabled={profileBusy}>{profileBusy?'Enviando...':'Salvar foto'}</button>}
        <small className="verification-note">{isMaster?'Conta Master: a foto é atualizada sem entrar em revisão.':'Ao trocar a foto, o perfil volta para revisão do Master.'}</small>
      </div>

      <form className="profile-card-v2165 profile-data-card" onSubmit={saveProfile}>
        <div className="profile-card-title"><UserRound/><div><h2>Dados pessoais</h2><p>{isMaster?'Como proprietário do site, seus dados são atualizados sem fila de moderação. A confirmação de identidade continua obrigatória.':'Todos os dados alterados passam por nova verificação.'}</p></div></div>
        <div className="profile-form-grid">
          <label>Nome completo<input value={profileForm.name} onChange={e=>setProfileForm({...profileForm,name:e.target.value})} required/></label>
          <label>Telefone com DDD<input inputMode="tel" value={profileForm.phone} onChange={e=>setProfileForm({...profileForm,phone:formatPhoneBR(e.target.value)})} placeholder="(45) 99999-9999"/></label>
          <label className="span-2">Endereço<input value={profileForm.address_line} onChange={e=>setProfileForm({...profileForm,address_line:e.target.value})} placeholder="Rua, número e complemento"/></label>
          <label>Bairro<input value={profileForm.neighborhood} onChange={e=>setProfileForm({...profileForm,neighborhood:e.target.value})}/></label>
          <label>Cidade<input value={profileForm.city} onChange={e=>setProfileForm({...profileForm,city:e.target.value})}/></label>
          <label>Estado<input maxLength="2" value={profileForm.state} onChange={e=>setProfileForm({...profileForm,state:e.target.value.toUpperCase()})} placeholder="PR"/></label>
          <label>CEP<input inputMode="numeric" value={profileForm.postal_code} onChange={e=>setProfileForm({...profileForm,postal_code:e.target.value})} placeholder="00000-000"/></label>
          {profile?.has_password?<label className="span-2 confirmation-field"><ShieldCheck/>Senha atual para confirmar<input type="password" value={profileForm.current_password} onChange={e=>setProfileForm({...profileForm,current_password:e.target.value})} placeholder="Digite sua senha atual" required/></label>:<div className="span-2 social-profile-confirm"><ShieldCheck/><div><b>Conta conectada com {profile?.auth_provider==='google'?'Google':'Facebook'}</b><span>Alterações sensíveis usam sua sessão social recente. Se ela tiver expirado, entre novamente pelo provedor para confirmar.</span></div></div>}
        </div>
        <div className="profile-verification-banner"><ShieldCheck/><div><b>{isMaster?'Verificação automática do Master':'Verificação por campo'}</b><span>{isMaster?'A conta proprietária não entra na fila de revisão. Alterações permanecem verificadas automaticamente, mas exigem confirmação de identidade.':<>Somente o dado que você alterar volta para análise. O que já estiver verificado permanece aprovado. {profile?.email_verified?`Seu e-mail já está confirmado${emailSource?` pelo ${emailSource}`:''}.`:''}</>}</span></div></div>
        <button className="primary" disabled={profileBusy}>{profileBusy?'Salvando...':isMaster?'Salvar alterações':'Salvar e enviar para verificação'}</button>
      </form>

      <form className="profile-card-v2165 password-card-v2165" onSubmit={changePassword}>
        <div className="profile-card-title"><LockKeyhole/><div><h2>{profile?.has_password?'Senha':'Criar senha'}</h2><p>{profile?.has_password?'A senha atual confirma que a alteração é realmente sua.':'Sua conta social pode também ter uma senha do ClassificaJá. Por segurança, crie-a logo após entrar com Google/Facebook.'}</p></div></div>
        {profile?.has_password&&<label>Senha atual<input type="password" value={passwordForm.current_password} onChange={e=>setPasswordForm({...passwordForm,current_password:e.target.value})} required/></label>}
        <label>{profile?.has_password?'Nova senha':'Nova senha do ClassificaJá'}<input type="password" minLength="8" value={passwordForm.new_password} onChange={e=>setPasswordForm({...passwordForm,new_password:e.target.value})} placeholder="Mínimo de 8 caracteres" required/></label>
        <label>Confirmar nova senha<input type="password" minLength="8" value={passwordForm.confirm_password} onChange={e=>setPasswordForm({...passwordForm,confirm_password:e.target.value})} required/></label>
        <button className="primary" disabled={passwordBusy}>{passwordBusy?(profile?.has_password?'Alterando...':'Criando...'):(profile?.has_password?'Alterar senha':'Criar senha')}</button>
      </form>

      <div className="profile-card-v2165 account-session-card">
        <div className="profile-card-title"><LogOut/><div><h2>Sessão e acesso</h2><p>Encerre sua sessão neste aparelho com segurança.</p></div></div>
        <button type="button" className="account-logout-btn" onClick={()=>{if(window.confirm('Deseja sair da sua conta?')){logout();nav('/')}}}><LogOut/>Sair da conta</button>
      </div>
    </div>
  </section>}

  {activeTab==='plan'&&<section className="dashboard-plan-section">
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
          {summary.ad_limit>0&&<span><b>{summary.ads_used || 0}</b> de <b>{summary.ad_limit}</b> anúncios cadastrados • <b>{summary.ads_remaining || 0}</b> vaga(s) disponível(is)</span>}
          <span><b>{summary.featured_count || 0}</b> anúncio(s) em destaque</span>
          <span>Próximo vencimento: <b>{formatDate(summary.next_expiration)}</b></span>
          {summary.expiring_soon_count>0 && <span className="expiry-inline"><Clock3 size={15}/> {summary.expiring_soon_count} plano(s) vencendo em até 3 dias</span>}
        </div>
        <div className="summary-actions">
          <Link className="secondary-btn" to="/meus-anuncios">Administrar plano</Link>
          {summary.ads_remaining>0 && summary.quota_status!=='expired' ?
            <Link className="primary" to="/publicar"><PlusCircle/> Novo anúncio</Link>
            : summary.current_plan_code==='boost_30' ?
              <Link className="primary" to="/escolher-plano"><RefreshCw/> Renovar Premium</Link>
            : summary.current_plan_code==='boost_15' ?
              <Link className="primary" to="/escolher-plano"><ArrowUpCircle/> Renovar Plus / Upgrade</Link>
            : summary.current_plan_code==='boost_7' ?
              <Link className="primary" to="/escolher-plano"><ArrowUpCircle/> Fazer upgrade</Link>
              : <Link className="primary" to="/escolher-plano"><Sparkles/> Escolher plano</Link>}
        </div>
      </div>

      <div className="plan-summary-card compare">
        <div className="plan-mini-grid">
          {plans.map(plan=><div className={`plan-mini-card ${planTone(plan.code)}`} key={plan.code}>
            <span className="mini-name">{plan.code==='boost_7'?'Grátis':plan.code==='boost_15'?'Plus':'Premium'}</span>
            <b>{plan.free?'Grátis':money(plan.amount)}</b>
            <small>{plan.free?`${plan.ad_limit||1} anúncio • publicação padrão`:`Até ${plan.ad_limit||1} anúncios • ${plan.days} dias`}</small>
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
  </section>}

  {activeTab==='partner'&&<section className="my-partner-section">
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
  </section>}

  {activeTab==='payments'&&<section className="payment-history-section">
    <div className="section-head small-head">
      <div><span className="section-kicker">PAGAMENTOS</span><h2>Histórico de pagamentos</h2><p className="section-desc">Acompanhe pagamentos, forma utilizada, parcelas e status.</p></div>
      <History/>
    </div>
    {payments.length ? <div className="payment-history-table-wrap"><table className="payment-history-table">
      <thead><tr><th>Data</th><th>Anúncio</th><th>Plano</th><th>Forma</th><th>Parcelas</th><th>Valor</th><th>Status</th></tr></thead>
      <tbody>{payments.map(row=><tr key={row.id}><td>{formatDate(row.paid_at||row.created_at)}</td><td>{row.product_title||'—'}</td><td>{row.plan_name||row.plan_code}</td><td>{row.method==='pix'?'PIX':'Cartão'}</td><td>{row.installment_label||'—'}</td><td>{money(row.amount)}</td><td><span className={`payment-status ${row.status}`}>{statusLabel(row.status)}</span></td></tr>)}</tbody>
    </table></div> : <div className="empty payment-empty"><h3>Nenhum pagamento registrado ainda.</h3></div>}
  </section>}
 </div>
}

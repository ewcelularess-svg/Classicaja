import React,{useEffect,useRef,useState} from 'react';
import {Eye, EyeOff, Facebook, ShieldCheck} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {api} from '../lib/api';
import {useAuth} from '../main';

const loadScript=(src,id)=>new Promise((resolve,reject)=>{
  const existing=document.getElementById(id);
  if(existing){
    if(existing.dataset.loaded==='1') return resolve();
    existing.addEventListener('load',()=>resolve(),{once:true});
    existing.addEventListener('error',()=>reject(new Error('Falha ao carregar integração externa')),{once:true});
    return;
  }
  const script=document.createElement('script');
  script.id=id;script.src=src;script.async=true;script.defer=true;
  script.onload=()=>{script.dataset.loaded='1';resolve()};
  script.onerror=()=>reject(new Error('Falha ao carregar integração externa'));
  document.head.appendChild(script);
});

export default function Auth(){
 const [mode,setMode]=useState('login');
 const [showPassword,setShowPassword]=useState(false);
 const [form,setForm]=useState({name:'',email:'',phone:'',password:''});
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const [socialBusy,setSocialBusy]=useState('');
 const [providers,setProviders]=useState(null);
 const googleButtonRef=useRef(null);
 const {login}=useAuth();
 const nav=useNavigate();

 const finishLogin=(data)=>{
   login(data);
   nav(data?.new_user ? '/escolher-plano' : '/');
 };

 const submit=async e=>{
   e.preventDefault();
   setErr('');setBusy(true);
   try{
     const data=await api(`/api/auth/${mode==='login'?'login':'register'}`,{method:'POST',body:JSON.stringify(form)});
     login(data);
     nav(mode==='register'?'/escolher-plano':'/');
   }catch(e){setErr(e.message)}finally{setBusy(false)}
 };

 const socialLogin=async(provider,credential)=>{
   setErr('');setSocialBusy(provider);
   try{
     const data=await api('/api/auth/social',{method:'POST',body:JSON.stringify({provider,credential})});
     finishLogin(data);
   }catch(e){setErr(e.message)}finally{setSocialBusy('')}
 };

 useEffect(()=>{
   api('/api/auth/providers').then(setProviders).catch(()=>setProviders({google:{enabled:false},facebook:{enabled:false}}));
 },[]);

 useEffect(()=>{
   if(!providers?.google?.enabled || !providers.google.client_id || !googleButtonRef.current) return;
   let cancelled=false;
   loadScript('https://accounts.google.com/gsi/client','google-gsi-script').then(()=>{
     if(cancelled || !window.google?.accounts?.id || !googleButtonRef.current) return;
     window.google.accounts.id.initialize({
       client_id:providers.google.client_id,
       callback:(response)=>response?.credential&&socialLogin('google',response.credential),
       auto_select:false,
       cancel_on_tap_outside:true,
     });
     googleButtonRef.current.innerHTML='';
     const googleWidth=Math.max(240,Math.min(330,googleButtonRef.current.clientWidth||330));
     window.google.accounts.id.renderButton(googleButtonRef.current,{
       type:'standard',theme:'outline',size:'large',shape:'pill',text:mode==='register'?'signup_with':'continue_with',width:googleWidth,logo_alignment:'left'
     });
   }).catch(()=>{});
   return()=>{cancelled=true};
 },[providers?.google?.enabled,providers?.google?.client_id,mode]);

 const loginFacebook=async()=>{
   if(!providers?.facebook?.enabled) return;
   setErr('');setSocialBusy('facebook');
   try{
     await loadScript('https://connect.facebook.net/pt_BR/sdk.js','facebook-jssdk');
     if(!window.FB) throw new Error('Não foi possível abrir o Facebook');
     window.FB.init({
       appId:providers.facebook.app_id,
       cookie:true,
       xfbml:false,
       version:providers.facebook.graph_version||'v26.0',
     });
     window.FB.login((response)=>{
       const accessToken=response?.authResponse?.accessToken;
       if(accessToken) socialLogin('facebook',accessToken);
       else {setSocialBusy('');setErr('Login com Facebook cancelado ou não autorizado.')}
     },{scope:'public_profile,email'});
   }catch(e){setSocialBusy('');setErr(e.message||'Falha no login com Facebook')}
 };

 const hasSocial=Boolean(providers?.google?.enabled||providers?.facebook?.enabled);
 return <div className="auth-page"><div className="auth-card auth-card-social">
   <div className="brand auth-brand"><span className="brand-mark">C</span><span>ClassificaJá</span></div>
   <h1>{mode==='login'?'Entrar na sua conta':'Criar conta'}</h1>
   <p>{mode==='login'?'Acesse para anunciar, editar e acompanhar seus produtos.':'Cadastre-se e publique seus anúncios.'}</p>

   {hasSocial&&<div className="social-auth-area">
     {providers?.google?.enabled&&<div className={`google-login-holder ${socialBusy==='google'?'is-busy':''}`} ref={googleButtonRef}/>} 
     {providers?.facebook?.enabled&&<button type="button" className="social-login-btn facebook-login-btn" onClick={loginFacebook} disabled={Boolean(socialBusy)}><Facebook size={20}/>{socialBusy==='facebook'?'Conectando...':mode==='login'?'Continuar com Facebook':'Cadastrar com Facebook'}</button>}
     <div className="auth-divider"><span>ou continue com e-mail</span></div>
   </div>}

   <form onSubmit={submit}>
    {mode==='register'&&<><label>Nome<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} required/></label><label>WhatsApp<input value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})} placeholder="(45) 99999-9999"/></label></>}
    <label>E-mail<input type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} required/></label>
    <label>Senha<div className="password-field"><input type={showPassword?'text':'password'} value={form.password} onChange={e=>setForm({...form,password:e.target.value})} minLength={6} required/><button type="button" className="password-toggle" onClick={()=>setShowPassword(v=>!v)} aria-label={showPassword?'Ocultar senha':'Ver senha'} title={showPassword?'Ocultar senha':'Ver senha'}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>
    {err&&<div className="form-error">{err}</div>}
    <button className="primary wide" disabled={busy||Boolean(socialBusy)}>{busy?'Aguarde...':mode==='login'?'Entrar':'Criar conta'}</button>
   </form>
   {hasSocial&&<div className="social-security-note"><ShieldCheck size={16}/><span>Google/Facebook confirmam sua identidade. Telefone, endereço, foto e alterações de perfil continuam sujeitos às regras de verificação do ClassificaJá.</span></div>}
   <button className="switch-auth" onClick={()=>{setErr('');setMode(mode==='login'?'register':'login')}}>{mode==='login'?'Ainda não tem conta? Cadastre-se':'Já tem conta? Entrar'}</button>
 </div></div>
}

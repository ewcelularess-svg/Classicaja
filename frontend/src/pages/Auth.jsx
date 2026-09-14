import React,{useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {api} from '../lib/api';
import {useAuth} from '../main';
export default function Auth(){
 const [mode,setMode]=useState('login'); const [form,setForm]=useState({name:'',email:'',phone:'',password:''}); const [err,setErr]=useState(''); const [busy,setBusy]=useState(false); const {login}=useAuth(); const nav=useNavigate();
 const submit=async e=>{e.preventDefault();setErr('');setBusy(true);try{const data=await api(`/api/auth/${mode==='login'?'login':'register'}`,{method:'POST',body:JSON.stringify(form)});login(data);nav('/')}catch(e){setErr(e.message)}finally{setBusy(false)}};
 return <div className="auth-page"><div className="auth-card"><div className="brand auth-brand"><span className="brand-mark">C</span><span>ClassificaJá</span></div><h1>{mode==='login'?'Entrar na sua conta':'Criar conta'}</h1><p>{mode==='login'?'Acesse para anunciar, editar e acompanhar seus produtos.':'Cadastre-se e publique seus anúncios.'}</p>
  <form onSubmit={submit}>{mode==='register'&&<><label>Nome<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} required/></label><label>WhatsApp<input value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})} placeholder="(45) 99999-9999"/></label></>}
   <label>E-mail<input type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} required/></label><label>Senha<input type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} minLength={6} required/></label>{err&&<div className="form-error">{err}</div>}<button className="primary wide" disabled={busy}>{busy?'Aguarde...':mode==='login'?'Entrar':'Criar conta'}</button></form>
  <button className="switch-auth" onClick={()=>{setErr('');setMode(mode==='login'?'register':'login')}}>{mode==='login'?'Ainda não tem conta? Cadastre-se':'Já tem conta? Entrar'}</button>
 </div></div>
}

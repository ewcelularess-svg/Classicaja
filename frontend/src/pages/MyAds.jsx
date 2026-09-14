import React,{useEffect,useState} from 'react';
import {Pencil, PauseCircle, PlayCircle, PlusCircle, Sparkles, Trash2} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const statusLabel=s=>({active:'Ativo',paused:'Pausado',rejected:'Rejeitado',sold:'Vendido'}[s]||s);
export default function MyAds(){
 const [items,setItems]=useState([]); const [err,setErr]=useState('');
 const load=()=>api('/api/me/products').then(setItems).catch(e=>setErr(e.message)); useEffect(()=>{load()},[]);
 const del=async id=>{if(confirm('Excluir este anúncio?')){await api(`/api/products/${id}`,{method:'DELETE'});load()}};
 const toggle=async p=>{await api(`/api/products/${p.id}`,{method:'PUT',body:JSON.stringify({status:p.status==='active'?'paused':'active'})});load()};
 return <div className="page"><div className="section-head"><div><span className="section-kicker">PAINEL DO VENDEDOR</span><h1>Meus anúncios</h1></div><Link className="primary small" to="/publicar"><PlusCircle/> Novo anúncio</Link></div>
 {err?<div className="empty"><h3>{err}</h3></div>:items.length?<div className="manage-list">{items.map(p=><div className="manage-card advanced" key={p.id}>
  <Link to={`/produto/${p.id}`} className="manage-thumb">{p.image_url?<img src={imageUrl(p.image_url)}/>:<span>📦</span>}</Link>
  <div className="manage-info"><Link to={`/produto/${p.id}`}><b>{p.title}</b></Link><span>{money(p.price)}</span><small>{p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state} • {p.views} visualizações</small><div className="status-line"><span className={`status-dot ${p.status}`}></span>{statusLabel(p.status)}{p.featured_active&&<em>• Em destaque</em>}</div></div>
  <div className="manage-actions"><Link className="edit-btn" to={`/editar/${p.id}`}><Pencil/> Editar</Link><Link className="boost-btn" to={`/destaque/${p.id}`}><Sparkles/> Destacar</Link><button className="secondary-btn" onClick={()=>toggle(p)}>{p.status==='active'?<PauseCircle/>:<PlayCircle/>}{p.status==='active'?'Pausar':'Ativar'}</button><button className="danger" onClick={()=>del(p.id)}><Trash2/> Excluir</button></div>
 </div>)}</div>:<div className="empty"><h3>Você ainda não publicou nada.</h3><Link className="primary" to="/publicar">Criar primeiro anúncio</Link></div>}</div>
}

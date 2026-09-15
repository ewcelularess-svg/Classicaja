import React,{useEffect,useMemo,useState} from 'react';
import {Eye, Heart, Pencil, PauseCircle, PlayCircle, PlusCircle, Sparkles, Trash2, XCircle} from 'lucide-react';
import {Link,useSearchParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const statusLabel=s=>({active:'Ativo',paused:'Pausado',rejected:'Rejeitado',sold:'Vendido'}[s]||s);
export default function MyAds(){
 const [items,setItems]=useState([]); const [err,setErr]=useState(''); const [busyCancel,setBusyCancel]=useState('');
 const [params,setParams]=useSearchParams();
 const statusFilter=params.get('status')||'';
 const sortMode=params.get('sort')||'';
 const load=()=>api('/api/me/products').then(setItems).catch(e=>setErr(e.message)); useEffect(()=>{load()},[]);
 const visibleItems=useMemo(()=>{
   let list=[...items];
   if(statusFilter) list=list.filter(item=>item.status===statusFilter);
   if(sortMode==='views') list.sort((a,b)=>Number(b.views||0)-Number(a.views||0));
   if(sortMode==='favorites') list.sort((a,b)=>Number(b.favorites_received||0)-Number(a.favorites_received||0));
   return list;
 },[items,statusFilter,sortMode]);
 const viewTitle=statusFilter==='active'?'Anúncios ativos':sortMode==='views'?'Mais visualizados':sortMode==='favorites'?'Mais favoritados':'Meus anúncios';
 const viewDesc=statusFilter==='active'?'Somente anúncios atualmente ativos.':sortMode==='views'?'Ranking dos seus anúncios por visualizações.':sortMode==='favorites'?'Ranking dos seus anúncios pelos favoritos recebidos.':'';
 const clearView=()=>setParams({});
 const del=async id=>{if(confirm('Excluir este anúncio?')){await api(`/api/products/${id}`,{method:'DELETE'});load()}};
 const toggle=async p=>{await api(`/api/products/${p.id}`,{method:'PUT',body:JSON.stringify({status:p.status==='active'?'paused':'active'})});load()};
 const cancelFeature=async p=>{ if(!confirm('Deseja cancelar o destaque deste anúncio?')) return; setBusyCancel(p.id); try{ await api(`/api/products/${p.id}/cancel-feature`,{method:'POST'}); load(); } catch(e){ alert(e.message);} finally{ setBusyCancel(''); } };
 return <div className="page"><div className="section-head"><div><span className="section-kicker">PAINEL DO VENDEDOR</span><h1>{viewTitle}</h1>{viewDesc&&<p className="myads-view-desc">{viewDesc}</p>}</div><div className="myads-head-actions">{(statusFilter||sortMode)&&<button type="button" className="secondary-btn" onClick={clearView}>Ver todos</button>}<Link className="primary small" to="/publicar"><PlusCircle/> Novo anúncio</Link></div></div>
 {err?<div className="empty"><h3>{err}</h3></div>:visibleItems.length?<div className="manage-list">{visibleItems.map(p=><div className="manage-card advanced" key={p.id}>
  <Link to={`/produto/${p.id}`} className="manage-thumb">{p.image_url?<img src={imageUrl(p.image_url)} alt={p.title}/>:<span>📦</span>}</Link>
  <div className="manage-info"><Link to={`/produto/${p.id}`}><b>{p.title}</b></Link><span>{money(p.price)}</span><small>{p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state}</small><div className="manage-performance"><span><Eye/> {Number(p.views||0).toLocaleString('pt-BR')} visualizações</span><span><Heart/> {Number(p.favorites_received||0).toLocaleString('pt-BR')} favoritos</span></div><div className="status-line"><span className={`status-dot ${p.status}`}></span>{statusLabel(p.status)}{p.featured_active&&<em>• Em destaque</em>}</div></div>
  <div className="manage-actions"><Link className="edit-btn" to={`/editar/${p.id}`}><Pencil/> Editar</Link><Link className="boost-btn" to={`/destaque/${p.id}`}><Sparkles/>{p.featured_active?(Number(p.boost_level||0)>=3?'Renovar Premium':'Migrar plano'):'Destacar'}</Link>{p.featured_active&&<button className="danger-lite-btn" onClick={()=>cancelFeature(p)} disabled={busyCancel===p.id}><XCircle/>{busyCancel===p.id?'Cancelando...':'Cancelar destaque'}</button>}<button className="secondary-btn" onClick={()=>toggle(p)}>{p.status==='active'?<PauseCircle/>:<PlayCircle/>}{p.status==='active'?'Pausar':'Ativar'}</button><button className="danger" onClick={()=>del(p.id)}><Trash2/> Excluir</button></div>
 </div>)}</div>:<div className="empty"><h3>{items.length?'Nenhum anúncio corresponde a este filtro.':'Você ainda não publicou nada.'}</h3>{items.length?(statusFilter||sortMode)&&<button type="button" className="secondary-btn" onClick={clearView}>Ver todos os anúncios</button>:<Link className="primary" to="/publicar">Criar primeiro anúncio</Link>}</div>}</div>
}
